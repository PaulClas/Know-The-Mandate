# KYM web — Know Your Mandate (frontend)

Next.js (App Router) + TypeScript (strict) + Tailwind v4 dashboard for the KYM proof of concept
(fictional Meridian Bank). **Synthetic demo — not compliant or certified.**

> The agent proposes. The mandate authorizes. The bank enforces. The ledger remembers.

## Run

Prerequisites: Node 20+, and the FastAPI backend on `http://localhost:8000`:

```bash
# from the repository root
PYTHONPATH=apps/api .venv/bin/uvicorn kym.app:app --port 8000
```

```bash
cd apps/web
npm install
npm run dev          # http://localhost:3000
# or: npm run build && npm start
```

`next.config.ts` proxies `/api/*`, `/bank/*`, `/oauth/*` and `/adapters/*` to the API
(override the target with `KYM_API_URL`). The UI signs in as a demo user (default `admin_001`,
token kept in `localStorage`); use the header switcher to become a customer, investigator, etc.
Scenario runs and *Reset demo* need `admin_001`; approving mandates/payments needs a customer.

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Executive overview, KPIs, ledger integrity, decision chart, Scenario C feature |
| `/agents` | Agent registry: declared vs bank-verified facts, trust profile, register / verify / suspend |
| `/studio` | Mandate studio: instruction → ambiguities → CNL → live compile artifacts → create mandate |
| `/portal` | Customer portal: accounts, agents, mandate lifecycle, per-payment approvals (EN/FR) |
| `/delegation` | React Flow delegation graph with parent-vs-child authority comparison |
| `/playground` | Authorization playground with presets (incl. "valid token, invalid mandate") |
| `/sandbox` | Chat with six simulated agents; step-by-step tool call → OAuth → mandate → risk → ledger |
| `/scenarios` | Scenarios A–M one-click runs, Reset demo (admin) |
| `/transactions` | Transaction monitor with trace drawer |
| `/ledger` | Evidence ledger, integrity verification, signed checkpoints |
| `/disputes` | Timeline reconstruction, responsibility attribution, evidence download |
| `/ontology` | Ontology graph (schema/instances), triples + JSON-LD, SPARQL (read-only) |
| `/standards` | Standards status and Canada / Québec / U.S. control mappings (not legal advice) |

Money is always integer minor units (`lib/money.ts` formats/parses via string and `BigInt`, never floats).
`lib/types.ts` mirrors `apps/api/kym/schemas.py`; `lib/api.ts` is the typed client. Endpoints that return
404/501 render a "backend pending" state instead of a blank page.

## Checks

```bash
npx tsc --noEmit
npm run lint
npm run build
```

## End-to-end tests (Playwright, Chromium)

Assumes the API on `:8000` and the web app on `:3000` (`npm run dev` or `npm start`); Playwright starts
nothing unless `PW_START_WEB=1` is set.

```bash
npx playwright install chromium   # once
npm run test:e2e
PW_SHOTS=1 npm run test:e2e       # also writes full-page screenshots to test-results/shots
```

Specs (`e2e/`): overview + ledger integrity, studio compile + SHACL, playground
(valid-token/invalid-mandate → DENY), scenarios (run Scenario C), customer approve/activate flow,
sandbox, ledger, ontology, standards, transactions, and a smoke test over every route.
Specs that need an active mandate create one by running Scenario C as `admin_001` through the API.

### Recorded outcome (2026-11-26)

Final run against the live API with `PW_START_WEB=1 npx playwright test`: **25 passed, 0 failed** (~57 s) on Chromium, after `npx tsc --noEmit`, `npm run lint` and `npm run build` were clean. An earlier run had 2 failures caused by test-order assumptions (no active mandate for the bill payment agent / no transactions on a fresh database); the helper `ensureActiveMandate` now guarantees both, and the suite was re-run in full.
