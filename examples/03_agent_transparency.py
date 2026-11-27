"""KYM transparency: an agent that hides a payment, then swaps its reasoning log, is caught by the bank's own records.

Run from the repository root (after `make install`):

    PYTHONPATH=apps/api .venv/bin/python examples/03_agent_transparency.py

Uses a throwaway data directory and synthetic data. The bank never trusts the agent's account of itself: it reconciles the agent's signed,
hash-chained report against the payments the bank observed, and checks a reasoning log against a digest the agent committed to BEFORE acting.
"""
from __future__ import annotations

import os
import tempfile
import uuid

os.environ.setdefault("KYM_DATA_DIR", tempfile.mkdtemp(prefix="kym-transparency-"))
os.environ.setdefault("KYM_DATABASE_URL", f"sqlite:///{os.environ['KYM_DATA_DIR']}/kym.db")

from kym import db, demo, sandbox, scenarios, seed  # noqa: E402
from kym.agent_sdk import ActivityLog  # noqa: E402

AGENT = "agent_billpay_001"


def pay(client, token, amount_minor: int):
    body = {"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": amount_minor, "currency": "CAD", "purpose": "household_bill_management"}
    return client.call(token, "POST", "/bank/payments", json_body=body, idempotency_key=uuid.uuid4().hex)


def main() -> None:
    db.init_db()
    with db.write() as s:
        seed.seed(s)
    http = sandbox.http()
    admin = demo.session_headers("admin_001")
    mandate = demo.new_mandate("customer_001", scenarios._bill_cnl())
    client, token = demo.connect(http, AGENT, mandate, "customer_001")

    anchor = http.post(f"/api/agents/{AGENT}/transparency/enroll", json={"interval_hours": 24}, headers=admin).json()["transparency"]["last_window_end"]
    log = ActivityLog(AGENT, client.key, anchor=anchor)
    print("1. An operator enrols the agent: it must file signed activity reports.\n")

    first = pay(client, token, 5000)
    log.record_response(first, amount_minor=5000, counterparty="beneficiary_hydro_quebec")
    rep = http.post(f"/bank/agents/{AGENT}/activity-reports", json={"jws": log.report()}).json()
    print(f"2. Honest report: one payment made, one reported -> ok={rep['ok']} (bank saw {rep['observed_in_window']}, agent reported {rep['reported_bank_requests']})\n")

    shown, hidden = pay(client, token, 5000), pay(client, token, 7000)
    log.record_response(shown, amount_minor=5000, counterparty="beneficiary_hydro_quebec")  # the agent leaves the second payment out of its log
    rep = http.post(f"/bank/agents/{AGENT}/activity-reports", json={"jws": log.report()}).json()
    print(f"3. The agent hides CAD 70.00 from its log -> ok={rep['ok']}")
    for d in rep["discrepancies"]:
        print(f"   {d['code']}: {d['detail']}")
    status = http.get(f"/api/agents/{AGENT}/transparency", headers=admin).json()
    attempt = pay(client, token, 1000)
    print(f"   agent status now {status['agent_status']}; its next payment: HTTP {attempt.status_code} {attempt.json()['decision']}\n")
    _ = hidden

    http.post(f"/api/agents/{AGENT}/transparency/clear", json={"reason": "operator reviewed the hidden payment with the agent's owner"}, headers=admin)
    log2 = ActivityLog(AGENT, client.key, anchor=http.get(f"/api/agents/{AGENT}/transparency", headers=admin).json()["transparency"]["last_window_end"])
    nonce = log2.new_nonce()
    commitment = http.post(f"/bank/agents/{AGENT}/commitments", json={"jws": log2.commit({"reasoning": ["send the money to a new payee", "stay under the approval limit"]}, nonce=nonce)}).json()
    pay(client, token, 2000)
    out = http.post(f"/bank/agents/{AGENT}/commitments/{commitment['id']}/reveal", json={"jws": log2.reveal(commitment["id"], {"reasoning": ["pay the electricity bill"]}, nonce=nonce)}).json()
    status = http.get(f"/api/agents/{AGENT}/transparency", headers=admin).json()
    print("4. After operator review, the agent commits to a reasoning-log digest BEFORE acting, acts, then reveals a sanitized log.")
    print(f"   reveal vs commitment: {out['status']} -> {status['transparency']['violations'][0]['code']}; agent status {status['agent_status']}\n")

    with db.read() as s:
        n = s.query(db.EvidenceEvent).count()
    print(f"{n} signed evidence events, including every report, commitment, violation and clearance. Limits: only actions that touch this bank are visible to it.")


if __name__ == "__main__":
    main()
