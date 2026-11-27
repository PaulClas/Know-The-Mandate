# KYM security review and cybersecurity-framework assessment

**Scope:** the full repository as of 2026-11-26 (backend `apps/api/kym`, web `apps/web`, infrastructure files). **Type:** self-assessment by the authors of the code, with executable regression proofs. **This is not an independent penetration test, audit or certification.** Self-review is biased toward finding what the reviewer already thought of; external review is listed as required work.

Machine-checkable evidence: `make redteam` (23 attacks, 3 designs), `tests/security/`, `tests/integration/`. Generated results: [docs/redteam/latest.md](../redteam/latest.md).

## 1. Method

1. Read every endpoint and trust boundary against the STRIDE model in [threat-model.md](../threat-model/threat-model.md).
2. Map the implementation to OWASP API Security Top 10 (2023), NIST CSF 2.0 functions and agent-specific risks.
3. Attack it: each suspected weakness got a reproducing test *before* the fix, then a regression test after (`redteam.py`).
4. Record what was **fixed**, what is **accepted** and what is **open**. Nothing is hidden by wording.

Framework sources checked on 2026-11-26 against the official publications: OWASP API Security Top 10 2023 (category names, api-security.owasp.org); OWASP Top 10 for LLM Applications 2025 (LLM01-LLM10 names, genai.owasp.org/llm-top-10); OWASP Top 10 for Agentic Applications 2026 (ASI01-ASI10 names, genai.owasp.org/top-10-for-agentic-applications-2026); NIST CSF 2.0 categories `PR.AA` (Identity Management, Authentication, and Access Control; `PR.AA-05` covers access permissions and authorizations defined in policy, managed, enforced and reviewed) and `DE.CM` (Continuous Monitoring), read from NIST's published CSF 2.0 reference data. Only names and identifiers were checked; the *mapping* of KYM behaviour to each item is the authors' indicative judgement, not an assessment by OWASP or NIST.

## 2. Findings register

Severity is the authors' judgement *in a deployed setting*, not in the local demo. "Fixed" means a regression test exists.

### Fixed during this review

| ID | Finding | Sev. | Fix | Proof |
|---|---|---|---|---|
| F-01 | **Evidence verifier trusted public keys embedded in the package.** A forger who re-signs every event with their own key and swaps the embedded key passed verification. `POST /api/evidence/verify` was exposed to this. | High | `verify_package(trusted_keys=…)`; endpoint pins the bank's key registry; report states `key_trust`; CLI `kym verify-package --keys`. | `redteam: forged_evidence_package` (unpinned verifier is fooled, pinned is not) |
| F-02 | **Unauthenticated ledger flooding.** Every request with a bad token appended a signed `TOKEN_REJECTED` event and held the write lock. | High | Per-IP rate limit; global cap on rejection events (excess counted in metrics, not written). | `redteam: unauth_flood` (300 junk requests → ≤ 60 events, ledger intact) |
| F-03 | **scrypt client authentication ran inside the global write lock**, so unauthenticated bad credentials stalled all writers. | High | Authenticate in a read context first; failed-auth lockout. | `redteam: client_auth_bruteforce` |
| F-04 | **SPARQL timeout could not kill the worker thread.** A hostile aggregate query could saturate the pool (DoS). | Med | Queries run in a child process with `RLIMIT_CPU`/`RLIMIT_AS`, killed on timeout. | `redteam: sparql_dos` |
| F-05 | **Path traversal:** `agent_id` became part of a key file name. | Med | Strict `^agent_[a-z0-9_]{2,60}$` validation at the sink and the API. | `redteam: path_traversal` |
| F-06 | **Constant session-signing secret** shipped in source and Compose → anyone could forge an admin session if the API was reachable. | High (if exposed) | Random per-install secret in `keys/session-secret`; legacy constant rejected. | `redteam: session_forgery` |
| F-07 | **No fail-closed switch** for no-password sessions and destructive reset. | Med | `KYM_ENV` (default `demo`); any other value disables login, API sessions, reset and red-team runs. | `redteam: production_fail_closed` |
| F-08 | No rate limiting or lockout on OAuth/bank endpoints. | Med | Sliding-window limiter, failed-auth lockout (`429`). | `test_rate_limit_applies…` |
| F-09 | No security headers or body-size cap. | Low | `nosniff`, `X-Frame-Options`, CSP `default-src 'none'`, `no-store`, 1 MB body cap. | `test_security_headers_and_body_limit` |
| F-10 | Unvalidated identifiers flowed into RDF IRIs (graph/serialization injection). | Low–Med | `ID_RE` validation on resources, beneficiaries, merchants, accounts. | schema tests |
| F-11 | Oversized or float amounts could overflow the database layer (500). | Low | `MAX_MINOR = 10^15`, integer-only validation. | `redteam: malformed_input` |
| F-12 | Non-object JSON bodies caused 500s. | Low | `_json_obj` validation, MCP adapter guards. | `redteam: malformed_input` |
| F-13 | DPoP replay cache grew without bound. | Low–Med | Entries older than 300 s deleted on insert. | code + DPoP tests |
| F-14 | Transfer to the same account, or to a destination in a different currency, was accepted (integrity). | Med | Rejected at normalization; engine refuses currency-mismatched or closed destination. | engine path |
| F-15 | Unbounded idempotency-key length. | Low | 1–128 characters. | gateway |

### Accepted or open (not fixed in this repository)

| ID | Item | Why it matters | Needed |
|---|---|---|---|
| O-01 | **Demo sessions have no authentication.** Anyone who can reach the API can act as admin. | Critical if exposed. Default bind is loopback/Compose localhost. | OIDC + passkeys; never run `KYM_ENV=demo` on a reachable host. |
| O-02 | Keys, agent private keys and agent client secrets are plaintext files; the "agent" runs inside the server process for the demo. | Host compromise = total compromise; agents are not independent. | HSM/KMS; real agents hold their own keys (SPIFFE/SPIRE, hardware-backed). |
| O-03 | One global write lock serializes all mutations. | Throughput ceiling; a slow transaction delays everyone; authenticated agents can still consume capacity. | Row-level locking / serializable isolation, per-tenant limits. |
| O-04 | **No maker–checker for bank operators.** One admin can suspend agents, reverse payments, clear risk reviews. | Insider risk. | Dual control, privileged-access management, signed operator actions. |
| O-05 | A business mandate can be approved by a **single** signatory (only *payments* can require two). | Weaker than typical corporate-authority rules. | Mandate-level multi-signatory policy. |
| O-06 | No server-issued DPoP nonces (RFC 9449 §8). | Proofs can be pre-generated within the 60 s `iat` window. | Nonce challenge. |
| O-07 | Ledger is tamper-**evident**: whoever replaces DB **and** keys **and** exported checkpoints can rewrite history. | Core limitation of any self-hosted log. | WORM, RFC 3161 timestamps, external witnesses, Merkle log. |
| O-08 | Decision snapshots store customer/mandate data in the database; only event payloads are erasable. | Privacy-law retention vs. erasure tension. | Snapshot minimisation and key-based erasure. |
| O-09 | SPARQL over the registry graph gives admins/investigators all rows (no row-level authorization). | Over-broad internal access. | Per-case scoped graphs. |
| O-10 | Rate limiter is in-process and ignores `X-Forwarded-For`. Behind a proxy, all clients share one bucket. | Mis-sized limits; trivial self-DoS or bypass depending on topology. | Edge/WAF limiter and trusted-proxy configuration. |
| O-11 | Rejection-event sampling (F-02) means a burst's individual rejections are only counted. | Forensic detail lost under attack. | Separate high-volume security log with independent retention. |
| O-12 | Risk engine and ambiguity detector are simple and rule-based; the trust score is gameable. | False negatives; adaptive attackers. | Governed models, red-team the models. |
| O-13 | Dependencies are version-pinned, not hash-locked; no SBOM or vulnerability scanning. | Supply-chain exposure (a listed threat). | Hash-locking, SBOM, SCA, signed releases. |
| O-14 | UI keeps the session token in `localStorage`; the web app sets no CSP. | An XSS would exfiltrate admin sessions. (React escapes output; the only `dangerouslySetInnerHTML` is a constant theme script.) | HttpOnly cookies + CSRF protection + CSP. |
| O-15 | **Denial responses reveal policy structure** (limits, allowed-beneficiary checks) to the calling agent. | An adaptive agent can map limits by probing. | A terse mode for agent-facing errors; detailed reasons only to the bank/customer. |
| O-16 | Gateway, PDP, risk engine and payment engine share one process and trust domain. | A single code-execution bug defeats separation of duties. | Separate processes with mutual authentication; signed decisions already make this possible. |
| O-17 | Decision replay proves the *engine is deterministic* over the stored snapshot, not that the snapshot was complete or honest when built. | A compromised gateway could build misleading inputs. | Independent input attestations; sampling replay by a second implementation. |
| O-18 | **"What you see is what you sign":** the consent summary is generated by the bank; its digest is recorded, but an incorrect or deceptive generator would mislead the customer. | Central to the thesis; the approval is only as good as the rendering. | Independent summary verification, accessibility and usability studies. |
| O-19 | Admin reads of evidence are not themselves logged. | Insider snooping undetected. | Access logging into a separate ledger. |
| O-20 | Time-window logic (day/month in IANA zones) has limited tests around DST and month boundaries. | Budget miscounts at boundaries. | Property tests over zone transitions. |
| O-21 | No external penetration test, no fuzzing campaign, no formal verification, no real-world pilot. | Unknown unknowns. | All of the above. |

## 3. OWASP API Security Top 10 (2023) mapping

| Risk | KYM status |
|---|---|
| API1 Broken Object Level Authorization | Customer-scoped checks on mandates, transactions, evidence, ledger events (`auth.assert_can_act_for`); test `cross_customer`. Residual: O-09. |
| API2 Broken Authentication | Agent side: confidential clients (scrypt), DPoP, PKCE, short-lived tokens, lockout. Human side: **demo-only, no authentication (O-01)**. |
| API3 Broken Object Property Level Authorization | Response models are hand-built views; `declared` agent metadata can't set `status`; extra mandate fields are rejected (`extra="forbid"`). No generic mass assignment paths found. |
| API4 Unrestricted Resource Consumption | Rate limits, body cap, SPARQL sandbox, ledger-event cap, bounded DPoP cache, `limit` caps. Residual: O-03, O-10. |
| API5 Broken Function Level Authorization | Role dependencies per route (`require_role`); tests assert customers cannot call admin routes and admins cannot approve. Residual: O-04. |
| API6 Unrestricted Access to Sensitive Business Flows | This is KYM's subject: budgets, approvals, idempotency, concurrency tests. |
| API7 SSRF | No server-side fetching of user-supplied URLs; SPARQL `SERVICE`/`FROM` blocked. |
| API8 Security Misconfiguration | Headers, fail-closed `KYM_ENV`, no default secrets, CORS limited to localhost origins. Residual: O-14. |
| API9 Improper Inventory Management | OpenAPI is generated and committed (`docs/specifications/openapi.json`); sandbox, playground and red-team endpoints are labelled and demo-gated. |
| API10 Unsafe Consumption of APIs | No third-party API is consumed. MCP/AP2 adapters are sandbox/mapping only. |

## 4. NIST CSF 2.0 function view (authors' mapping, not an attestation)

| Function | Present | Gaps |
|---|---|---|
| Govern | Documented invariants (`AGENTS.md`), ADRs, risk register, honest labelling | No governance process, no owners, no policy change control |
| Identify | Threat model, agent registry, asset/trust-boundary diagrams | No asset inventory beyond the repo |
| Protect | Deny-by-default PDP, DPoP, scoped access, validation, headers, rate limits | Plaintext keys, no real authentication, O-04/O-16 |
| Detect | Signed evidence ledger, verification endpoint, decision replay, metrics | No alerting, no anomaly detection on operators (O-19) |
| Respond | Revocation with cascade, agent suspension, pending-operation cancellation, dispute reconstruction | No incident-response runbooks or case management |
| Recover | Reproducible seed/reset, migrations | No backup/restore, DR, or tested recovery of the ledger |

## 5. Agent-specific risk view

| Risk | How KYM treats it |
|---|---|
| Prompt injection / excessive agency (OWASP LLM01/LLM06 in the 2025 list) | Capability is bounded by the mandate; injected content cannot widen it (`prompt_injection` proof). It cannot stop injected requests that stay **inside** the mandate (`in_mandate_malicious`). |
| Confused deputy / token sharing | Actor binding (`act`), DPoP key binding, per-request mandate lookup. |
| Compromised agent runtime | Blast radius = the mandate (amounts, beneficiaries, budget, expiry) plus approvals. The agent's own key can still be used by the attacker within those bounds. |
| Non-human-identity sprawl | Registry with status/attestation; no expiry/recertification (open). |
| Malicious tool output / supply chain | Tool outputs are data; no bank decision depends on them. Dependency risks: O-13. |

## 6. Verdict

KYM's **core design claim**, that authority can be represented, evaluated per request, revoked and evidenced independently of tokens, is supported by the executable proofs. Its **implementation** is a well-tested prototype with real vulnerabilities found and fixed in this pass, and a long list of production gaps above. The honest summary: *the architecture is sound enough to be worth external review; the code is not ready to guard money.*
