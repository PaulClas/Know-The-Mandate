# Security policy

KYM is an **experimental proof of concept** with synthetic data and sandbox security mechanisms. It must not be used to protect real money or real customer data. Even so, we want to hear about weaknesses: the project exists to make claims about authorization *falsifiable*.

## Supported versions

| Version | Supported |
|---|---|
| `main` / latest `0.x` | Yes (best effort) |
| Anything else | No |

## Reporting a vulnerability

**Please do not open a public issue for an exploitable vulnerability.** Use GitHub's private reporting:
<https://github.com/PaulClas/Know-The-Mandate/security/advisories/new>

Include: affected component/commit, reproduction steps (a failing test or a new attack in `apps/api/kym/redteam.py` is ideal), impact, and any suggested fix.

What to expect (best effort, single maintainer): acknowledgement within 7 days; an assessment within 14 days; a fix or a documented acceptance in the [security review](docs/security/security-review.md) afterwards, with credit if you wish.

## In scope
* Bypass of mandate enforcement: any way to move money or read data outside an active mandate with a valid or invalid credential.
* Replay or substitution of approvals, decisions, DPoP proofs, tokens.
* Evidence-ledger tampering that verification does not detect; evidence-package forgery that a verifier with **pinned keys** accepts.
* Authentication/authorization flaws in the API (cross-customer access, role bypass), injection, path traversal, resource-exhaustion vectors reachable without authentication.

## Out of scope / already disclosed
These are documented limitations (see the [security review](docs/security/security-review.md) open items and the [risk register](docs/risk/risk-register.md)), not new findings:
* The demo's no-password sessions, plaintext demo keys, single-process lock, absence of operator dual control, sandbox OAuth server.
* Attacks that stay **inside** a mandate (`in_mandate_malicious`): mandate enforcement cannot detect them by design.
* Findings that require running with `KYM_ENV=demo` on a publicly reachable host.

## Safe harbour
Research on your own local instance is welcome. Do not test against infrastructure you do not own. Good-faith research under this policy will not be pursued.

## Hardening reference
`docs/security/security-review.md` lists 15 fixed and 21 open/accepted items, mapped to OWASP API Security Top 10 (2023) and NIST CSF 2.0.
