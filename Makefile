PY      ?= .venv/bin/python
PIP     ?= uv pip install --python $(PY)
API_DIR := apps/api
export PYTHONPATH := $(API_DIR)
export PYTHONWARNINGS := ignore

.PHONY: concurrency coverage reference examples audit llms-full redteam help install install-web demo api web seed reset-demo migrate test test-unit test-e2e lint verify-ledger benchmark scenarios schema openapi clean

help:
	@echo "make install       - create .venv and install backend dependencies"
	@echo "make demo          - start API (:8000) and web (:3000); seeds synthetic data automatically"
	@echo "make test          - backend tests (unit, integration, security, property-based)"
	@echo "make test-e2e      - Playwright end-to-end tests (needs make demo running)"
	@echo "make scenarios     - run demonstration scenarios A-M headless"
	@echo "make redteam       - 28 attacks vs scope-only, OAuth+static-RAR and KYM; writes docs/redteam/latest.md"
	@echo "make verify-ledger - verify the evidence ledger hash chain, signatures and checkpoints"
	@echo "make benchmark     - measure authorization latency (p50/p95/p99)"
	@echo "make reset-demo    - delete the local demo database and re-seed"
	@echo "make coverage     - backend tests with line+branch coverage report"
	@echo "make examples     - run the quickstart example"
	@echo "make reference    - regenerate docs/reference (API table, reason codes)"
	@echo "make concurrency  - race 4 OS processes for one budget (SQLite; set KYM_DATABASE_URL for PostgreSQL)"
	@echo "make audit        - pip-audit the Python dependencies"
	@echo "make lint          - ruff (backend) and tsc (frontend)"

install:
	uv venv --python 3.13 .venv
	$(PIP) -e ".[dev,postgres]"

install-web:
	cd apps/web && npm install

migrate:
	cd $(API_DIR) && ../../$(PY) -m alembic upgrade head

seed: migrate
	$(PY) -m kym.cli seed

reset-demo:
	$(PY) -m kym.cli reset

api: migrate
	$(PY) -m uvicorn kym.app:app --host 127.0.0.1 --port 8000

web:
	cd apps/web && npm run dev

demo: seed
	@echo "API  -> http://127.0.0.1:8000/docs   Web -> http://localhost:3000"
	@( $(PY) -m uvicorn kym.app:app --host 127.0.0.1 --port 8000 & cd apps/web && npm run dev ; wait )

test:
	$(PY) -m pytest tests

coverage:
	$(PY) -m pytest tests --cov --cov-report=term

examples:
	$(PY) examples/01_quickstart_bill_payment.py

reference:
	$(PY) scripts/build_reference.py

concurrency:
	$(PY) scripts/concurrency_check.py

audit:
	.venv/bin/pip-audit --skip-editable

test-unit:
	$(PY) -m pytest tests/unit

test-e2e:
	cd apps/web && npx playwright test

scenarios:
	$(PY) -m kym.cli scenarios

redteam:
	$(PY) -m kym.cli redteam

llms-full:
	python3 scripts/build_llms_full.py

verify-ledger:
	$(PY) -m kym.cli verify-ledger

benchmark:
	$(PY) -m kym.cli benchmark

schema:
	$(PY) -m kym.cli schema

openapi:
	$(PY) -c "import json; from kym.app import app; print(json.dumps(app.openapi(), indent=2))" > docs/specifications/openapi.json

lint:
	.venv/bin/ruff check apps tests
	cd apps/web && npx tsc --noEmit

clean:
	rm -rf .kym-data .pytest_cache .ruff_cache .hypothesis
