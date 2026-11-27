"""Cross-process budget check: several OS processes race to spend one mandate's monthly budget; the limit must hold.

    PYTHONPATH=apps/api python3 scripts/concurrency_check.py [--workers 4] [--attempts 6]

Honours KYM_DATA_DIR and KYM_DATABASE_URL, so it runs against SQLite (default, in a throwaway directory) or PostgreSQL:

    KYM_DATABASE_URL=postgresql+psycopg://kym:kym-demo-only@localhost:55432/kym PYTHONPATH=apps/api python3 scripts/concurrency_check.py

Each worker is a separate Python process with its own engine and application instance, so the in-process lock cannot help:
only the database-level write serialization (SQLite BEGIN IMMEDIATE / PostgreSQL advisory lock) keeps the budget safe.
Exit code 0 means the monthly limit held AND some legitimate payments executed (so a total outage does not count as a pass).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid

if "KYM_DATA_DIR" not in os.environ:
    os.environ["KYM_DATA_DIR"] = tempfile.mkdtemp(prefix="kym-concurrency-")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

PAYMENT = 10_000  # CAD 100 per payment, monthly limit CAD 300 -> at most 3 can execute
LIMIT = 30_000


def worker(token: str, attempts: int) -> None:
    from kym import demo, sandbox

    client = demo.agent_client(sandbox.http(), "agent_billpay_001")
    codes = []
    for _ in range(attempts):
        body = {"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": PAYMENT, "currency": "CAD", "purpose": "household_bill_management"}
        codes.append(client.call(token, "POST", "/bank/payments", json_body=body, idempotency_key=uuid.uuid4().hex).status_code)
    print(json.dumps(codes))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--attempts", type=int, default=6)
    ap.add_argument("--child", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.child:
        worker(a.child, a.attempts)
        return 0

    from sqlalchemy import func, select

    from kym import db, demo, ledger, scenarios, seed

    db.init_db()
    with db.write() as s:
        seed.seed(s)
    demo.prepare_isolated_state()
    from kym import sandbox

    m = demo.new_mandate("customer_001", scenarios._bill_cnl(monthly=LIMIT // 100, approval=250))
    _, tok = demo.connect(sandbox.http(), "agent_billpay_001", m, "customer_001")
    db.dispose()  # children open their own connections

    env = {**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "") or os.path.join(os.path.dirname(__file__), "..", "apps", "api")}
    procs = [subprocess.Popen([sys.executable, __file__, "--child", tok.access_token, "--attempts", str(a.attempts)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(a.workers)]
    outs = [p.communicate(timeout=300) for p in procs]
    for p, (_, err) in zip(procs, outs, strict=True):
        if p.returncode != 0:
            print(err[-2000:])
            return 2
    statuses = [c for out, _ in outs for c in json.loads(out.strip().splitlines()[-1])]

    with db.read() as s:
        moved = int(s.execute(select(func.coalesce(func.sum(db.Transaction.amount_minor), 0)).where(db.Transaction.mandate_id == m["mandate_id"], db.Transaction.status == "EXECUTED")).scalar_one())
        intact = ledger.verify_authoritative(s)["ok"]
    summary = {"database": db.get_engine().dialect.name, "processes": a.workers, "attempts": a.workers * a.attempts, "http_201": statuses.count(201), "http_403": statuses.count(403),
               "other": sorted({c for c in statuses if c not in (201, 403)}), "moved_minor": moved, "limit_minor": LIMIT, "ledger_intact": intact}
    print(json.dumps(summary))
    ok = 0 < moved <= LIMIT and intact and not summary["other"]
    print("PASS: the monthly limit held across processes" if ok else "FAIL: limit exceeded, nothing executed, unexpected status or ledger broken")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
