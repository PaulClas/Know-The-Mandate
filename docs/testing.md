# Testing

KYM's central claim is testable, so the test suite is part of the product. All numbers below were measured on 2026-11-27 on a developer laptop; re-run to refresh.

## Layers

| Layer | Location | Tests | What it proves | Command |
|---|---|---|---|---|
| Unit | [tests/unit](../tests/unit) | 100 | Policy decision point as a pure function, CNL compiler, ontology/SHACL, ledger primitives, docs-consistency | `make test-unit` |
| Property-based | [tests/unit/test_properties.py](../tests/unit/test_properties.py) (Hypothesis) | 5 (in unit) | Money arithmetic and attenuation invariants hold for generated inputs | `make test-unit` |
| Integration | [tests/integration](../tests/integration) | 87 | Real FastAPI app and database: OAuth/DPoP flow, enforcement, scenarios A to M, migrations, examples | `make test` |
| Security / red-team | [tests/security](../tests/security) | 51 | Regression tests for fixed findings F-01 to F-21 and the 23-attack harness | `make test` |
| End to end (browser) | [apps/web/e2e](../apps/web/e2e) | 30 Playwright specs | UI pages, scenario runner, customer approval flow, discoverability metadata | `make test-e2e` (needs `make demo` running) |
| Multi-process | [scripts/concurrency_check.py](../scripts/concurrency_check.py) | 1 SQLite test (+1 PostgreSQL, opt-in) | Four OS processes race one budget; the limit must hold and some payments must execute | `make concurrency` |
| Docker smoke | [.github/workflows/ci.yml](../.github/workflows/ci.yml) | CI job | Compose stack builds, becomes healthy, passes scenarios and red-team | `docker compose up --build` |

Total backend: **238 tests** (237 run by default; the PostgreSQL multi-process test is skipped unless `KYM_TEST_PG_URL` points at an empty database) (`make test`).

## Coverage

```bash
make coverage
```

Measured: **82% of statements and branches** across `apps/api/kym` (5,638 statements, 1,620 branches), excluding `cli.py` and `sparql_worker.py`, which run as subprocesses and are exercised by CLI runs instead of in-process.

Highest value modules are well covered: `policy.py` 88%, `ledger.py` 84%, `security.py` 96%, `ontology_service.py` 94%, `db.py` 97%. Weakest: `sandbox.py` 55% (the demo agent simulator), `bank.py` 67%, `adapters.py` 68%. Coverage is a floor for what ran, not proof of correctness. Many important behaviours (for example the red-team checks) are asserted by outcome, not by line.

## The red-team harness is also a test

`make redteam` runs 23 attacks against three designs (a scope-only bank, OAuth with static RAR, and KYM) and writes [redteam/latest.md](redteam/latest.md). [tests/security/test_redteam.py](../tests/security/test_redteam.py) asserts that KYM blocks every applicable attack, that the baselines fail where claimed, and that the one in-mandate malicious action is documented as unstoppable. It is self-assessed: the attacks were written by the author of the defence.

## Determinism

The decision point is a pure function of a JSON snapshot, so a recorded decision can be replayed and must produce the same result. Tests build snapshots without a database ([tests/helpers.py](../tests/helpers.py)). Demo/test-only isolation (`demo.prepare_isolated_state`) resets the risk window and tops up balances between tests so ordering does not matter.

## Lint, types and docs checks

```bash
make lint            # ruff (backend) + tsc (frontend)
make llms-full       # regenerate llms-full.txt after editing README/FAQ/risk/security docs
make reference       # regenerate docs/reference/*; a test fails if they are stale
```

[tests/unit/test_docs_consistency.py](../tests/unit/test_docs_consistency.py) fails when documented numbers (attack counts, finding counts), `llms.txt` links, generated files or the "experimental / synthetic" disclaimers drift from the code.

## Writing a new test

* Policy rule change: add a case in `tests/unit/test_policy.py` using `make_mandate()` / `make_inputs()`.
* New API behaviour: add to `tests/integration`, using the `client` fixture and `demo.new_mandate` / `demo.connect`.
* New attack idea: add it to [redteam.py](../apps/api/kym/redteam.py) (see [CONTRIBUTING](../CONTRIBUTING.md)) and keep the honest-gap rule: if KYM cannot stop it, record it as a gap.
