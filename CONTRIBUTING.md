# Contributing to KYM

Thank you for helping. KYM is an experimental proof of concept; **the most valuable contribution is a credible attack or a failing test**, not praise. Please read [AGENTS.md](AGENTS.md) (architectural invariants) and the [code of conduct](CODE_OF_CONDUCT.md) first.

## Quick start (development)

```bash
git clone https://github.com/PaulClas/Know-The-Mandate && cd Know-The-Mandate
make install            # .venv + pinned backend deps + dev tools (pytest, hypothesis, ruff, coverage)
make install-web        # npm install for the UI (Node 20+)
make test               # backend: unit, property-based, integration, security
make lint               # ruff + tsc
make coverage           # tests with line+branch coverage
make reference          # regenerate docs/reference after API or reason-code changes
make demo               # API :8000 + UI :3000 with synthetic data
```

Python >= 3.12, [uv](https://docs.astral.sh/uv/), Node 20+. No external services or API keys are needed. Docker is optional (`docker compose up --build`).

## Repository layout

| Path | What |
|---|---|
| `apps/api/kym/` | FastAPI modular monolith (see the module map in [AGENTS.md](AGENTS.md)) |
| `apps/api/alembic/` | Database migrations |
| `apps/web/` | Next.js UI and Playwright specs (`e2e/`) |
| `packages/` | Ontology (Turtle, SHACL, JSON-LD), CNL grammar, generated JSON Schema |
| `policies/`, `standards/` | Versioned bank policy; regulatory and standards data |
| `tests/unit`, `integration`, `security` | Backend tests (see [docs/testing.md](docs/testing.md)) |
| `examples/` | Runnable examples and CNL mandate library |
| `docs/` | Specs, ADRs, security review, risk register, philosophy, reference |

## Workflow

1. **Open an issue first** for anything non-trivial (bug report, feature request, or an attack idea).
2. Branch from `main`: `feat/...`, `fix/...`, `docs/...`, `attack/...`.
3. Make focused changes; add tests *first* when fixing a bug or closing a security finding.
4. Run `make test lint`. For UI changes also `cd apps/web && npx tsc --noEmit && npm run lint && npm run build`, and `make test-e2e` with `make demo` running.
5. Open a PR using the template. CI must pass.

### Commit messages
[Conventional Commits](https://www.conventionalcommits.org/): `feat(policy): ...`, `fix(oauth): ...`, `docs: ...`, `test(redteam): ...`, `security: ...`. Explain *why*.

## What a good PR looks like

* **Security-relevant change?** Add or update an attack in `apps/api/kym/redteam.py` and a regression test. If you find a vulnerability, **do not file it publicly**: see [SECURITY.md](SECURITY.md).
* **New or changed claim in docs?** It must be backed by a command or test. When counts change, update `README.md`, `docs/faq.md`, `llms.txt`, then run `make llms-full` and `make redteam` (`tests/unit/test_docs_consistency.py` enforces this).
* **Standards or regulation text?** Cite an official source URL and a verification date, or mark it *unverified*. Never invent legal requirements; never claim compliance.
* **Schema changes:** edit `apps/api/kym/db.py`, then `cd apps/api && alembic revision --autogenerate -m "..."`; keep the migration test green. Mandate model changes: `make schema` and update `apps/web/lib/types.ts`.
* **Keep simulated things labelled** as simulated in the UI and docs.
* **Do not weaken a baseline or a check to make something pass.** Fix the cause or document the gap.

## Code style

* Python: `ruff` (config in `pyproject.toml`), type hints on public functions, small pure functions for anything on the decision path. No floating-point money. No custom cryptographic primitives.
* TypeScript: strict mode, `eslint`, no `any` without a comment.
* Comments only where the *why* is not obvious.
* Pre-commit hooks: `pip install pre-commit && pre-commit install` (runs ruff, whitespace, secret scan).

## Tests

`docs/testing.md` explains the pyramid, markers, property-based tests, the red-team harness, coverage and Playwright. Keep the suite deterministic; tests that need randomness use Hypothesis with a database-free engine.

## Licensing and sign-off

By contributing you agree your contribution is licensed under the [Apache License 2.0](LICENSE) (inbound = outbound). Add a `Signed-off-by:` line (`git commit -s`) to certify the [Developer Certificate of Origin](https://developercertificate.org/).

## Recognition
Contributors are credited in release notes. Valid security reports are credited in the security review if the reporter wishes.
