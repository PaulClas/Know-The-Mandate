# Agent transparency: detecting agents that hide, invent or rewrite what they did

> Status: **implemented in the sandbox** (`apps/api/kym/transparency.py`, tested in `tests/security/test_transparency.py` and four red-team attacks). Experimental, synthetic data, self-assessed, not externally reviewed.

## The problem

An AI agent can misreport itself. Its reasoning ("chain of thought") and its own logs are produced by the very system being governed, so they can be incomplete, edited after the fact, or fabricated. A model's stated reasoning is not guaranteed to be a faithful record of why it acted; how far that holds is an open research question, and KYM does not depend on how it is resolved. A control plane that *believes* what an agent says about itself inherits every one of those failures.

## The principle

**Never trust an agent's account of itself. Enforce on what the bank can observe.**

KYM's core already follows this: the mandate is checked against the request the bank receives, and the evidence ledger records what the bank saw, signed by the bank. Transparency extends the same principle to the agent's own claims: the bank asks the agent to account for itself, then **checks the account against the bank's own records**. A discrepancy is a signed, restricting event.

## What the bank can and cannot do

| The bank can | The bank cannot |
|---|---|
| Record every request that reaches it (including denied ones), independent of the agent | See what the agent does at other banks, with other tools, or with data |
| Require a signed, hash-chained log and reconcile it with its own records | Read, verify or interpret the agent's reasoning |
| Make the agent commit to a digest of its reasoning log *before* acting, then demand the reveal | Know whether a log committed before the action was honest in the first place |
| Treat silence, refusal and late reports as violations | Stop an agent that is willing to look compliant while acting elsewhere |

Transparency therefore makes **hiding and after-the-fact rewriting detectable for actions that touch the bank**. It does not make an agent honest. That limit is a documented honest gap in the red-team harness (`out_of_band_action`).

## Mechanisms

### 1. Signed, hash-chained activity reports

An operator **enrols** an agent (`POST /api/agents/{id}/transparency/enroll`, interval and grace period). The bank returns an anchor timestamp. The agent keeps an append-only log (`agent_sdk.ActivityLog`): each entry has a sequence number, the previous entry's hash and its own hash. Periodically it submits a report: a compact JWS (`typ: kym-activity-report+jwt`, `alg: ES256`) signed with the agent's **registered key**, covering a contiguous time window.

The bank verifies the signature and the chain, then reconciles against its own `transactions` (payment and transfer attempts, including denied ones):

| Finding | Meaning |
|---|---|
| `UNREPORTED_ACTION` | The bank saw a payment or transfer in the window that the report does not mention (a hidden action) |
| `PHANTOM_ACTION` | The report claims a bank request the bank has no record of for this agent (an invented action) |
| `DECLARATION_MISMATCH` | The report states a different amount or counterparty than the bank recorded |
| `LOG_CHAIN_BREAK` | An entry is missing, reordered or altered: the log does not extend the previously accepted head |
| `WINDOW_GAP` | The window does not start where the previous one ended: time is unreported (or re-reported) |

### 2. Commit-reveal for reasoning logs

Before acting, the agent may commit to `sha256(nonce ‖ 0x00 ‖ canonical_json(log))` (`POST /bank/agents/{id}/commitments`, `typ: kym-log-commitment+jwt`). The bank stores the commitment with a bank-side timestamp, so it provably existed before any later dispute. An operator or investigator can **demand the reveal** (`POST /api/commitments/{id}/demand-reveal`, with a deadline):

| Outcome | Result |
|---|---|
| Reveal matches the commitment | `REVEALED`. The log is now consistent with what the agent committed to. It is still **untrusted content**: consistency, not truth |
| Reveal differs | `LOG_SWAPPED`: proof the log was altered or replaced after the fact |
| No reveal by the deadline | `REVEAL_REFUSED`: refusing to show the log is itself a violation |

### 3. Dead-man's switch

If an enrolled agent files no valid report within `interval_hours + grace_minutes`, the gateway marks it `REPORT_OVERDUE` **before making the next decision**, so silence cannot outrun enforcement. The same check runs when anyone reads the agent's transparency status.

## Consequence and recovery

A violation:

1. restricts the agent (the existing `RESTRICTED` status: read-only; money movement is denied by the unchanged decision point),
2. appends a signed `AGENT_TRANSPARENCY_VIOLATION` event with the findings, and
3. adds an incident to the agent's record.

Only a **bank operator** can clear it (`POST /api/agents/{id}/transparency/clear`, a reason is required). Clearing is recorded in the ledger together with the acknowledged violations and the old anchor and head, resets the log chain, and re-verifies the agent. Customers cannot clear it.

## Event types (evidence ledger)

`AGENT_TRANSPARENCY_ENROLLED`, `AGENT_ACTIVITY_REPORTED`, `AGENT_TRANSPARENCY_VIOLATION`, `AGENT_TRANSPARENCY_CLEARED`, `AGENT_LOG_COMMITTED`, `AGENT_REVEAL_DEMANDED`, `AGENT_LOG_REVEALED`. Agent-supplied content is stored as agent-supplied and never used as an input to any authorization decision.

## HTTP surface

| Endpoint | Caller | Purpose |
|---|---|---|
| `POST /api/agents/{id}/transparency/enroll` | admin | Require reports on a schedule |
| `GET /api/agents/{id}/transparency` | admin, investigator | Status, reports, commitments, next deadline |
| `POST /api/agents/{id}/transparency/clear` | admin | Close a violation after review |
| `POST /api/commitments/{id}/demand-reveal` | admin, investigator | Demand the committed log |
| `POST /bank/agents/{id}/activity-reports` | agent (JWS) | Submit a signed report |
| `POST /bank/agents/{id}/commitments` | agent (JWS) | Commit before acting |
| `POST /bank/agents/{id}/commitments/{cid}/reveal` | agent (JWS) | Reveal the committed log |

The agent-facing endpoints need no session: the ES256 signature under the agent's registered key authenticates them, `iat` must be within 10 minutes, identical submissions are idempotent, bodies are capped, and the normal rate limits apply.

## Try it

```bash
PYTHONPATH=apps/api .venv/bin/python examples/03_agent_transparency.py   # honest report, a hidden payment, a swapped log
make redteam                                                              # hidden_action, phantom_action, log_swap, silent_agent, out_of_band_action
```

## Limits, stated plainly

* Only actions that **touch this bank** are reconciled, and only payment and transfer attempts (reads and delegation are not).
* Reasoning is **never verified**. Commit-reveal proves that a log was not changed after commitment; an agent can still commit to a sanitized log before acting. See [security review](../security/security-review.md) O-23 to O-26.
* The agent must learn the bank's transaction id (returned in responses) to log a request. An agent that discards it will be flagged `UNREPORTED_ACTION`, which fails safe.
* Enrolment is opt-in per agent in this PoC, and clearing is a single-operator action (no maker-checker).
* It adds recurring work for agent operators and for the bank (reports, reveals, reviews). That cost is real and unmeasured.
