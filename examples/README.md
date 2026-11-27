# Examples

Runnable, synthetic-data examples. Every example is exercised by [tests/integration/test_examples.py](../tests/integration/test_examples.py), so they cannot silently rot.

| File | What it shows | How to run |
|---|---|---|
| [01_quickstart_bill_payment.py](01_quickstart_bill_payment.py) | End to end: compile a mandate, activate it, obtain a DPoP-bound OAuth token, then make four payments. Shows that a valid token is not enough: one payment is allowed, one needs a human, two are denied. Uses a throwaway data directory | `PYTHONPATH=apps/api .venv/bin/python examples/01_quickstart_bill_payment.py` |
| [02_http_walkthrough.sh](02_http_walkthrough.sh) | The same API over plain HTTP with `curl`: health, demo session, compile KYM-CNL, verify the evidence ledger | `make api` in one terminal, then `bash examples/02_http_walkthrough.sh` |
| [03_agent_transparency.py](03_agent_transparency.py) | An agent hides a payment from its own signed log and later swaps its reasoning log; the bank catches both by reconciling against its own records, restricts the agent, and a human clears it. Shows the limits too | `PYTHONPATH=apps/api .venv/bin/python examples/03_agent_transparency.py` |
| [mandates/](mandates) | Library of KYM-CNL mandates. `{{EXPIRES_AT}}` is replaced by a timestamp 30 days ahead | `make api`, then paste into **Mandate Studio** at <http://localhost:3000/studio>, or use the walkthrough |

## Mandate library

| Mandate | Intent |
|---|---|
| [01-read-only-analyst.cnl](mandates/01-read-only-analyst.cnl) | Read balances and transactions only; no money movement, no delegation |
| [02-bill-payer.cnl](mandates/02-bill-payer.cnl) | Pay one named biller up to CAD 250 per payment and CAD 500 per month; human approval above CAD 100 |
| [03-dual-approval.cnl](mandates/03-dual-approval.cnl) | As above, but payments above CAD 100 need two distinct human approvals |

KYM-CNL has no comment syntax (see the [CNL specification](../docs/specifications/kym-cnl-spec.md)). Money-moving mandates must carry a per-transaction maximum and a cumulative limit, or the bank rejects them.

## Expected output of the quickstart

```text
mandate mdt_… v1 is ACTIVE (digest sha256:…)
agent holds a valid token with scope: balances.read payments.initiate

  CAD   85.00 -> beneficiary_hydro_quebec   HTTP 201  decision=ALLOW
  CAD  180.00 -> beneficiary_hydro_quebec   HTTP 202  decision=REQUIRE_HUMAN_APPROVAL
  CAD  300.00 -> beneficiary_hydro_quebec   HTTP 403  decision=DENY  ['TRANSACTION_LIMIT_EXCEEDED']
  CAD   50.00 -> beneficiary_videotron      HTTP 403  decision=DENY  ['BENEFICIARY_NOT_AUTHORIZED']
```

Want the full set? `make scenarios` runs scenarios A to M, and `make redteam` runs the 23-attack comparison.
