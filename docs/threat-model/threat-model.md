# KYM threat model (STRIDE)

**Scope.** KYM (Know Your Mandate) is a proof-of-concept in which a fictional bank, Meridian Bank, governs financial authority delegated to AI agents. All data is synthetic. This model is a design analysis, not a security assessment or certification; no penetration test has been performed. Mitigation status tags (**[implemented]**, **[not implemented]**, **[partially implemented]**) were reconciled against the code; the automated tests under `tests/security` and `tests/integration` exercise the implemented ones.

## 1. Design under analysis

- **Decision point.** A deny-by-default policy decision point (PDP) allows an operation only if it falls inside the **intersection** of: customer authority, agent capabilities, OAuth grant, mandate, parent mandate, bank policy and risk.
- **Payment engine.** Accepts only a **server-signed, short-lived decision bound to the exact operation hash**.
- **Revocation.** Checked on **every request**, regardless of token validity.
- **Approvals.** Bound to the **SHA-256 of the canonical transaction payload** (RFC 8785 JCS) and **single use**.
- **Budgets.** **Atomic reservations inside database transactions**.
- **Evidence.** **Ed25519-signed, hash-chained ledger** with signed checkpoints.
- **Tokens.** Sandbox authorization server issues JWT access tokens (RFC 9068-style claims), validates RAR `authorization_details`, PKCE, DPoP (`cnf.jkt`; `htm`/`htu`/`iat`/`ath`/`jti`), audience, revocation and introspection. See [standards mapping](../research/standards-mapping.md).

**Trust boundaries.** (1) Customer <-> bank channel (simulated authenticated session); (2) agent runtime <-> bank APIs (untrusted caller); (3) agent <-> tools/other agents (untrusted content); (4) PDP <-> payment engine (signed decision); (5) services <-> ledger/database; (6) build/dependency supply chain.

**STRIDE key.** S = Spoofing, T = Tampering, R = Repudiation, I = Information disclosure, D = Denial of service, E = Elevation of privilege.

**External references (indicative mappings, item names read from the official pages on 2026-11-26).**
OWASP Top 10 for Agentic Applications 2026 (https://genai.owasp.org/top-10-for-agentic-applications-2026/): ASI01 Agent Goal Hijack, ASI02 Tool Misuse and Exploitation, ASI03 Identity and Privilege Abuse, ASI04 Agentic Supply Chain Vulnerabilities, ASI07 Insecure Inter-Agent Communication, ASI08 Cascading Failures, ASI09 Human-Agent Trust Exploitation, ASI10 Rogue Agents.
OWASP Top 10 for LLM Applications, 2025 edition names (https://genai.owasp.org/llm-top-10/): LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM03 Supply Chain, LLM05 Improper Output Handling, LLM06 Excessive Agency.
OWASP API Security Top 10 2023 (https://owasp.org/API-Security/editions/2023/en/0x11-t10/): API1 Broken Object Level Authorization, API2 Broken Authentication, API5 Broken Function Level Authorization, API6 Unrestricted Access to Sensitive Business Flows, API9 Improper Inventory Management.

## 2. Summary table

| # | Threat | STRIDE | Residual risk |
|---|---|---|---|
| T01 | Credential theft | S, I | Medium |
| T02 | Token replay | S, T | Low-Medium |
| T03 | Agent impersonation | S | Medium |
| T04 | Confused deputy | E | Medium |
| T05 | Unauthorized resource access | I, E | Medium |
| T06 | Excessive OAuth permissions | E | Medium |
| T07 | Mandate substitution | T | Low-Medium |
| T08 | Privilege escalation | E | Medium |
| T09 | Delegation escalation | E | Medium |
| T10 | Prompt injection | T, E | High (bounded by limits) |
| T11 | Malicious tool output | T, E | Medium-High |
| T12 | Compromised agent runtime | S, T, E | High (bounded by limits) |
| T13 | Revoked mandate reuse | E | Low-Medium |
| T14 | Approval replay | S, R | Low-Medium |
| T15 | Transaction substitution | T | Low-Medium |
| T16 | Concurrent limit bypass | T, E | Low-Medium |
| T17 | Ledger tampering | T, R | Medium (demo) |
| T18 | Evidence disclosure | I | Medium |
| T19 | Non-human identity sprawl | E, R | Medium |
| T20 | Cross-tenant access | I, E | Medium |
| T21 | Policy downgrade | T, E | Medium |
| T22 | Stale policy evaluation | T | Low-Medium |
| T23 | Supply-chain compromise | T, E | Medium-High |

Residual ratings are qualitative judgments by the KYM authors for the demo design, not measured values.

## 3. Threats

### T01 Credential theft
- **STRIDE:** Spoofing, Information disclosure.
- **Attack:** An attacker steals an access token, refresh token or client credential (log leak, memory dump, network capture) and presents it to bank APIs.
- **KYM mitigation:** Access tokens are sender-constrained with DPoP (`cnf.jkt`), so a stolen token is unusable without the proof key. Tokens are short-lived. A token alone cannot move money: the payment engine requires a separate signed decision bound to the operation hash, and the PDP re-evaluates mandate state and revocation on every request. Token revocation (RFC 7009) is available.
- **Residual risk:** Theft of the DPoP private key together with the token (e.g. from a compromised runtime, see T12). Demo keys are stored in local files and there is no HSM. Data-access tokens can still expose data within granted scopes until revoked.

### T02 Token replay
- **STRIDE:** Spoofing, Tampering.
- **Attack:** Captured requests, DPoP proofs or decisions are replayed.
- **KYM mitigation:** DPoP proof validation checks `htm`, `htu`, `iat` and `ath` and detects `jti` replay. Decisions are short-lived and bound to the exact operation hash, so a replayed decision cannot authorize a different operation. Approvals are single use (T14).
- **Residual risk:** Replay caches are local to a single node in the demo (SQLite); distributed deployments need shared replay state. Clock-skew windows allow limited replay. TLS is assumed; no mTLS in the demo.

### T03 Agent impersonation
- **STRIDE:** Spoofing.
- **Attack:** A malicious process claims to be a registered agent or reuses another agent's identity.
- **KYM mitigation:** Agent identity is established by the token subject/actor claims and bound to the agent's proof key through `cnf.jkt`. The PDP intersects the agent's registered capabilities with the request, so an impersonator gains only what the impersonated agent's mandate allows. Token exchange (simulated) records the actor via the `act` claim.
- **Residual risk:** Agent identities in the demo are issued by a sandbox, not attested by a platform. If an agent's key is stolen the attacker is that agent until revoked. Production should use attested workload identity (see section 5).

### T04 Confused deputy
- **STRIDE:** Elevation of privilege.
- **Attack:** An agent or tool is tricked into using its own, broader authority on behalf of an unprivileged requester, or a token intended for one resource server is accepted by another.
- **KYM mitigation:** The audience (`aud`) check restricts tokens to their intended resource (RFC 8707-style). The PDP always evaluates the *combination* of customer, agent and mandate, never a single ambient permission. Operations are bound to a specific mandate and customer. Maps indicatively to OWASP ASI03 Identity and Privilege Abuse and API5 Broken Function Level Authorization.
- **Residual risk:** Tools or services running with ambient authority outside KYM; misconfigured audiences. Only the audience check is implemented, not full resource-indicator negotiation.

### T05 Unauthorized resource access
- **STRIDE:** Information disclosure, Elevation of privilege.
- **Attack:** An agent reads or acts on accounts, objects or functions outside its grant (object-level or function-level authorization failures).
- **KYM mitigation:** Deny-by-default PDP; per-resource and per-function checks against mandate scope; data-access scopes are separate from payment authority (a data-access token cannot authorize a payment); responses are limited to permitted fields (data minimization). Maps to API1 Broken Object Level Authorization and API5.
- **Residual risk:** Authorization logic bugs; incomplete test coverage; field-level filtering errors. No independent review.

### T06 Excessive OAuth permissions
- **STRIDE:** Elevation of privilege.
- **Attack:** An agent is granted a broad OAuth scope or `authorization_details` and uses it beyond the customer's intent.
- **KYM mitigation:** RAR (`authorization_details`, including the experimental `kym_financial_mandate` type) is validated against a narrow schema. The OAuth grant is only one input to the intersection; even a broad token cannot exceed the mandate, agent capabilities or bank policy. Maps to LLM06 Excessive Agency and ASI03.
- **Residual risk:** Customers may approve over-broad mandates (consent fatigue); validation gaps in new RAR types.

### T07 Mandate substitution
- **STRIDE:** Tampering.
- **Attack:** An attacker swaps or edits the mandate referenced by a token or approval (e.g. substituting a higher-limit mandate).
- **KYM mitigation:** Mandates are canonicalized (RFC 8785) and digested with a cryptographic hash; the token and decision reference the mandate identity and digest; **[implemented]** mandate changes create a new immutable version recorded in the ledger (`MANDATE_AMENDED`); content is never edited in place. The PDP loads the mandate from the bank's store, not from the caller's input.
- **Residual risk:** Insider or key-compromise scenarios where the bank store is altered (see T17, T21); no external witness of mandate versions.

### T08 Privilege escalation
- **STRIDE:** Elevation of privilege.
- **Attack:** A low-privilege principal (agent, operator or customer role) obtains administrative or higher authority.
- **KYM mitigation:** Deny-by-default; distinct roles for customer, agent, operator and bank administrator; policy changes are evidence events. **[not implemented]** Separation of duties for policy edits: the demo policy is a versioned JSON file in the repository (`policies/bank-policy-1.0.0.json`).
- **Residual risk:** Insider/administrator abuse; the demo has no dual control, HSM-protected signing, or independent administration plane.

### T09 Delegation escalation
- **STRIDE:** Elevation of privilege.
- **Attack:** A sub-agent or delegated agent obtains more authority than its delegator.
- **KYM mitigation:** The parent mandate is one of the PDP intersection inputs, so a child can never exceed its parent. Delegation is recorded with the `act` claim (simulated token exchange). This is a technical rule; it parallels, but does not establish, the substitution/delegation concepts in Civil Code of Québec arts. 2140-2142 (see [regulatory mapping](../regulatory-mapping/README.md)).
- **Residual risk:** Token exchange is a simulated adapter; deep or cyclic chains; legal characterization of sub-agents is unresolved.

### T10 Prompt injection
- **STRIDE:** Tampering, Elevation of privilege.
- **Attack:** Untrusted content (web page, email, document, tool result) manipulates the agent into issuing harmful requests (OWASP LLM01 Prompt Injection; ASI01 Agent Goal Hijack).
- **KYM mitigation:** The agent is treated as an untrusted caller. Authorization is enforced by deterministic code outside the model, so injected instructions cannot widen authority; the worst case is bounded by mandate limits (amount, payee, window, budget). Approvals show and bind the exact payload so a human can reject unexpected operations. KYM's restricted tool interface sandbox follows "discovery is not permission".
- **Residual risk:** A hijacked agent can still perform harmful actions that remain inside its mandate (e.g. paying an allowed payee the maximum amount). Human-approval fatigue (ASI09 Human-Agent Trust Exploitation). KYM does not detect injections.

### T11 Malicious tool output
- **STRIDE:** Tampering, Elevation of privilege.
- **Attack:** A tool or upstream API returns crafted data (payee details, instructions, fake confirmations) that steers the agent or poisons records (LLM05 Improper Output Handling; ASI02 Tool Misuse and Exploitation).
- **KYM mitigation:** Tool outputs are treated as data, never as authority; the PDP decision does not depend on tool-provided claims and the operation hash is computed from the exact payload the bank will execute. **[not implemented]** Schema validation of tool results on the agent side (outside the bank's control).
- **Residual risk:** Agent behaviour can still be influenced, e.g. selection among allowed payees. The restricted tool interface sandbox is not tested against real MCP clients or servers.

### T12 Compromised agent runtime
- **STRIDE:** Spoofing, Tampering, Elevation of privilege.
- **Attack:** An attacker controls the agent's process, memory, keys and tokens (ASI10 Rogue Agents).
- **KYM mitigation:** Blast radius is bounded: sender-constrained tokens work only with the key (which the attacker now has), but mandate limits, per-operation decisions, approvals for higher-risk operations, budget caps, risk checks and instant revocation still apply. All operations are recorded in the ledger for investigation.
- **Residual risk:** The attacker can spend up to the mandate limits until detection and revocation. Detection is limited to simulated risk checks. High.

### T13 Revoked mandate reuse
- **STRIDE:** Elevation of privilege.
- **Attack:** An agent keeps using authority after the customer revoked the mandate (valid token, cached approval).
- **KYM mitigation:** Revocation is checked on **every request** regardless of token validity, and in the same transaction as the budget reservation. Revoked mandates cannot produce decisions; **[implemented]** pending approvals, risk reviews and reservations tied to the mandate are cancelled on revocation (`bank.cancel_pending`).
- **Residual risk:** Requests in flight at the instant of revocation; in a distributed deployment, replica lag. Third parties that rely on the agent are not notified automatically (compare Civil Code of Québec art. 2181 on third parties unaware of revocation; legal effect not analysed).

### T14 Approval replay
- **STRIDE:** Spoofing, Repudiation.
- **Attack:** A prior customer approval is reused for another transaction or a second time.
- **KYM mitigation:** Approvals are bound to the **SHA-256 of the canonical transaction payload** and are **single use** with an expiry; consumption is recorded atomically.
- **Residual risk:** The demo authenticates the approver with a simulated bank session rather than passkeys/WebAuthn, so approval authenticity is not strongly attested. UI spoofing of approval content.

### T15 Transaction substitution
- **STRIDE:** Tampering.
- **Attack:** The payload is altered between approval/decision and execution (payee, amount, account, currency).
- **KYM mitigation:** The signed decision is bound to the exact operation hash; the payment engine recomputes the hash of what it is about to execute and rejects any mismatch. Canonical JSON (RFC 8785) avoids representation ambiguity.
- **Residual risk:** Fields omitted from the canonical payload would escape protection; canonicalization or schema bugs; requires thorough tests of the field set.

### T16 Concurrent limit bypass
- **STRIDE:** Tampering, Elevation of privilege.
- **Attack:** Many parallel requests race the budget or velocity check so that total spend exceeds the limit (compare "double spend" in AP2's security considerations).
- **KYM mitigation:** **Atomic budget reservations inside database transactions**; the decision is issued only after a successful reservation; reservations are released or consumed on outcome.
- **Residual risk:** SQLite serializes writers in the demo; horizontal scaling requires serializable transactions or an external lock; reservation expiry/cleanup races; distributed budgets across systems.

### T17 Ledger tampering
- **STRIDE:** Tampering, Repudiation.
- **Attack:** An attacker (or insider) edits, deletes or reorders evidence to hide actions or deny responsibility.
- **KYM mitigation:** Ed25519-signed entries linked in a hash chain, with signed checkpoints; verification detects modification, reordering and mid-chain deletion.
- **Residual risk:** Signing keys are demo keys in local files; anyone holding the key can rewrite history and re-sign. Tail truncation after the last checkpoint is undetectable without an external witness. No WORM storage, RFC 3161 timestamps or transparency log (section 6).

### T18 Evidence disclosure
- **STRIDE:** Information disclosure.
- **Attack:** Evidence or ledger exports leak customer or transaction details (LLM02 Sensitive Information Disclosure).
- **KYM mitigation:** **[implemented]** event payloads live in a protected store that can be erased without breaking the chain; the chain commits only to digests; evidence views are role- and customer-scoped; reusable tokens are never stored; **[limitation]** payloads still contain synthetic transaction detail; synthetic data only in the demo. Hashes of low-entropy fields can be guessed, a concern AP2's privacy section also raises for checkout hashes.
- **Residual risk:** No encryption at rest, field-level redaction or key separation in the demo; retention and deletion obligations (privacy law) are not implemented.

### T19 Non-human identity sprawl
- **STRIDE:** Elevation of privilege, Repudiation.
- **Attack:** Many forgotten agent identities, keys and mandates accumulate, widening the attack surface and obscuring accountability (API9 Improper Inventory Management).
- **KYM mitigation:** **[implemented]** Agent registry with an owner, status and attestation checks; **[not implemented]** agent registration expiry/recertification; mandates are time-limited and revocable; inventory views for review.
- **Residual risk:** The registry only knows registered agents; no discovery of shadow agents; demo has no lifecycle automation. See enterprise identity options in section 5.

### T20 Cross-tenant access
- **STRIDE:** Information disclosure, Elevation of privilege.
- **Attack:** One customer's or operator's agent accesses another tenant's accounts, mandates or evidence (API1 Broken Object Level Authorization).
- **KYM mitigation:** Customer authority is an input to the intersection, so the PDP denies operations on resources not owned by the mandating customer. **[implemented]** customer scoping on mandate, transaction, evidence and ledger endpoints (covered by tests); **[not implemented]** database-level row security.
- **Residual risk:** The demo uses a single SQLite database and is not hardened for multi-tenancy; no tenant-level encryption or isolation testing.

### T21 Policy downgrade
- **STRIDE:** Tampering, Elevation of privilege.
- **Attack:** An attacker or misconfiguration swaps in an older or weaker policy set, or disables a rule, so risky operations pass.
- **KYM mitigation:** Policy changes are recorded as evidence events; **[implemented]** every decision stores the policy version and the full policy snapshot used, so it can be replayed; **[not implemented]** a policy-version floor in the payment engine.
- **Residual risk:** Administrators with key access can still change policy; no four-eyes approval or external audit of policy changes in the demo.

### T22 Stale policy evaluation
- **STRIDE:** Tampering.
- **Attack:** A decision is made on out-of-date policy, mandate or revocation state (cache, long-lived decision).
- **KYM mitigation:** Decisions are short-lived and bound to the operation hash; mandate and revocation state are read at decision time in the same transaction as the budget reservation; the payment engine verifies the signature and expiry at execution.
- **Residual risk:** The decision TTL window (a revocation or policy change between decision and execution); caching layers added later.

### T23 Supply-chain compromise
- **STRIDE:** Tampering, Elevation of privilege.
- **Attack:** A compromised dependency or build tool (JWT, canonicalization, RDF/SHACL libraries, UI packages) undermines verification or exfiltrates keys (OWASP ASI04 Agentic Supply Chain Vulnerabilities; LLM03 Supply Chain).
- **KYM mitigation:** Small set of well-known libraries (e.g. PyJWT, rfc8785, rdflib, pySHACL). **[partially implemented]** dependency versions are pinned in `pyproject.toml`; **[not implemented]** hash-locking, SBOM, vulnerability scanning, signed releases.
- **Residual risk:** Compromise of a cryptographic or JWT library defeats most controls. The demo has no supply-chain attestation.

## 4. Demo-only security limitations

These are deliberate simplifications of the proof-of-concept and must not be carried into any real deployment:

- **Demo keys in local files** (token signing, decision signing, ledger signing). No HSM or managed key service.
- **Simulated bank-authenticated session** instead of passkeys/WebAuthn for customer authentication and approval.
- **SQLite local database**: single node, no replication, no encryption at rest, limited concurrency.
- **No mTLS** between components or to external parties.
- **Simulated KYC, KYT and sanctions screening** using synthetic data. This is **not real AML/CFT**; no reports are filed.
- Sandbox authorization server: not a certified OAuth/OpenID/FAPI server; no interoperability testing.
- No rate limiting, DoS protection or abuse monitoring beyond demonstration checks (the Denial-of-service category is therefore largely out of scope of this document).
- All data is synthetic; no real customers, money or institutions.

## 5. Enterprise identity options (production)

Replace demo agent keys with platform-attested workload identity: SPIFFE/SPIRE, cloud IAM federation (AWS STS/OIDC federation, Google Workload Identity Federation) or directory-managed agent identities (Microsoft Entra Agent ID). URLs and notes are listed in [standards mapping, section 7](../research/standards-mapping.md#7-enterprise-identity-references).

## 6. Production-hardening list

1. HSM/KMS-backed signing for tokens, decisions and ledger checkpoints, with key rotation and separation of duties.
2. WORM (write-once) storage for evidence.
3. RFC 3161 trusted timestamping of ledger checkpoints (https://www.rfc-editor.org/rfc/rfc3161).
4. Merkle-tree transparency log for the ledger (cf. RFC 6962, https://www.rfc-editor.org/rfc/rfc6962) with **external witnesses** cosigning checkpoints.
5. SPIFFE/SPIRE (or equivalent) workload identity for agents and services.
6. Passkeys/WebAuthn for customer authentication and for approval signing.
7. mTLS between services and for agent connections, with certificate-bound tokens (RFC 8705).
8. A certified FAPI 2.0 authorization server and conformance/interoperability testing.
9. Distributed, serializable budget reservation; replicated revocation state with low-latency propagation (e.g. shared signals).
10. Encryption at rest, field-level redaction and retention policies for evidence.
11. Dependency pinning, SBOM, signed builds, vulnerability management.
12. Independent penetration testing, red-teaming of prompt-injection paths and legal review of the regulatory mapping.
