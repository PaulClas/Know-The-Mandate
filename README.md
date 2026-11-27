# KYM — Know Your Mandate

**Bank the agent. Verify the mandate. Govern the execution. Record the evidence.**

[![CI](https://github.com/PaulClas/Know-The-Mandate/actions/workflows/ci.yml/badge.svg)](https://github.com/PaulClas/Know-The-Mandate/actions/workflows/ci.yml)
[![Security checks](https://github.com/PaulClas/Know-The-Mandate/actions/workflows/security.yml/badge.svg)](https://github.com/PaulClas/Know-The-Mandate/actions/workflows/security.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Status: experimental](https://img.shields.io/badge/status-experimental%20PoC-orange.svg)](#security-limitations-read-before-drawing-conclusions)
[![Data: synthetic only](https://img.shields.io/badge/data-synthetic%20only-lightgrey.svg)](#the-idea)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

> **The agent proposes. The mandate authorizes. The bank enforces. The ledger remembers.**

**KYM (Know Your Mandate) is an experimental framework that lets a bank represent, enforce and prove the financial authority a customer has delegated to an AI agent.** The customer's authority is captured as a *mandate*, checked deterministically on every request (even when the agent holds a valid OAuth token), and recorded in a signed, hash-chained evidence ledger. It runs locally with no paid services, API keys, real credentials or external AI.

> ⚠️ **Synthetic demo. Not compliant, certified, audited or production-ready.** All customers, accounts, agents, KYC and "sanctions" data are fictional. Authentication, signing keys and approvals use clearly labelled sandbox mechanisms. Nothing here is legal advice or a claim of conformance with any law, regulation or standard. KYM is **not** related to "Know Your Meme".

**Contents:** [At a glance](#at-a-glance-for-people-and-ai-assistants) · [The idea](#the-idea) · [Quickstart](#quickstart) · [What is built](#what-is-built) · [Philosophy](#philosophy-in-brief) · [Risks](#risks-and-disclosures) · [Prove it](#prove-it-or-break-it) · [Run it](#run-it) · [Test evidence](#test-evidence-recorded-from-actual-runs) · [Standards](#standards-implemented-vs-simulated-vs-mapped) · [Security limitations](#security-limitations-read-before-drawing-conclusions) · [Documentation](#documentation) · [Contributing](#contributing) · [Security policy](#security-policy) · [Contact](#contact) · [Citing](#citing-kym) · [License](#license)

## At a glance (for people and AI assistants)

| Question | Short answer |
|---|---|
| What is it? | A mandate registry + deterministic policy decision/enforcement point + signed evidence ledger + simulated bank, for AI-agent financial authority |
| What does it add to OAuth? | State and per-request decisions: cumulative budgets, instant revocation, single-use approvals, delegation lineage, evidence. It *uses* OAuth (PKCE, PAR, DPoP, RFC 9396 RAR) |
| Is it a standard? | No. The namespace (`https://example.org/kym/v1#`), KYM-CNL and the `kym_financial_mandate` RAR type are experimental proposals |
| What can it NOT do? | Stop wrong-but-permitted actions inside a mandate; make agents safe; decide legal liability; guarantee compliance |
| What is the evidence? | `make redteam`: 23 attacks against a scope-only bank, an OAuth+static-RAR bank and KYM. KYM blocks 22/22 applicable attacks; on the 10 attacks the baselines can model: scope-only 0/10, stateless static RAR 3/10, KYM 10/10. One attack is documented as unstoppable. Self-assessed, written by the author, baselines are deliberately stateless |
| Is it production-ready? | No: see [security review](docs/security/security-review.md) and [risk register](docs/risk/risk-register.md) |
| Where do I learn more? | [FAQ](docs/faq.md) · [Philosophy and critics](docs/philosophy/README.md) · [Glossary](docs/glossary.md) · [Docs index](docs/README.md) · [llms.txt](llms.txt) |

## The idea

Traditional controls answer *who is the customer* (KYC), *is this really that entity* (authentication), *what API access does this client have* (OAuth), *which agent is acting* (KYA) and *is this transaction risky* (KYT). None of them establishes **who granted what authority to whom, for what purpose, within which limits, until when, and with what evidence**. KYM treats that **mandate** as a separately governed object with a verifiable lifecycle, and separates four concepts:

1. **Identity** — who/what is this? (customer KYC, agent registry + attestation)
2. **Technical permission** — what can this credential call? (OAuth scopes, DPoP-bound token)
3. **Delegated authority** — what has the customer actually authorized? (mandate)
4. **Financial execution** — did the money move, and was it within the mandate? (payment engine + evidence ledger)

A valid access token never implies an authorized financial operation. **Scenario C** shows it: the agent holds a perfectly valid `payments.initiate` token, OAuth verification passes, mandate verification fails, the payment is denied.

## Quickstart

```bash
git clone https://github.com/PaulClas/Know-The-Mandate.git && cd Know-The-Mandate
make install
PYTHONPATH=apps/api .venv/bin/python examples/01_quickstart_bill_payment.py
```

```text
mandate mdt_… v1 is ACTIVE (digest sha256:…)
agent holds a valid token with scope: balances.read payments.initiate

  CAD   85.00 -> beneficiary_hydro_quebec   HTTP 201  decision=ALLOW
  CAD  180.00 -> beneficiary_hydro_quebec   HTTP 202  decision=REQUIRE_HUMAN_APPROVAL
  CAD  300.00 -> beneficiary_hydro_quebec   HTTP 403  decision=DENY  ['TRANSACTION_LIMIT_EXCEEDED']
  CAD   50.00 -> beneficiary_videotron      HTTP 403  decision=DENY  ['BENEFICIARY_NOT_AUTHORIZED']
```

Same agent, same valid OAuth token, four different outcomes: the **mandate** decides, not the token. More: [getting started](docs/getting-started.md), [examples](examples/README.md), `make scenarios` (A–M), `make redteam` (23 attacks).

## What is built

| Area | Where | Notes |
|---|---|---|
| Mandate ontology (OWL/RDF, PROV-O + ODRL reuse), SHACL shapes, JSON-LD context | [packages/ontology](packages/ontology) | Experimental `https://example.org/kym/v1#` namespace. Used for validation/explanation, **never** for runtime authorization |
| KYM-CNL controlled language (Lark grammar) + deterministic compiler | [packages/controlled-language](packages/controlled-language), [cnl.py](apps/api/kym/cnl.py) | Inspired by ASD-STE100; makes no conformance claim |
| Canonical mandate model (Pydantic + generated JSON Schema) | [schemas.py](apps/api/kym/schemas.py), [packages/mandate-schema](packages/mandate-schema) | Integer minor units; explicit timezones |
| Deterministic Policy Decision Point | [policy.py](apps/api/kym/policy.py) | Pure function of a JSON snapshot → replayable. Deny by default |
| Sandbox OAuth/OIDC server (PAR, PKCE, RAR, DPoP, introspection, revocation, token exchange) | [oauth.py](apps/api/kym/oauth.py) | **Sandbox adapter**, not a certified server |
| Policy Enforcement Point + simulated open-banking gateway | [gateway.py](apps/api/kym/gateway.py), [bank.py](apps/api/kym/bank.py) | Payment engine accepts only signed, short-lived, single-use decisions bound to the exact operation hash |
| Double-entry accounting ledger (money) | [bank.py](apps/api/kym/bank.py) | Distinct from the evidence ledger (authority) |
| KYM Evidence Ledger (Ed25519, hash-chained, signed checkpoints, RFC 8785) | [ledger.py](apps/api/kym/ledger.py) | Tamper-evident, not tamper-proof; see limits below |
| Human approval (bound to operation hash, single use, expiring, multi-signatory) | [approvals.py](apps/api/kym/approvals.py) | Demo assurance level: simulated session |
| Synthetic risk engine (KYT), trust profile | [risk.py](apps/api/kym/risk.py), [agents.py](apps/api/kym/agents.py) | Not real AML/sanctions screening |
| Delegation with strict attenuation, cycle detection, cascading revocation | [mandates.py](apps/api/kym/mandates.py), [policy.py](apps/api/kym/policy.py) | |
| Dispute reconstruction, evidence packages, offline verification, responsibility mapping | [disputes.py](apps/api/kym/disputes.py), [responsibility.py](apps/api/kym/responsibility.py) | Attributes *who did what*; never decides liability |
| Regulatory control mappings (CA, CA-QC, US) and standards matrix | [policies/](policies), [standards/](standards), [docs/research](docs/research) | Mappings, not compliance claims |
| Protocol adapters (MCP-shaped, AP2 conceptual mapping, extension interfaces) | [adapters.py](apps/api/kym/adapters.py) | See the standards matrix for what is real vs. mapped |
| Agent sandbox (6 deterministic agents, restricted tools) and scenarios A–M | [sandbox.py](apps/api/kym/sandbox.py), [scenarios.py](apps/api/kym/scenarios.py) | Every step uses the real HTTP API, PDP and ledger |
| Web UI (Next.js) | [apps/web](apps/web) | 12 pages incl. Mandate Studio, ontology explorer, playground, ledger, disputes |

## Philosophy in brief

Authority is not identity and not permission; the agent never decides what it may do; the bank enforces observable facts, not intentions; authority can only narrow when delegated; humans approve exact operations; evidence is checkable by someone who does not trust the bank; and the claims are narrow enough to be falsified. Read the full argument, twelve steelmanned critic objections (and where the critics are right) in **[docs/philosophy](docs/philosophy/README.md)**.

## Risks and disclosures

KYM's authors publish what could go wrong: **[risk register](docs/risk/risk-register.md)** (hacking, insider abuse, design flaws, legal exposure, adoption failure, "when not to use KYM", pre-mortem) and **[security review](docs/security/security-review.md)** (24 vulnerabilities found and fixed (15 in a self-review, 9 more through an independent review and follow-up testing), 22 open or accepted items, OWASP API Top 10 and NIST CSF mapping). The largest open issues: no real authentication in the demo, plaintext keys, a single-process lock, no maker–checker for operators, approval-fatigue unmeasured, no external audit.

## Prove it (or break it)

```bash
make redteam      # 23 attacks x 3 designs, same real token; writes docs/redteam/latest.md
make test         # unit, property-based, integration, security
make scenarios    # demonstration scenarios A-M
make verify-ledger
```

The red-team harness compares a **scope-only bank**, an **OAuth + static RAR bank** (stronger than scopes, but deliberately stateless: no sender constraint, online revocation, budgets or approvals, so it is a model of one common design, not of every OAuth deployment) and **KYM**, and includes an attack KYM cannot stop (`in_mandate_malicious`). It runs in the UI at `/proof`. Add an attack that KYM fails and you have improved the project. After `make redteam`, run `make reset-demo` for a clean demo state.

## Run it

Prerequisites: Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Node 20+ (for the UI). No Docker required.

```bash
make install        # creates .venv and installs pinned backend deps
make install-web    # npm install for the UI
make demo           # migrates + seeds synthetic data, starts API :8000 and UI :3000
```

* API docs (OpenAPI/Swagger): http://127.0.0.1:8000/docs — static copy in [docs/specifications/openapi.json](docs/specifications/openapi.json)
* UI: http://localhost:3000
* Everything else: `make test`, `make scenarios`, `make verify-ledger`, `make benchmark`, `make reset-demo`, `make lint` (see `make help`).
* Docker: `docker compose up --build` (PostgreSQL 16 + API + UI, localhost-bound, demo secrets from `.env.example`). **Verified end to end on 2026-11-27**: the stack built and started, scenarios A–M passed through the containerised API on PostgreSQL 16, the red-team run gave 0/10, 3/10 and 22/22, and the web container proxied the API. Details in [docs/deployment.md](docs/deployment.md).

### Demo accounts and roles (no passwords — demo sessions only)

| User | Role | Notes |
|---|---|---|
| `admin_001` | bank operator | verifies/suspends agents, runs scenarios, resets demo; **cannot** approve mandates or transactions |
| `investigator_001` | investigator | read-only evidence and disputes |
| `customer_001` Alice Tremblay | customer (CA-QC, French) | owns `account_001` chequing / `account_002` savings |
| `customer_002` Ben Carter | customer (US) | used for cross-customer access tests |
| `customer_003` Priya Nair, `customer_004` Jordan Lee | authorized signatories of Northwind Supply Inc. (`business_001`) | business treasury / separation of duties |
| `customer_005` Sam Ortiz | analyst **without** signing authority | |

## Demonstrate it

* **5-minute live demo:** [docs/specifications/demo-script-5-min.md](docs/specifications/demo-script-5-min.md)
* **10-minute technical walkthrough:** [docs/specifications/walkthrough-10-min.md](docs/specifications/walkthrough-10-min.md)
* One-click scenarios A–M in the UI (`/scenarios`) or `make scenarios`.

## Test evidence (recorded from actual runs)

| Suite | Result |
|---|---|
| `make test` — unit, property-based (Hypothesis), integration, security, red-team regression, docs-consistency | **237 passed, 0 failed, 1 skipped** (the PostgreSQL multi-process test runs only when `KYM_TEST_PG_URL` is set; it was run separately); line + branch coverage **82%** (`make coverage`, [how to read it](docs/testing.md)) |
| `make scenarios` — scenarios A–M against the real engine (SQLite), run three times in a row on one database | **13/13 passed each time**; `make verify-ledger` afterwards: 767 events, 8 checkpoints, chain intact |
| Same 13 scenarios + Alembic migration against **PostgreSQL 14** and, through `docker compose`, **PostgreSQL 16** | **13/13 passed** on both |
| `ruff check apps tests` | clean |
| `make redteam` (23 attacks, 3 designs) | scope-only 0/10, OAuth + static RAR 3/10, **KYM 22/22** applicable blocked (10/10 on the same ten attacks the baselines can model); 1 documented honest gap; 0 harness errors ([results](docs/redteam/latest.md)) |
| Web: `tsc`, `eslint`, `next build`, Playwright (Chromium, live API) | clean; **30 passed, 0 failed** ([apps/web/README.md](apps/web/README.md)) |
| `make benchmark` (single process, SQLite, in-process ASGI client) | PDP pure evaluation p50 0.076 ms / p95 0.088 ms / p99 0.135 ms (n=20 000); full gateway payment p50 18.9 ms / p95 24.7 ms / p99 37.0 ms (n=300). Raw output: [docs/benchmarks/latest.json](docs/benchmarks/latest.json) |


## Standards: implemented vs. simulated vs. mapped

Full matrix with sources and "interoperability tested?" (it is **No** everywhere): [docs/research/standards-mapping.md](docs/research/standards-mapping.md), machine-readable [standards/standards.json](standards/standards.json), shown in the UI at `/standards`.

* **Implemented (sandbox quality, using maintained libraries):** JWT/JWS signing & verification (PyJWT, ES256), PKCE S256, RFC 9396 `authorization_details` (proposed type `kym_financial_mandate`), RFC 9449 DPoP proof validation, RFC 7662 introspection, RFC 7009 revocation, RFC 8707 audience check, RFC 8785 JCS (`rfc8785`), RDF/Turtle/JSON-LD (rdflib), SHACL (pySHACL), SPARQL (rdflib, read-only guard), PROV-O and ODRL terms reuse, Ed25519 signatures (`cryptography`).
* **Simulated / simplified:** RFC 9126 PAR, RFC 8693 token exchange, OIDC `id_token`, customer authentication and approval (simulated session — **not** passkeys), agent attestation, KYC, KYT, sanctions screening, payment rails.
* **Conceptually mapped only:** mTLS (RFC 8705), FAPI 2.0, OpenID Shared Signals/CAEP, FDX, AP2 ([mapping](docs/research/ap2-mapping.md)), Visa/Mastercard agentic commerce, ACP, x402, A2A, SPIFFE/SPIRE, OPA/Cedar (not used — a typed Python engine is used).
* **Experimental KYM proposals (not standards):** ontology v1, KYM-CNL, `kym_financial_mandate` RAR type, `https://example.org/kym/*` JWT claims, the evidence ledger design.

## Security limitations (read before drawing conclusions)

* Demo sessions have no authentication; demo keys (ledger, decision, witness, customer consent, agent, authorization server) are plain files under `.kym-data/keys` (mode 0600). Production: HSM/KMS, WORM storage, RFC 3161 timestamping, independent witnesses, SPIFFE/SPIRE, passkeys, mTLS, a FAPI-certified authorization server.
* The ledger is **tamper-evident, not tamper-proof**: whoever can replace the database *and* the keys can rewrite history. The demo adds signed checkpoints, an independent witness key and locally exported checkpoint files to show stronger detection (Scenario L).
* Budget atomicity relies on a global write lock: an in-process lock plus a database-level lock (`BEGIN IMMEDIATE` on SQLite, an advisory lock on PostgreSQL). `make concurrency` races four OS processes for one budget and passed on SQLite and PostgreSQL 16 (without the lock, PostgreSQL runs crashed on the ledger sequence). It is a throughput ceiling, tested at four processes, not at load or across nodes.
* Scenario runs call `demo.prepare_isolated_state()` (demo/test only): it starts a fresh *synthetic risk window* and tops up balances with a balanced `DEMO_TOPUP` double-entry pair, so repeated runs are independent. It never touches the enforcement path.
* Within-mandate mistakes (e.g. paying CAD 90 instead of CAD 9) cannot be detected by mandate enforcement alone (Scenario D).
* A valid signature proves integrity and key control, **not** legally effective consent.

Details: [threat model](docs/threat-model/threat-model.md), [gap analysis](docs/specifications/production-readiness-gap-analysis.md), [regulatory mapping](docs/regulatory-mapping/README.md).

## Repository map

```
apps/api/kym/        FastAPI modular monolith (see AGENTS.md for the module/boundary map)
apps/api/alembic/    database migrations
apps/web/            Next.js UI
packages/ontology/   OWL/Turtle ontology, SHACL shapes, JSON-LD context
packages/controlled-language/  KYM-CNL grammar
packages/mandate-schema/       generated JSON Schema
policies/            bank policy (versioned) and regulatory control mappings
standards/           standards matrix data, AP2 mapping
tests/               unit, integration, security (+ web e2e under apps/web/e2e)
examples/            runnable quickstart, curl walkthrough, KYM-CNL mandate library
scripts/             llms-full and reference generators, GitHub metadata helper
docker/              API Dockerfile (compose file at the repository root)
.github/             CI and security workflows, issue/PR templates, CODEOWNERS, Dependabot
docs/                architecture, ADRs, specifications, research, threat model, regulatory mapping,
                     security review, risk register, philosophy, FAQ, glossary, red-team results,
                     getting started, testing, configuration, deployment, generated API reference
LICENSE NOTICE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md GOVERNANCE.md ROADMAP.md CHANGELOG.md   project policies
llms.txt / llms-full.txt / CITATION.cff / codemeta.json   machine-readable summaries for AI assistants and citation
```

The repository layout deliberately omits empty placeholder services (`services/*`, `scenarios/*` directories): logical components live in one modular monolith with explicit module boundaries ([ADR-0001](docs/adr/0001-modular-monolith.md)).

## Documentation

| | |
|---|---|
| Start | [Getting started](docs/getting-started.md) · [Examples](examples/README.md) · [Configuration](docs/configuration.md) · [Deployment](docs/deployment.md) |
| Reference | [HTTP API](docs/reference/api.md) · [Reason codes](docs/reference/reason-codes.md) · [Mandate spec](docs/specifications/mandate-spec.md) · [KYM-CNL](docs/specifications/kym-cnl-spec.md) · [Ledger spec](docs/specifications/evidence-ledger-spec.md) · [OpenAPI](docs/specifications/openapi.json) |
| Understand | [FAQ](docs/faq.md) · [Glossary](docs/glossary.md) · [Philosophy and critics](docs/philosophy/README.md) · [Architecture](docs/architecture/README.md) · [ADRs](docs/adr) |
| Trust | [Security review](docs/security/security-review.md) · [Risk register](docs/risk/risk-register.md) · [Red-team results](docs/redteam/latest.md) · [Testing](docs/testing.md) · [Benchmarks](docs/benchmarks/README.md) |
| Trust more | [External review status and how to commission one](docs/security/external-review.md) · [Media and citation guide](docs/media-guide.md) |
| Project | [Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md) · [Governance](GOVERNANCE.md) · [Support](SUPPORT.md) |

Full index: [docs/README.md](docs/README.md).

## Contact

Questions, corrections, critiques, or a wish to review the design: **email me at [clas.paul@gmail.com](mailto:clas.paul@gmail.com)**, or open a [GitHub issue](https://github.com/PaulClas/Know-The-Mandate/issues) for anything that others may benefit from. Security reports: [SECURITY.md](SECURITY.md).

**About the author.** I am Paul Clas, a **machine learning developer**. I built KYM as an independent exploration of how banks might govern the authority they hand to AI agents. I am not a bank, payments-security, cryptography or legal professional, which is why the project publishes its [risks](docs/risk/risk-register.md), [open findings](docs/security/security-review.md) and [call for external review](docs/security/external-review.md) rather than asking you to trust it. Expert criticism is the most useful thing you can send me. Media and citation notes: [media guide](docs/media-guide.md).

## Contributing

Issues and pull requests are welcome, especially **new attacks KYM fails** and corrections to the disclosures. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). The invariants in [AGENTS.md](AGENTS.md) apply to humans and coding assistants alike.

## Security policy

Please report vulnerabilities privately; see [SECURITY.md](SECURITY.md). KYM is a synthetic-data demo with sandbox security, so the [known limitations](docs/security/security-review.md) are not vulnerabilities, but novel bypasses of the mandate check are very welcome.

## Citing KYM

See [CITATION.cff](CITATION.cff) (GitHub shows a "Cite this repository" button) and [codemeta.json](codemeta.json). KYM is an experimental proposal, not a standard.

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE). Chosen for its explicit patent grant and because it is the common choice for security and infrastructure projects (it is compatible with the permissive dependencies used here; `psycopg` and `sharp-libvips` are LGPL-3.0 and used unmodified, see NOTICE). Provided as is, without warranty; not legal, compliance or financial advice.
