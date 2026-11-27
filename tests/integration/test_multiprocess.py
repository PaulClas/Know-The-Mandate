"""Budgets must hold when several OS processes (not just threads) write at once. See scripts/concurrency_check.py."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_check(env_extra: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "apps" / "api"), "PYTHONWARNINGS": "ignore", **env_extra}
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "concurrency_check.py")], env=env, capture_output=True, text=True, timeout=600)


def test_budget_holds_across_processes_on_sqlite(tmp_path):
    env = {"KYM_DATA_DIR": str(tmp_path)}
    r = run_check({**env, "KYM_DATABASE_URL": f"sqlite:///{tmp_path}/kym.db"})
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not os.environ.get("KYM_TEST_PG_URL"), reason="set KYM_TEST_PG_URL to an empty PostgreSQL database to run this against PostgreSQL")
def test_budget_holds_across_processes_on_postgresql(tmp_path):
    r = run_check({"KYM_DATA_DIR": str(tmp_path), "KYM_DATABASE_URL": os.environ["KYM_TEST_PG_URL"]})
    assert r.returncode == 0, r.stdout + r.stderr
