# Ten-minute technical walkthrough

1. **Problem framing (1 min)** — four concepts: identity, technical permission, delegated authority, financial execution. Open `/standards` to show what is implemented/simulated/mapped and that interoperability was not tested.
2. **Ontology + CNL (2 min)** — `/ontology`: schema graph, PROV-O/ODRL reuse, action taxonomy with *no implicit inheritance*; SPARQL examples (agents that can initiate payments from an account, mandates expiring in 7 days, downstream of a revoked parent). Studio: same authority in two phrasings ⇒ same digest.
3. **Credentials (1.5 min)** — `GET /.well-known/oauth-authorization-server`; PAR → bank-hosted approval → code + PKCE + DPoP → ES256 JWT with `act`, `cnf.jkt`, RAR `kym_financial_mandate`, KYM claims. Playground: token profiles (wrong audience, expired, missing scope, wrong actor, revoked, no DPoP) all rejected by the same PDP.
4. **PDP (2 min)** — `/playground`: trace of passed/failed checks, rule names, reason codes; show intersection semantics; `make benchmark` numbers (`docs/benchmarks/latest.json`).
5. **Enforcement (1.5 min)** — only signed single-use decision certificates reach the payment engine (`tests/security`); atomic budgets (Scenario H: exactly as many succeed as the budget allows); idempotency; double-entry trial balance.
6. **Delegation (1 min)** — Scenario G: CAD 5,000 rejected, CAD 200 accepted, parent revocation cascades; `/delegation` graph.
7. **Evidence (1 min)** — signed hash chain, checkpoints with witness key, Scenario L tamper matrix, replay of a historic decision, offline-verifiable evidence package.
8. **Limits (≤1 min)** — see the production-readiness gap analysis: no HSM, simulated passkeys, single-process locking, sandbox AS.
