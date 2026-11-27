"""Simulated open banking data + payment execution engine with a double-entry accounting ledger.

The payment engine is NOT reachable by agents. It only executes operations accompanied by a valid,
unexpired, single-use, server-signed authorization decision certificate bound to the exact operation hash.
This is the accounting ledger (movement of money); the KYM Evidence Ledger (exercise of authority) is ledger.py.
Inspired by FDX-style account/balance/transaction resources; payments/transfers are KYM sandbox extensions.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from . import canon, clock, db, keys, ledger

DECISION_DOMAIN = b"KYM-DECISION-V1\x00"
OPEN_STATES = ("PENDING_APPROVAL", "RISK_REVIEW", "RESERVED", "AUTHORIZED")
BUDGET_STATES = ("RESERVED", "EXECUTED")


class EngineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def op_hash(op: dict, mandate_id: str, mandate_version: int, principal_id: str, agent_id: str) -> str:
    return canon.digest({"operation": op, "mandate_id": mandate_id, "mandate_version": mandate_version, "principal_id": principal_id, "agent_id": agent_id})


def issue_certificate(s, tx_id: str | None, decision: dict, *, op_h: str, inputs_digest: str, ttl: int, dry_run: bool = False) -> dict:
    """Server-signed, short-lived authorization decision bound to the exact operation."""
    now = clock.now()
    cert = {"decision_id": f"dec_{canon.sha256_hex(canon.canonical([tx_id, op_h, clock.iso(now)]))[:14]}", "decision": decision["decision"], "op_hash": op_h,
            "policy_version": decision["policy_version"], "inputs_digest": inputs_digest, "issued_at": clock.iso(now), "expires_at": clock.iso(now + timedelta(seconds=ttl))}
    k = keys.decision_key()
    return {**cert, "signature": k.sign(DECISION_DOMAIN + canon.canonical(cert)), "key_id": k.kid}


def verify_certificate(cert: dict, expected_op_hash: str) -> None:
    body = {k: v for k, v in cert.items() if k not in ("signature", "key_id")}
    if not keys.verify_ed25519(keys.decision_key().public_b64u, DECISION_DOMAIN + canon.canonical(body), cert.get("signature", "")):
        raise EngineError("CERT_INVALID", "authorization decision signature invalid")
    if cert["decision"] != "ALLOW":
        raise EngineError("CERT_NOT_ALLOW", "decision is not ALLOW")
    if clock.parse(cert["expires_at"]) <= clock.now():
        raise EngineError("CERT_EXPIRED", "authorization decision expired")
    if cert["op_hash"] != expected_op_hash:
        raise EngineError("CERT_OP_MISMATCH", "decision is not bound to this operation")


def _post(s, tx_id: str, account_id: str, debit: int, credit: int, ccy: str, kind: str = "EXECUTION") -> None:
    s.add(db.Posting(tx_id=tx_id, account_id=account_id, debit_minor=debit, credit_minor=credit, currency=ccy, kind=kind, created_at=clock.iso()))


def execute_authorized(s, tx: db.Transaction, cert: dict) -> str:
    """Reserve funds, then post balanced double-entry lines. Returns the final status. Called under the global write lock."""
    verify_certificate(cert, tx.op_hash)
    dec = s.get(db.Decision, cert["decision_id"])
    if dec is None or dec.consumed_at:
        raise EngineError("CERT_CONSUMED", "authorization decision already used or unknown (single use)")
    dec.consumed_at = clock.iso()
    acct = s.get(db.Account, tx.account_id)
    op = tx.operation
    dest = s.get(db.Account, op["counterparty_id"]) if op.get("counterparty_kind") == "account" else None
    if acct.currency != tx.currency or acct.status != "OPEN":
        return _fail(s, tx, "account unavailable or currency mismatch")
    if dest is not None and (dest.currency != tx.currency or dest.status != "OPEN"):
        return _fail(s, tx, "destination account unavailable or currency mismatch (no FX in this simulator)")
    if acct.balance_minor - acct.reserved_minor < tx.amount_minor:
        return _fail(s, tx, "INSUFFICIENT_FUNDS")
    acct.reserved_minor += tx.amount_minor
    tx.status = "RESERVED"
    s.flush()
    credit_acct = dest.id if dest else f"gl_settlement_{tx.currency}"
    _post(s, tx.id, acct.id, tx.amount_minor, 0, tx.currency)
    _post(s, tx.id, credit_acct, 0, tx.amount_minor, tx.currency)
    s.flush()
    total_d = s.execute(select(func.sum(db.Posting.debit_minor)).where(db.Posting.tx_id == tx.id, db.Posting.kind == "EXECUTION")).scalar_one()
    total_c = s.execute(select(func.sum(db.Posting.credit_minor)).where(db.Posting.tx_id == tx.id, db.Posting.kind == "EXECUTION")).scalar_one()
    if total_d != total_c:
        raise EngineError("UNBALANCED", "double-entry invariant violated")
    acct.reserved_minor -= tx.amount_minor
    acct.balance_minor -= tx.amount_minor
    target = dest or s.get(db.Account, credit_acct)
    target.balance_minor += tx.amount_minor
    tx.status = "EXECUTED"
    tx.updated_at = clock.iso()
    s.flush()
    ledger.append(s, "PAYMENT_EXECUTED", actor_id="meridian-payment-engine", actor_type="bank_system", principal_id=tx.principal_id, agent_id=tx.agent_id, mandate_id=tx.mandate_id,
                  mandate_version=tx.mandate_version, transaction_id=tx.id, correlation_id=tx.correlation_id,
                  payload={"decision_id": cert["decision_id"], "op_hash": tx.op_hash, "amount_minor": tx.amount_minor, "currency": tx.currency, "debit_account": acct.id, "credit_account": credit_acct})
    agent = s.get(db.Agent, tx.agent_id)
    agent.stats = {**agent.stats, "payments_executed": agent.stats.get("payments_executed", 0) + 1}
    return "EXECUTED"


def _fail(s, tx: db.Transaction, reason: str) -> str:
    tx.status = "FAILED"
    tx.failure_reason = reason
    tx.updated_at = clock.iso()
    ledger.append(s, "PAYMENT_FAILED", actor_id="meridian-payment-engine", actor_type="bank_system", principal_id=tx.principal_id, agent_id=tx.agent_id, mandate_id=tx.mandate_id,
                  mandate_version=tx.mandate_version, transaction_id=tx.id, correlation_id=tx.correlation_id, payload={"reason": reason, "op_hash": tx.op_hash})
    return "FAILED"


def reverse(s, tx_id: str, *, actor_id: str, reason: str) -> dict:
    tx = s.get(db.Transaction, tx_id)
    if not tx or tx.status != "EXECUTED":
        raise EngineError("NOT_REVERSIBLE", "only EXECUTED payments can be reversed")
    for p in s.execute(select(db.Posting).where(db.Posting.tx_id == tx_id, db.Posting.kind == "EXECUTION")).scalars().all():
        _post(s, tx_id, p.account_id, p.credit_minor, p.debit_minor, p.currency, "REVERSAL")
        acct = s.get(db.Account, p.account_id)
        acct.balance_minor += p.debit_minor - p.credit_minor
    tx.status = "REVERSED"
    tx.updated_at = clock.iso()
    ledger.append(s, "PAYMENT_FAILED", actor_id=actor_id, actor_type="bank_operator", principal_id=tx.principal_id, agent_id=tx.agent_id, mandate_id=tx.mandate_id, mandate_version=tx.mandate_version,
                  transaction_id=tx.id, correlation_id=tx.correlation_id, payload={"reversal": True, "reason": reason})
    return {"id": tx_id, "status": "REVERSED"}


def cancel_pending(s, mandate_ids: list[str], *, reason: str, actor_id: str) -> list[str]:
    """On revocation: cancel pending approvals/reviews and release reservations. Executed payments are NOT reversed."""
    out = []
    for tx in s.execute(select(db.Transaction).where(db.Transaction.mandate_id.in_(mandate_ids), db.Transaction.status.in_(OPEN_STATES))).scalars().all():
        if tx.status == "RESERVED":
            s.get(db.Account, tx.account_id).reserved_minor -= tx.amount_minor
        tx.status = "CANCELLED"
        tx.failure_reason = reason
        tx.updated_at = clock.iso()
        if tx.approval_id:
            ap = s.get(db.Approval, tx.approval_id)
            if ap and ap.status in ("PENDING", "APPROVED"):
                ap.status = "CANCELLED"
        ledger.append(s, "ACTION_DENIED", actor_id=actor_id, actor_type="bank_system", principal_id=tx.principal_id, agent_id=tx.agent_id, mandate_id=tx.mandate_id, mandate_version=tx.mandate_version,
                      transaction_id=tx.id, correlation_id=tx.correlation_id, payload={"cancelled": True, "reason": reason})
        out.append(tx.id)
    return out


# --------------------------------------------------------------------------- open-banking style resources


def account_view(a: db.Account) -> dict:
    return {"accountId": a.id, "nickname": a.name, "accountType": a.type, "currency": a.currency, "status": a.status}


def balance_view(a: db.Account) -> dict:
    return {"accountId": a.id, "currency": a.currency, "currentBalanceMinor": a.balance_minor, "reservedMinor": a.reserved_minor, "availableBalanceMinor": a.balance_minor - a.reserved_minor}


def history_view(s, account_id: str, limit: int = 100) -> list[dict]:
    rows = s.execute(select(db.HistoryEntry).where(db.HistoryEntry.account_id == account_id).order_by(db.HistoryEntry.posted_at.desc()).limit(limit)).scalars()
    out = [{"transactionId": h.id, "postedAt": h.posted_at, "description": h.description, "amountMinor": h.amount_minor, "currency": h.currency, "category": h.category, "payeeId": h.payee_id} for h in rows]
    execd = s.execute(select(db.Transaction).where(db.Transaction.account_id == account_id, db.Transaction.status == "EXECUTED")).scalars()
    out += [{"transactionId": t.id, "postedAt": t.updated_at, "description": f"Agent payment ({t.action})", "amountMinor": -t.amount_minor, "currency": t.currency, "category": "agent_payment", "payeeId": t.payee_id} for t in execd]
    return sorted(out, key=lambda x: x["postedAt"], reverse=True)[:limit]


def trial_balance(s) -> dict:
    d = s.execute(select(func.coalesce(func.sum(db.Posting.debit_minor), 0))).scalar_one()
    c = s.execute(select(func.coalesce(func.sum(db.Posting.credit_minor), 0))).scalar_one()
    return {"debits_minor": d, "credits_minor": c, "balanced": d == c}
