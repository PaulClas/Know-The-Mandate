# Production readiness gap analysis

KYM is a proof of concept. Gaps below are **not** closed in this repository.

| Area | Demo | Needed for production |
|---|---|---|
| Customer authentication & consent | Role sessions without passwords; server-held demo keys; `DEMO_SIMULATED_SESSION` assurance | OIDC with passkeys/WebAuthn, step-up auth, customer-held keys or qualified e-signature where law requires, accessibility and fraud analytics |
| Authorization server | Sandbox adapter on PyJWT/cryptography; no mTLS, refresh, JARM, request objects | FAPI 2.0-certified server (conformance testing), mTLS or DPoP at scale, key rotation, client registration |
| Keys | PEM files in `.kym-data/keys` | HSM/KMS, separation of ledger/decision/consent keys, rotation and revocation, key ceremonies |
| Evidence ledger | Local hash chain + signed checkpoints + file export | WORM storage, RFC 3161 timestamping, Merkle transparency log, external audit witnesses, retention/legal hold, tested restore |
| Concurrency | Single-process lock + DB transactions (SQLite, PostgreSQL 14 single process verified) | Row-level locking/serializable isolation, idempotency stores, multi-node tests, outbox if the ledger becomes a service |
| Isolation | Modular monolith | Separate trust domains for PEP, payment engine and ledger with mutual authentication (mTLS/SPIFFE), network policy |
| Agent identity | Demo attestation signed by a demo key | SPIFFE/SPIRE or cloud workload identity federation, SLSA/in-toto provenance, hardware-backed keys, continuous posture (CAEP/SSF) |
| Risk/KYT/KYC/AML | Synthetic signals and watch list | Licensed screening, model governance, regulator-approved controls, case management for referred items (clearing workflow not implemented) |
| Payments | Simulated double-entry | Real rails, settlement, reconciliation, reversal/chargeback processes |
| Policy lifecycle | Versioned JSON file | Change control, separation of duties, staged rollout, policy-version floors, shadow evaluation |
| Mandate semantics | Single currency per mandate, subset of constraints | Recurring schedules, multi-currency, merchant category handling, revocation of delegated child by parent agent, amendment diffing UX |
| Ops | Metrics in-process (real p50/p95/p99), structured logs minimal | OpenTelemetry export, SLOs, alerting, DR, capacity tests, security testing and pen test, SBOM, hash-locked dependencies |
| Legal/regulatory | Mappings with official URLs; several items unverified (see regulatory README) | Counsel review per jurisdiction; no automated liability determination; privacy impact assessment; French-language review |
| Interoperability | None tested | Conformance suites; AP2/MCP/A2A/ACP integrations against real counterparties |

Known functional limits: the SPARQL timeout cannot kill a running worker thread; ambiguity detection is rule-based; the CNL template in the Studio cannot express "move some savings" transfers (use the CNL editor); `risk-review` clearing is a record only — the agent must resubmit.
