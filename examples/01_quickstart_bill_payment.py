"""KYM quickstart: a valid OAuth token is not enough to move money.

Run from the repository root (after `make install`):

    PYTHONPATH=apps/api .venv/bin/python examples/01_quickstart_bill_payment.py

It uses a throwaway data directory, so it never touches your demo database. Everything is synthetic.
What happens:
  1. A customer's bill-paying mandate is compiled from KYM-CNL, approved and activated.
  2. The agent obtains a DPoP-bound OAuth token whose authorization_details name the mandate.
  3. The agent pays Hydro-Quebec (allowed), a larger bill (needs a human), then another biller (denied).
     The token is valid every time; the mandate decides.
"""
from __future__ import annotations

import os
import tempfile
import uuid

os.environ.setdefault("KYM_DATA_DIR", tempfile.mkdtemp(prefix="kym-quickstart-"))
os.environ.setdefault("KYM_DATABASE_URL", f"sqlite:///{os.environ['KYM_DATA_DIR']}/kym.db")

from kym import db, demo, sandbox, seed  # noqa: E402


def pay(client, token, amount_minor: int, beneficiary: str):
    body = {"account_id": "account_001", "beneficiary_id": beneficiary, "amount_minor": amount_minor,
            "currency": "CAD", "purpose": "household_bill_management", "action": "payments.initiate"}
    r = client.call(token, "POST", "/bank/payments", json_body=body, idempotency_key=uuid.uuid4().hex)
    out = r.json()
    codes = [c["reason_code"] if "reason_code" in c else c.get("id") for c in out.get("failed_checks", [])]
    print(f"  CAD {amount_minor / 100:>7.2f} -> {beneficiary:<26} HTTP {r.status_code}  decision={out.get('decision')}  {codes or ''}")


def main() -> None:
    db.init_db()
    with db.write() as s:
        seed.seed(s)
    http = sandbox.http()

    cnl = open(os.path.join(os.path.dirname(__file__), "mandates", "02-bill-payer.cnl")).read()
    cnl = cnl.replace("{{EXPIRES_AT}}", demo.iso_in(days=30))
    mandate = demo.new_mandate("customer_001", cnl)
    print(f"mandate {mandate['mandate_id']} v{mandate['version']} is ACTIVE (digest {mandate['digest'][:16]}...)")

    client, token = demo.connect(http, "agent_billpay_001", mandate, "customer_001")
    print(f"agent holds a valid token with scope: {token.scope}\n")

    pay(client, token, 8_500, "beneficiary_hydro_quebec")     # inside the mandate -> ALLOW
    pay(client, token, 18_000, "beneficiary_hydro_quebec")    # above the approval threshold -> needs a human
    pay(client, token, 30_000, "beneficiary_hydro_quebec")    # above the per-payment cap -> DENY
    pay(client, token, 5_000, "beneficiary_videotron")        # valid token, wrong beneficiary -> DENY

    with db.read() as s:
        n = s.query(db.EvidenceEvent).count()
    print(f"\n{n} signed evidence events recorded; verify with: PYTHONPATH=apps/api KYM_DATA_DIR={os.environ['KYM_DATA_DIR']} .venv/bin/python -m kym.cli verify-ledger")


if __name__ == "__main__":
    main()
