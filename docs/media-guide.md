# Media and citation guide: what you can and cannot say about KYM

KYM is one person's experimental proof of concept. This page exists so that coverage, talks and citations stay accurate.

## You can say

* KYM is an **experimental, open-source proof of concept** that explores how a bank could represent, enforce and prove the financial authority a customer delegates to an AI agent.
* It **adds state to OAuth**: it uses OAuth 2.0 (PKCE, PAR, DPoP, RFC 9396 Rich Authorization Requests) and layers a revocable mandate, cumulative budgets, single-use approvals, delegation lineage and a signed evidence ledger on top.
* In its own red-team harness, KYM blocked 22 of 22 applicable attacks. On the same ten attacks the baselines could model, a stateless scope-only design blocked 0 and a stateless OAuth+static-RAR design blocked 3. These results are **self-assessed** and the baselines are deliberately simple.
* It documents what it **cannot** stop: a wrong-but-permitted payment inside a mandate.
* It has been tested on SQLite and PostgreSQL 16, with 237 automated tests and about 82% line-and-branch coverage.

## You cannot say

| Do not say | Why |
|---|---|
| "Secure", "audited", "verified by experts", "pen-tested" | No external review exists ([external-review.md](security/external-review.md)) |
| "Compliant with" any law, regulation or standard (FAPI, PSD2, GDPR, OSFI, FINTRAC, GLBA, …) | Mappings are research aids, not conformance claims |
| "Production-ready", "bank-grade", "used by banks" | Synthetic data, demo authentication, plaintext keys, no pilot |
| "A standard", "proposed to IETF/OpenID", "endorsed by OWASP/NIST" | The namespace, KYM-CNL and `kym_financial_mandate` are experimental names. OWASP and NIST identifiers are cited as references only |
| "Prevents AI agents from making mistakes or being hijacked" | It bounds the *authority*; an agent can still err or be hijacked within it |
| "Determines who is liable" | Evidence supports reconstruction; it makes no liability determination |
| "Solves agentic payments" | It is one design for one slice of the problem |
| Any real customer, bank or "Meridian Bank" as real | All data and organizations are fictional |

## Facts for a quick check

| Fact | Value | Where verified |
|---|---|---|
| License | Apache-2.0 | [LICENSE](../LICENSE) |
| Maintainer | One person, a machine learning developer, not a bank, payments-security or legal professional | [README](../README.md#contact) |
| Red-team | 23 attacks, 22 applicable to KYM, 1 documented gap | [docs/redteam/latest.md](redteam/latest.md) |
| Findings | 24 fixed, 22 open or accepted | [security review](security/security-review.md) |
| Not related to | "Know Your Meme" | |

## Citing

Use [CITATION.cff](../CITATION.cff) (GitHub's "Cite this repository") and state the commit or version. Corrections welcome: see [Contact](../README.md#contact).
