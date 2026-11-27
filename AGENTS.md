# AGENTS.md — guidance for coding assistants

KYM is a security-sensitive proof of concept. Preserve these invariants when changing anything.

## Non-negotiable invariants

1. **Deny by default; fail closed.** Missing permission, missing risk information, unverifiable mandate/policy state ⇒ deny or defer. Never "default allow" to make a scenario pass.
2. **Possession of a valid token ≠ authority.** OAuth gives technical permission only. The PDP (`policy.py`) decides per request from authoritative mandate state.
3. **Explicit prohibitions override permissions.** No trust score, risk score, LLM output, ontology inference or UI state may override a prohibition, revocation or failed limit.
4. **No implicit inheritance.** Taxonomy superclasses grant nothing. Authority is per exact action id (`taxonomy.py`).
5. **Only the PEP reaches the payment engine.** Agents talk HTTP to `/bank/*`. `bank.execute_authorized` requires a signed, unexpired, single-use decision certificate bound to the exact `op_hash`. Do not add any other path to money movement.
6. **PDP purity.** `policy.evaluate` is a pure function of a JSON snapshot (no clock, DB or network). Decisions store the snapshot so they can be replayed (`disputes.build_package`). Keep it deterministic.
7. **Atomicity.** State change + evidence event commit in one `db.write()` transaction under `db.WRITE_LOCK`. Budget check, reservation and execution happen inside the same locked transaction.
8. **Immutability.** Mandate content per version is immutable; lifecycle status, counters and revocation are separate authoritative records. Authority changes ⇒ new version ⇒ new customer approval.
9. **Money is integer minor units.** Never use floats for money. Validate API amounts with `money.require_minor`.
10. **Evidence discipline.** Every lifecycle transition, token issue, decision, approval and execution appends a signed event. Never store reusable tokens or private keys. Keep PII/transaction detail in the protected payload store, not in the chain.
11. **Labelling honesty.** Simulated things stay labelled simulated (UI + docs). Do not claim a standard is implemented when only a mock exists; update `standards/standards.json` and `docs/research/standards-mapping.md` when status changes. Do not claim compliance or certification.
12. **LLMs have no authority.** An optional LLM may only *propose* typed tool calls or CNL text (`sandbox.ToolCallProposer`); it can never issue/approve a mandate, sign, decide authorization or reach the payment engine.

13. **Unauthenticated surfaces must not amplify.** Anything reachable without a valid token (`/bank`, `/oauth`, `/adapters`) must be rate limited, must not write unbounded ledger events (`security.REJECT_EVENTS`), and must not do expensive work (scrypt, SPARQL) while holding `db.WRITE_LOCK`.
14. **Fail closed outside the demo.** `KYM_ENV != demo` disables no-password sessions, reset and red-team runs. Never ship a constant secret; the session secret is per-install (`config.session_secret`).
15. **Verifiers pin keys.** `disputes.verify_package` must be given trusted keys by the caller; embedded keys prove only internal consistency.
16. **Identifiers are validated at the boundary** (`schemas.ID_RE`, `agents.AGENT_ID_RE`) because they become file names and RDF IRIs. Money is capped (`money.MAX_MINOR`).
18. **Never trust an agent's account of itself.** Agent-supplied logs, reasoning, rationales and reports are untrusted content: store them labelled, never use them as an input to any authorization decision, and reconcile them against what the bank observed (`transparency.py`). Transparency findings restrict the agent through the existing status machinery; do not add a second enforcement path.
17. **Keep the proof honest.** `redteam.py` compares KYM with scope-only and OAuth+static-RAR baselines. Do not weaken a baseline to flatter KYM (`tests/security/test_redteam.py` pins expectations) and do not remove the documented honest gaps (`redteam.HONEST_GAPS`: `in_mandate_malicious`, `out_of_band_action`). Add attacks KYM fails rather than hiding them. When counts change, update `README.md`, `docs/faq.md`, `llms.txt`, then run `make llms-full`; `tests/unit/test_docs_consistency.py` checks them.

## Module map (modular monolith, `apps/api/kym`)

| Layer | Modules |
|---|---|
| Semantic | `ontology_service` (graph, SHACL, JSON-LD, safe SPARQL) · `cnl` (grammar/compile) · `schemas` · `taxonomy` |
| Identity | `kyc` · `agents` (KYA, attestation, trust) · `auth` (demo sessions/RBAC) |
| Authority | `mandates` (lifecycle, delegation) · `policy` (PDP) · `risk` · `approvals` |
| Credentials | `oauth` (sandbox AS, DPoP) · `agent_sdk` (agent-side client, `ActivityLog`) |
| Transparency | `transparency` (signed activity reports, commit-reveal, dead-man's switch) |
| Enforcement | `gateway` (PEP) · `bank` (accounts, double-entry, payment engine) |
| Evidence | `ledger` · `disputes` · `responsibility` · `redteam` (executable proof) |
| Hardening | `security` (rate limits, headers, body cap) · `sparql_worker` (killable SPARQL child) |
| Surface | `app` (FastAPI routes) · `adapters` (MCP/AP2) · `compliance` |
| Demo | `seed` · `sandbox` · `scenarios` · `demo` · `cli` |

Boundaries: `policy`, `risk` and `canon` are pure (no DB). `gateway` is the only caller of `bank.execute_authorized`. `sandbox`/`agent_sdk` use HTTP only.

## Working rules

* Run `make test` and `make lint` before finishing. Add tests for new invariants (property-based where it fits). Do not suppress failing tests; do not weaken a security check to make a scenario pass.
* Pin dependencies in `pyproject.toml`. Prefer maintained libraries for crypto/JOSE/RDF. Do not hand-roll cryptographic primitives.
* Schema changes: update `db.py`, regenerate the Alembic migration (`cd apps/api && alembic revision --autogenerate`), keep `tests/integration/test_scenarios_and_migrations.py` green. Mandate model changes: `make schema` and update the web types.
* Keep reason codes in `policy.REASON_CODES` / `EXTENDED_REASON_CODES`. Extensions beyond the base list must be documented in `docs/specifications/mandate-spec.md`.
* New regulatory/standards claims need an official source URL and a verification date, or must be marked unverified. Never invent legal requirements.
* Demo-only mechanisms (keys on disk, no-password sessions, server-held consent keys) must stay clearly labelled. Never commit secrets.
