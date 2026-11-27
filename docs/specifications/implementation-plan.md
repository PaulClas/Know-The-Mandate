# Implementation plan (as executed)

1. Foundation: models, seed data, bank simulator, evidence ledger, canonical JSON.
2. Semantic layer: ontology/SHACL/JSON-LD, mandate schema, KYM-CNL compiler.
3. Authorization: PDP, mandate lifecycle, sandbox OAuth (PAR/PKCE/RAR/DPoP), revocation.
4. Execution: gateway/PEP, atomic budgets, risk, approvals, payment engine with decision certificates.
5. Evidence: signed events, checkpoints, replay, dispute packages, responsibility mapping.
6. Governance: delegation/attenuation/cascade, regulatory mappings, standards matrix, protocol adapters.
7. Demonstration/security: scenarios A–M, sandbox agents, UI, tests (unit, property, integration, security, Playwright), benchmark, docs.

Vertical slice first (register → mandate → token → payment → ledger), then breadth. Decisions are in `docs/adr`.
