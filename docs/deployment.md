# Deployment (local and Docker)

> KYM is a demo. These instructions run it on one machine. There is no supported production deployment; see the [production-readiness gap analysis](specifications/production-readiness-gap-analysis.md).

## Docker Compose

```bash
docker compose up --build        # PostgreSQL 16 + API + web, ports bound to 127.0.0.1
docker compose down -v           # stop and delete volumes
```

| Service | Image / build | Port | Notes |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | `127.0.0.1:55432` | Healthcheck gates the API. Password from `KYM_POSTGRES_PASSWORD` |
| `api` | [docker/Dockerfile.api](../docker/Dockerfile.api) | `127.0.0.1:8000` | Runs Alembic migrations, then serves FastAPI (synthetic data is seeded on first start) |
| `web` | [apps/web/Dockerfile](../apps/web/Dockerfile) | `127.0.0.1:3000` | Next.js; proxies API routes to `api:8000` |

### What was verified

On 2026-11-27 the stack was built and started with `docker compose up --build -d` on a developer laptop. Through the containerised API on **PostgreSQL 16**: scenarios A to M all passed, the red-team run returned 0/10, 3/10 and 22/22 with no errors, the web container proxied `/`, `/api/overview` and `/llms.txt` on port 3000, and the database held a balanced trial balance. This is a one-off manual verification; CI also builds and smoke-tests the stack (see [ci.yml](../.github/workflows/ci.yml)).

## Local without Docker

See [getting started](getting-started.md). SQLite is the default and the most-tested backend; PostgreSQL is covered by the migration and scenario runs above.

## Exposing it

Do not. Ports are bound to localhost on purpose, sessions have no passwords, and signing keys sit on disk. If you must demo remotely, use an SSH tunnel, keep `KYM_ENV=demo`, and treat the data as public.
