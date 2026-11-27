# KYM frequently asked questions

Answers lead with the direct answer. Last reviewed 2026-11-26. KYM is an experimental, synthetic-data proof of concept; nothing here is legal or compliance advice.

## What is KYM?
**KYM (Know Your Mandate) is an experimental framework that lets a bank represent, enforce and prove the financial authority a customer has delegated to an AI agent.** The customer's authority is captured as a *mandate*: who may act, on which accounts, for what purpose, with which limits and expiry, whether it can be delegated, and which actions need a human. A deterministic policy engine checks the mandate on every request, and a signed evidence ledger records what happened.

## What problem does KYM solve?
**It closes the gap between "this client holds a valid token" and "the customer actually authorized this specific action".** KYC identifies the customer, authentication verifies the caller, OAuth grants API access, KYA identifies the agent, KYT scores transactions. None records the delegated authority itself. Without it, a bank cannot easily answer who authorized what, within which limits, and whether those limits were honoured.

## How is KYM different from OAuth and OAuth Rich Authorization Requests (RAR)?
**OAuth/RAR is the carrier; KYM supplies the state and the decision.** RAR (RFC 9396) can express account, beneficiary and maximum amount inside a token, and KYM uses it. But a static grant cannot track cumulative budgets, instant mandate revocation, single-use approvals or delegation lineage. In KYM's red-team comparison, a design with scopes plus static RAR stopped 3 of 10 applicable attacks; KYM blocked 22 of 22 applicable attacks (and documents one it cannot stop). See [philosophy](philosophy/README.md#1-oauth-with-rich-authorization-requests-already-does-this).

## Does a valid access token authorize a payment in KYM?
**No.** A valid token is only technical permission. Scenario C demonstrates it: the token passes OAuth verification (including `payments.initiate`), the mandate does not permit the beneficiary, and the payment is denied.

## Can KYM stop an AI agent from making mistakes or being prompt-injected?
**It limits the damage; it does not prevent the mistake.** Anything outside the mandate is denied no matter why the agent asked (hallucination, injection, compromise). Anything *inside* the mandate is allowed, and mandate enforcement cannot tell a wrong-but-permitted payment from a right one. This is the documented honest gap (`in_mandate_malicious`).

## Is KYM a standard? Is it compliant or certified?
**No.** The vocabulary (`https://example.org/kym/v1#`), the controlled language (KYM-CNL), the `kym_financial_mandate` authorization-details type and the `https://example.org/kym/*` token claims are experimental proposals. The demo claims no compliance, certification or conformance with any law or standard.

## Which standards does it use, and which are only mapped?
**Implemented in a sandbox using maintained libraries:** JWT/JWS (ES256), PKCE, RFC 9396 RAR validation, RFC 9449 DPoP proof validation, introspection, revocation, RFC 8785 canonical JSON, RDF/JSON-LD, SHACL, SPARQL, Ed25519 signatures. **Simplified/simulated:** PAR, token exchange, OIDC, customer authentication, attestation, KYC/KYT/sanctions. **Mapped only:** mTLS, FAPI 2.0, FDX, AP2, Visa/Mastercard, ACP, x402, A2A, SPIFFE/SPIRE, OPA/Cedar. No interoperability has been tested. Details: [standards matrix](research/standards-mapping.md).

## How does KYM relate to Google's AP2, MCP and A2A?
**They are complementary layers, not substitutes.** AP2 concerns agent-driven commerce artifacts (user-approved mandates, checkout and payment proofs); KYM adds the bank-side authority decision and evidence. MCP and A2A are transport/discovery protocols: tool discovery is not permission, and every MCP-shaped call in KYM still passes the same enforcement point. AP2 mapping is conceptual only: [ap2-mapping.md](research/ap2-mapping.md).

## Why not just use Open Policy Agent (OPA) or Cedar?
**You can; KYM chose a typed Python engine for determinism, explanation and replay in one language.** The decision is a pure function of a stored JSON snapshot, which makes every historical decision replayable. OPA/Cedar are valid production choices; the snapshot format is the integration seam ([ADR-0002](adr/0002-deterministic-pdp-no-opa.md)).

## Is the ontology used to make authorization decisions?
**No.** OWL reasoning is open-world; money needs deny-by-default. The ontology and SHACL validate mandates when they are created and support explanation and SPARQL queries. The runtime decision uses a compiled policy ([ADR-0003](adr/0003-ontology-not-in-the-decision-path.md)).

## How does revocation work?
**The mandate's lifecycle state is checked on every request, independent of the token.** Revoking a mandate immediately denies later requests even with an unexpired token, cascades to delegated child mandates, and cancels pending approvals and reservations. It does not reverse payments already executed.

## What is the evidence ledger, and is it a blockchain?
**It is a signed, hash-chained, append-only event log with signed checkpoints; it is not a blockchain.** Events use RFC 8785 canonical JSON, SHA-256 and Ed25519. It is tamper-*evident*: someone who replaces the database, the signing keys and exported checkpoints can rewrite history. Production alternatives: HSM, WORM storage, RFC 3161 timestamps, external witnesses.

## Does KYM decide who is legally liable?
**No.** It attributes who did what and which party controlled which system. It distinguishes factual responsibility, contractual responsibility, potential legal liability and final adjudicated liability, and decides none of the last three. A valid signature shows integrity and key control, not legally effective consent.

## Is it ready for production?
**No.** See the [production readiness gap analysis](specifications/production-readiness-gap-analysis.md), the [security review](security/security-review.md) (15 findings fixed, 21 open or accepted) and the [risk register](risk/risk-register.md). Key gaps: no real authentication, plaintext keys, single-process locking, no external audit, sandbox OAuth.

## What are the biggest risks of KYM?
**Approval fatigue, customers misreading mandates, overly broad mandates, coverage gaps when payments bypass the bank, in-mandate harm, insider abuse, and standards absorbing the idea.** Full list with likelihood and impact: [risk register](risk/risk-register.md).

## When should I not use KYM?
**When agents only read data, when a single static per-transaction cap suffices, or when you cannot run a highly available enforcement point.** See [risk register §E](risk/risk-register.md#e-when-you-should-not-use-kym).

## How can I verify the claims myself?
**Run `make redteam`.** It executes 23 attacks against three designs with the same real token and writes [docs/redteam/latest.md](redteam/latest.md). Also `make test` (208 tests incl. property-based), `make scenarios` (13 demonstration scenarios A–M), and `make verify-ledger`.

## How do I run it?
`make install && make install-web && make demo`; API docs at http://127.0.0.1:8000/docs, UI at http://localhost:3000. Demo users and details: [README](../README.md#run-it).
