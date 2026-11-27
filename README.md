# KYM — Know Your Mandate

**Bank the agent. Verify the mandate. Govern the execution. Record the evidence.**

> **The agent proposes. The mandate authorizes. The bank enforces. The ledger remembers.**

KYM is an **experimental proof of concept** of an authorization control plane and cryptographically verifiable evidence ledger that lets a bank govern the *financial authority* delegated to AI agents. It runs locally with no paid services, API keys, real credentials or external AI.

> ⚠️ **Synthetic demo. Not compliant, certified, audited or production-ready.** All customers, accounts, agents, KYC and "sanctions" data are fictional. Authentication, signing keys and approvals use clearly labelled sandbox mechanisms. Nothing here is legal advice or a claim of conformance with any law, regulation or standard. See [docs/specifications/production-readiness-gap-analysis.md](docs/specifications/production-readiness-gap-analysis.md).

## The idea

Traditional controls answer *who is the customer* (KYC), *is this really that entity* (authentication), *what API access does this client have* (OAuth), *which agent is acting* (KYA) and *is this transaction risky* (KYT). None of them establishes **who granted what authority to whom, for what purpose, within which limits, until when, and with what evidence**. KYM treats that **mandate** as a separately governed object with a verifiable lifecycle, and separates four concepts:

1. **Identity** — who/what is this? (customer KYC, agent registry + attestation)
2. **Technical permission** — what can this credential call? (OAuth scopes, DPoP-bound token)
3. **Delegated authority** — what has the customer actually authorized? (mandate)
4. **Financial execution** — did the money move, and was it within the mandate? (payment engine + evidence ledger)

A valid access token never implies an authorized financial operation. **Scenario C** shows it: the agent holds a perfectly valid `payments.initiate` token, OAuth verification passes, mandate verification fails, the payment is denied.

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
* Docker: `docker compose up --build` (API + PostgreSQL + UI, localhost-bound, demo secrets from `.env.example`). The Compose stack itself has **not been run in the authoring environment** (the Docker daemon could not pull images); the API code path was verified instead by running the Alembic migration and all scenarios against a local PostgreSQL 14 server.

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

## Test evidence (recorded from actual runs on 2026-11-26)

| Suite | Result |
|---|---|
| `make test` — unit, property-based (Hypothesis), integration, security | **183 passed, 0 failed** (~25 s), run twice consecutively |
| `make scenarios` — scenarios A–M against the real engine (SQLite), run three times in a row on one database | **13/13 passed each time**; `make verify-ledger` afterwards: 767 events, 8 checkpoints, chain intact |
| Same 13 scenarios + Alembic migration against **PostgreSQL 14** | **13/13 passed** |
| `ruff check apps tests` | clean |
| Web: `tsc`, `eslint`, `next build`, Playwright (Chromium, live API) | clean; **25 passed, 0 failed** ([apps/web/README.md](apps/web/README.md)) |
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
* Budget atomicity relies on a single-process write lock plus database transactions; a multi-process deployment needs row-level locking (`SELECT … FOR UPDATE`) or serializable isolation.
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
docs/                architecture, ADRs, specifications, research, threat model, regulatory mapping
```

The repository layout deliberately omits empty placeholder services (`services/*`, `scenarios/*` directories): logical components live in one modular monolith with explicit module boundaries ([ADR-0001](docs/adr/0001-modular-monolith.md)).
