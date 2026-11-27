# Red-team results (generated; do not edit)

Generated 2026-11-27T02:09:13.181Z. Same real access token; baselines are deliberately simple models. Results are measured, not asserted.

| Attack | Category | scope-only bank | OAuth+static RAR | KYM |
|---|---|---|---|---|
| Beneficiary swap with a valid token | authorization | **SUCCEEDED** | BLOCKED | BLOCKED |
| Single payment above the per-transaction limit | authorization | **SUCCEEDED** | BLOCKED | BLOCKED |
| Many small in-limit payments drain the cumulative budget | authorization | **SUCCEEDED** | **SUCCEEDED** | BLOCKED |
| Concurrent requests race the cumulative budget | concurrency | **SUCCEEDED** | **SUCCEEDED** | BLOCKED |
| Use of a still-valid token after the mandate is revoked | lifecycle | **SUCCEEDED** | **SUCCEEDED** | BLOCKED |
| Stolen or shared bearer token replayed by another party | credential | **SUCCEEDED** | **SUCCEEDED** | BLOCKED |
| Replay of a captured DPoP proof | credential | n/a | n/a | BLOCKED |
| High-value payment without human approval | human-in-the-loop | **SUCCEEDED** | **SUCCEEDED** | BLOCKED |
| Approved CAD 180, agent submits CAD 190 | human-in-the-loop | **SUCCEEDED** | **SUCCEEDED** | BLOCKED |
| Reuse of a one-time approval | human-in-the-loop | **SUCCEEDED** | **SUCCEEDED** | BLOCKED |
| Injected document instructs a CAD 2,000 payment | agent | **SUCCEEDED** | BLOCKED | BLOCKED |
| HONEST CASE: malicious or mistaken payment that stays inside the mandate (honest case) | limitation | **SUCCEEDED** | **SUCCEEDED** | **SUCCEEDED** |
| Parent agent delegates more authority than it holds | delegation | n/a | n/a | BLOCKED |
| Edit, rehash, delete or alter evidence after the fact | evidence | n/a | n/a | BLOCKED |
| Forged evidence package signed with attacker keys | evidence | n/a | n/a | BLOCKED |
| Hostile SPARQL query (cartesian explosion) | availability | n/a | n/a | BLOCKED |
| Unauthenticated flood tries to bloat the signed ledger | availability | n/a | n/a | BLOCKED |
| Client-secret guessing against the OAuth endpoints | credential | n/a | n/a | BLOCKED |
| Path traversal via agent identifier into the key store | injection | n/a | n/a | BLOCKED |
| Customer B reads or revokes customer A's mandate | authorization | n/a | n/a | BLOCKED |
| Overflowing, float and wrong-typed payloads | robustness | n/a | n/a | BLOCKED |
| Forge an admin session using the formerly public constant secret | authentication | n/a | n/a | BLOCKED |
| Demo authentication and reset must fail closed outside KYM_ENV=demo | configuration | n/a | n/a | BLOCKED |

**Applicable attacks blocked** (excluding the honest case): scope-only 0/10, OAuth+static RAR 3/10, KYM 22/22.
**Like for like:** on the same 10 attacks the baselines can model, KYM blocked 10/10; the other 12 attacks target KYM-specific mechanisms (ledger, delegation, approvals, hardening) and have no baseline equivalent.
**Read this fairly:** the baselines are stateless by construction (no sender constraint, online revocation, budgets or approvals). A production OAuth server can add some of these; the claim is not that no other design can, but that these controls need state beyond the token. KYM was scored against attacks written by its own author.
KYM did **not** block: in_mandate_malicious. Errors: none.

## Details

### Beneficiary swap with a valid token (`beneficiary_swap`)
Refs: STRIDE:E, OWASP-API5, OWASP-LLM06
- **scope_only**: **SUCCEEDED** — executed
- **rar_static**: BLOCKED — denied
- **kym**: BLOCKED — HTTP 403 DENY ['BENEFICIARY_NOT_AUTHORIZED']

### Single payment above the per-transaction limit (`over_limit`)
Refs: STRIDE:E, OWASP-LLM06
- **scope_only**: **SUCCEEDED** — executed
- **rar_static**: BLOCKED — denied
- **kym**: BLOCKED — HTTP 403 DENY ['TRANSACTION_LIMIT_EXCEEDED']

### Many small in-limit payments drain the cumulative budget (`budget_drain`)
Refs: STRIDE:E, OWASP-API6
- **scope_only**: **SUCCEEDED** — moved 68600 vs monthly limit 50000
- **rar_static**: **SUCCEEDED** — moved 68600 vs monthly limit 50000
- **kym**: BLOCKED — moved 49000 vs monthly limit 50000 (legitimate payments executed, excess refused)

### Concurrent requests race the cumulative budget (`budget_race`)
Refs: STRIDE:T, OWASP-API6
- **scope_only**: **SUCCEEDED** — moved 80000 vs limit 30000
- **rar_static**: **SUCCEEDED** — moved 80000 vs limit 30000
- **kym**: BLOCKED — moved 30000 vs limit 30000 under 8 concurrent requests (some executed, the rest refused)

### Use of a still-valid token after the mandate is revoked (`revoked_mandate`)
Refs: STRIDE:E, NIST-CSF:PR.AA
- **scope_only**: **SUCCEEDED** — token still verifies offline: executed
- **rar_static**: **SUCCEEDED** — executed
- **kym**: BLOCKED — before revocation HTTP 201; after: HTTP 403 ['MANDATE_REVOKED']
- _Note:_ Baselines assume offline JWT validation. With immediate online token revocation they would also block; KYM adds mandate-level revocation that cascades to children independent of token plumbing.

### Stolen or shared bearer token replayed by another party (`stolen_token`)
Refs: STRIDE:S, OWASP-API2, RFC9449
- **scope_only**: **SUCCEEDED** — bearer token accepted from any holder
- **rar_static**: **SUCCEEDED** — bearer token accepted
- **kym**: BLOCKED — HTTP 403 ['INVALID_TOKEN'] (DPoP key mismatch)

### Replay of a captured DPoP proof (`dpop_replay`)
Refs: STRIDE:S, RFC9449
- **scope_only**: n/a — no proof-of-possession concept
- **rar_static**: n/a — no proof-of-possession concept
- **kym**: BLOCKED — first 201, replay 403

### High-value payment without human approval (`approval_threshold_bypass`)
Refs: STRIDE:E, NIST-CSF:PR.AA
- **scope_only**: **SUCCEEDED** — executed without any human approval
- **rar_static**: **SUCCEEDED** — executed without any human approval
- **kym**: BLOCKED — HTTP 202 REQUIRE_HUMAN_APPROVAL (held for a human; nothing executed)

### Approved CAD 180, agent submits CAD 190 (`approval_substitution`)
Refs: STRIDE:T
- **scope_only**: **SUCCEEDED** — executed (no approval concept)
- **rar_static**: **SUCCEEDED** — executed (no approval concept)
- **kym**: BLOCKED — approved 180.00, submitted 190.00: HTTP 202 ['APPROVAL_INVALID', 'HUMAN_APPROVAL_REQUIRED']

### Reuse of a one-time approval (`approval_replay`)
Refs: STRIDE:R
- **scope_only**: **SUCCEEDED** — executed repeatedly
- **rar_static**: **SUCCEEDED** — executed repeatedly
- **kym**: BLOCKED — first 201, replay 202 ['APPROVAL_INVALID', 'HUMAN_APPROVAL_REQUIRED']

### Injected document instructs a CAD 2,000 payment (`prompt_injection`)
Refs: OWASP-LLM01, OWASP-LLM06
- **scope_only**: **SUCCEEDED** — obeyed injection: executed CAD 2,000
- **rar_static**: BLOCKED — denied by static max amount
- **kym**: BLOCKED — same CAD 2,000 request and token: HTTP 403 ['TRANSACTION_LIMIT_EXCEEDED', 'MONTHLY_LIMIT_EXCEEDED']; separate shopping-agent loop with a document injection: DENY ['ACTION_NOT_AUTHORIZED', 'MONTHLY_LIMIT_EXCEEDED']

### HONEST CASE: malicious or mistaken payment that stays inside the mandate (`in_mandate_malicious`)
Refs: OWASP-LLM09
- **scope_only**: **SUCCEEDED** — executed
- **rar_static**: **SUCCEEDED** — executed
- **kym**: **SUCCEEDED** — HTTP 201: executed. A wrong-but-in-mandate action is NOT detectable by mandate enforcement.
- _Note:_ ACCEPTED LIMITATION. Mitigations are outside mandate enforcement: tighter limits, approval thresholds, customer notification, behavioural risk models.

### Parent agent delegates more authority than it holds (`delegation_escalation`)
Refs: STRIDE:E
- **scope_only**: n/a — no delegation record exists; agents share bearer tokens
- **rar_static**: n/a — no delegation record exists
- **kym**: BLOCKED — HTTP 422 ['DELEGATION_EXCEEDS_PARENT']

### Edit, rehash, delete or alter evidence after the fact (`ledger_tamper`)
Refs: STRIDE:T, STRIDE:R, NIST-CSF:DE.CM
- **scope_only**: n/a — plain logs: no integrity evidence
- **rar_static**: n/a — plain logs: no integrity evidence
- **kym**: BLOCKED — edit/rehash/delete/payload-alter detected: [True, True, True, True]

### Forged evidence package signed with attacker keys (`forged_evidence_package`)
Refs: STRIDE:S, STRIDE:T
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — verifier with pinned keys: ok=False; verifier trusting embedded keys: ok=True (why trusted keys must be obtained out of band)

### Hostile SPARQL query (cartesian explosion) (`sparql_dos`)
Refs: OWASP-API4
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — hostile cartesian query terminated after 2.1s; service still answers

### Unauthenticated flood tries to bloat the signed ledger (`unauth_flood`)
Refs: STRIDE:D, OWASP-API4
- **scope_only**: n/a — naive logging would append one record per request (300)
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — 300 junk requests wrote 60 signed events (cap 60/min); ledger intact=True

### Client-secret guessing against the OAuth endpoints (`client_auth_bruteforce`)
Refs: STRIDE:S, OWASP-API2
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — 20 attempts answered 401 then lockout 429 (limit 20/min/IP)

### Path traversal via agent identifier into the key store (`path_traversal`)
Refs: OWASP-API8, CWE-22
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — HTTP 422; no file written outside the key store

### Customer B reads or revokes customer A's mandate (`cross_customer`)
Refs: OWASP-API1
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — another customer got [403, 403]

### Overflowing, float and wrong-typed payloads (`malformed_input`)
Refs: OWASP-API4, OWASP-API8
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — status codes [400, 400, 400, 400] (no 5xx, nothing executed)

### Forge an admin session using the formerly public constant secret (`session_forgery`)
Refs: OWASP-API2
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — session forged with the previously public constant secret: HTTP 401

### Demo authentication and reset must fail closed outside KYM_ENV=demo (`production_fail_closed`)
Refs: OWASP-API8
- **scope_only**: n/a — n/a
- **rar_static**: n/a — n/a
- **kym**: BLOCKED — KYM_ENV=production: login 403, reset 503, API 503 (demo auth fails closed)
