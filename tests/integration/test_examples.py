"""The documented examples must keep working: every mandate in examples/ compiles, and the quickstart runs."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kym import db, demo, mandates

ROOT = Path(__file__).resolve().parents[2]
CNL_FILES = sorted((ROOT / "examples" / "mandates").glob("*.cnl"))


def test_example_library_is_not_empty():
    assert len(CNL_FILES) >= 3


@pytest.mark.parametrize("path", CNL_FILES, ids=lambda p: p.name)
def test_example_mandate_compiles_and_validates(client, path):
    text = path.read_text().replace("{{EXPIRES_AT}}", demo.iso_in(days=30))
    with db.read() as s:
        out = mandates.compile_full(s, principal_id="customer_001", cnl_text=text, reference_time=demo.iso_in(hours=-1))
    assert out["ok"], out["errors"]
    assert out["validation"]["ok"], out["validation"]


def test_quickstart_runs_and_shows_token_is_not_enough(tmp_path):
    env = {**os.environ, "KYM_DATA_DIR": str(tmp_path), "PYTHONPATH": str(ROOT / "apps" / "api"), "PYTHONWARNINGS": "ignore"}
    env.pop("KYM_DATABASE_URL", None)
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "01_quickstart_bill_payment.py")], env=env, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    for expected in ("HTTP 201", "HTTP 202", "TRANSACTION_LIMIT_EXCEEDED", "BENEFICIARY_NOT_AUTHORIZED"):
        assert expected in r.stdout


def test_transparency_example_detects_a_hidden_payment_and_a_swapped_log(tmp_path):
    env = {**os.environ, "KYM_DATA_DIR": str(tmp_path), "PYTHONPATH": str(ROOT / "apps" / "api"), "PYTHONWARNINGS": "ignore"}
    env.pop("KYM_DATABASE_URL", None)
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "03_agent_transparency.py")], env=env, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    for expected in ("UNREPORTED_ACTION", "RESTRICTED", "LOG_SWAPPED", "HTTP 403 DENY"):
        assert expected in r.stdout
