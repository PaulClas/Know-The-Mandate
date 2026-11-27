from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.environ.get("KYM_DATA_DIR", ROOT / ".kym-data"))
DATABASE_URL = os.environ.get("KYM_DATABASE_URL", f"sqlite:///{DATA_DIR / 'kym.db'}")

ISSUER = os.environ.get("KYM_ISSUER", "https://bank.example")
API_AUDIENCE = f"{ISSUER}/api"
PAYMENTS_RESOURCE = f"{ISSUER}/api/payments"
KYM_NS = "https://example.org/kym/v1#"
CLAIM_NS = "https://example.org/kym/"
SCHEMA_VERSION = "1.0.0"
ONTOLOGY_VERSION = "1.0.0"
POLICY_VERSION = "bank-policy-1.0.0"
CNL_VERSION = "1.0.0"
BUDGET_TZ_DEFAULT = "America/Toronto"
ACCESS_TOKEN_TTL_SECONDS = 300
PUBLIC_BASE_URL = os.environ.get("KYM_PUBLIC_BASE_URL", "")  # set when behind a proxy so DPoP htu matches
ENV = os.environ.get("KYM_ENV", "demo")  # "demo" enables no-password sessions and destructive reset; anything else fails closed
RATE_LIMIT_PER_MIN = int(os.environ.get("KYM_RATE_LIMIT_PER_MIN", "1200"))
FAILED_AUTH_PER_MIN = int(os.environ.get("KYM_FAILED_AUTH_PER_MIN", "20"))
REJECT_EVENTS_PER_MIN = int(os.environ.get("KYM_REJECT_EVENTS_PER_MIN", "60"))
_LEGACY_DEFAULT_SECRET = "demo-only-session-secret-do-not-use-in-production"


def is_demo() -> bool:
    return ENV == "demo"


def session_secret() -> str:
    """Per-install random secret (file, mode 0600) unless explicitly configured. Never a constant shipped in source."""
    import secrets as _secrets

    env = os.environ.get("KYM_DEMO_SESSION_SECRET")
    if env and env != _LEGACY_DEFAULT_SECRET:
        return env
    ensure_dirs()
    p = DATA_DIR / "keys" / "session-secret"
    if not p.exists():
        p.write_text(_secrets.token_hex(32))
        p.chmod(0o600)
    return p.read_text().strip()

PACKAGES = ROOT / "packages"
POLICIES = ROOT / "policies"
STANDARDS = ROOT / "standards"


@lru_cache
def policy_config(version: str = POLICY_VERSION) -> dict:
    path = POLICIES / f"{version}.json"
    if not path.exists():
        raise KeyError(f"unknown policy version {version}")
    return json.loads(path.read_text())


def ensure_dirs() -> None:
    (DATA_DIR / "keys").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "checkpoints").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "exports").mkdir(parents=True, exist_ok=True)
