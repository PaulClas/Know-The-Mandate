# KYM glossary

**Mandate.** A bank-validated, customer-approved, immutable-per-version statement of delegated financial authority: principal, mandatary (agent), purpose, permissions with constraints, prohibitions, aggregate limits, approval obligations, delegation rules, validity and jurisdictions. Lifecycle status is stored separately.

**Mandatary.** The agent (software identity) to which authority is delegated. In KYM it is not a legal person; the responsible operator is a separate legal entity.

**Principal.** The customer (individual or business) who grants the mandate and must control the resources concerned.

**Delegated authority.** What the customer actually allowed, as opposed to *identity* (who) and *technical permission* (what a token can call).

**Effective authority.** The intersection of customer authority, agent capabilities, OAuth authorization, the active mandate, every parent mandate, bank policy, risk controls and operational restrictions. It can never exceed the narrowest boundary.

**Policy Decision Point (PDP).** The pure deterministic function that returns `ALLOW`, `DENY`, `REQUIRE_HUMAN_APPROVAL` or `REFER_TO_RISK_REVIEW` with reason codes and a check-by-check trace.

**Policy Enforcement Point (PEP).** The gateway through which every financial operation passes.

**Decision certificate.** A server-signed, short-lived, single-use record of an `ALLOW` decision bound to the SHA-256 of the exact operation. The payment engine refuses to execute without it.

**Operation hash.** SHA-256 of the canonical operation (account, beneficiary, amount, currency, purpose, reference) plus mandate id/version, principal and agent. Approvals and decisions bind to it.

**Attenuation.** The rule that delegation can only narrow authority: a child mandate can never expand actions, resources, limits, beneficiaries, validity, delegation depth or geography.

**Cascading revocation.** Revoking a parent mandate makes all delegated children unusable immediately.

**Mandate-bound credential.** A DPoP-bound JWT access token that references the mandate id, version and digest, carries RFC 9396 `authorization_details` and an `act` claim for the agent.

**Rich Authorization Requests (RAR, RFC 9396).** OAuth extension for structured `authorization_details`. KYM's proposed type is `kym_financial_mandate`.

**DPoP (RFC 9449).** Sender-constraining of tokens with a proof of possession of a private key, so a stolen token cannot be replayed from elsewhere.

**KYM-CNL.** KYM Controlled Natural Language: a small controlled language (Lark grammar) inspired by the principles of ASD-STE100 that compiles deterministically into a mandate. No ASD-STE100 compliance is claimed.

**KYM Evidence Ledger.** Append-only, hash-chained, Ed25519-signed log of the exercise of authority, with signed checkpoints. Distinct from the double-entry accounting ledger, which records movement of money.

**Checkpoint.** A signed statement of the ledger head (sequence and hash) by the ledger key and an independent witness key, exported outside the database.

**Pinned keys.** Trusted public keys obtained out of band by the verifier. Verifying a package against keys embedded in the package proves only internal consistency.

**Human approval.** A bank-controlled, single-use, expiring approval bound to the exact operation hash, requiring distinct signatories when the mandate says so.

**Know Your Agent (KYA).** Registry and attestation of AI agents as non-human identities, separating agent-declared metadata from bank-verified facts.

**Know Your Transaction (KYT).** Transaction risk assessment. In KYM it is synthetic and separate from mandate authorization.

**Honest gap.** An attack or limitation KYM documents instead of hiding: payments that stay inside the mandate (`in_mandate_malicious`) and activity outside the bank (`out_of_band_action`).

**Baseline (red-team).** Deliberately simple models used for comparison: *scope-only* and *OAuth + static RAR*.

## Agent transparency terms

**Activity report.** A compact JWS signed with an agent's registered key, covering a contiguous time window and carrying the agent's hash-chained log entries. The bank reconciles it against its own records; it is never taken on trust.

**Commit-reveal.** The agent commits to a digest of its reasoning/decision log before acting; the bank can demand the reveal later. A reveal that differs from the commitment proves the log was altered; a refusal is a violation. It proves consistency, not honesty.

**Dead-man's switch.** The rule that an enrolled agent that files no valid report within its interval (plus grace) is restricted before its next decision.

