# Getting started

A five-minute path from clone to a verified result. Everything is synthetic; nothing needs an account, an API key or the internet after install.

## Prerequisites

| Need | Version | Needed for |
|---|---|---|
| Python | 3.12+ (developed on 3.13) | backend, tests, CLI |
| [uv](https://docs.astral.sh/uv/) | any recent | creating the virtualenv |
| Node.js | 20+ | web UI only |
| Docker | optional | `docker compose up` |

## 1. Install and run the headless proof (no UI needed)

```bash
git clone https://github.com/PaulClas/Know-Your-Mandate.git
cd Know-Your-Mandate
make install                 # .venv with pinned dependencies
make scenarios               # scenarios A-M against a real SQLite database
make redteam                 # 28 attacks vs scope-only, OAuth+static-RAR and KYM
PYTHONPATH=apps/api .venv/bin/python examples/01_quickstart_bill_payment.py
```

You should see 13 scenarios pass, `KYM 26/26` in the red-team summary, and the quickstart's four payments (allow, approval needed, two denials). Run `make reset-demo` afterwards, because `make redteam` writes to the demo database.

## 2. Run the full demo with the UI

```bash
make install-web
make demo                    # API on :8000, UI on :3000, seeds synthetic data
```

Open <http://localhost:3000>. Suggested order: **Scenarios** (run C: valid token, denied payment), **Proof** (red-team), **Mandate Studio** (type CNL), **Evidence** (download and verify a package).

## 3. Or use Docker Compose

```bash
docker compose up --build
```

Starts PostgreSQL 16, the API and the web UI, all bound to `127.0.0.1`. See [deployment](deployment.md).

## 4. Verify what you ran

```bash
make test                    # backend tests
make verify-ledger           # hash chain, signatures and checkpoints of the evidence ledger
make benchmark               # authorization latency on your machine
```

## Where next

* [Examples](../examples/README.md): runnable code and a mandate library
* [Architecture](architecture/README.md) and [specifications](specifications/mandate-spec.md)
* [HTTP API reference](reference/api.md) and [reason codes](reference/reason-codes.md)
* [Configuration](configuration.md), [testing](testing.md), [benchmarks](benchmarks/README.md)
* [Security review](security/security-review.md), [risk register](risk/risk-register.md), [philosophy](philosophy/README.md)

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: kym` | Set `PYTHONPATH=apps/api` when running scripts directly (the Makefile does this) |
| `429 Too Many Requests` during experiments | The built-in rate limiter; wait a minute or raise `KYM_RATE_LIMIT_PER_MIN` / `KYM_FAILED_AUTH_PER_MIN` |
| `403` from `/api/session` | `KYM_ENV` is not `demo`; demo sessions are disabled by design (fail closed) |
| Scenarios behave oddly after `make redteam` | `make reset-demo` |
| Port 8000 or 3000 busy | Stop the other process, or run the API with `--port` and set `KYM_API_URL` for the web app |
