"""Bank-controlled human approval. Bound to the SHA-256 of the exact canonical operation; single use; expiring."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from . import canon, clock, config, db, keys, kyc, ledger

APPROVAL_DOMAIN = b"KYM-APPROVAL-V1\x00"
ASSURANCE = "DEMO_SIMULATED_SESSION (server-held demo key; production: passkey/WebAuthn step-up)"


class ApprovalError(ValueError):
    def __init__(self, message: str, code: str = "APPROVAL_ERROR"):
        super().__init__(message)
        self.code = code


def eligible_approvers(s, principal_id: str, account_id: str | None) -> list[str]:
    c = s.get(db.Customer, principal_id)
    if c and c.type == "business":
        return kyc.signatories(s, principal_id, account_id)
    return [principal_id]


def create(s, tx: db.Transaction, *, required: int, reason: str, display: dict, policy: dict) -> db.Approval:
    ap = db.Approval(
        id=f"apr_{uuid.uuid4().hex[:12]}", tx_id=tx.id, op_hash=tx.op_hash, mandate_id=tx.mandate_id, mandate_version=tx.mandate_version, principal_id=tx.principal_id,
        required_count=required, eligible_approvers=eligible_approvers(s, tx.principal_id, tx.account_id), grants=[], status="PENDING", reason=reason,
        created_at=clock.iso(), expires_at=clock.iso(clock.now() + timedelta(seconds=policy["approval"]["approval_ttl_seconds"])), display=display,
    )
    s.add(ap)
    s.flush()
    tx.approval_id = ap.id
    ledger.append(s, "HUMAN_APPROVAL_REQUESTED", actor_id="meridian-policy-enforcement-point", actor_type="bank_system", principal_id=tx.principal_id, agent_id=tx.agent_id, mandate_id=tx.mandate_id,
                  mandate_version=tx.mandate_version, transaction_id=tx.id, correlation_id=tx.correlation_id,
                  payload={"approval_id": ap.id, "op_hash": tx.op_hash, "required_approvals": required, "expires_at": ap.expires_at, "reason": reason})
    return ap


def _expire_if_due(s, ap: db.Approval) -> None:
    if ap.status in ("PENDING", "APPROVED") and clock.parse(ap.expires_at) <= clock.now():
        ap.status = "EXPIRED"
        s.flush()


def _grant_message(g: dict) -> bytes:
    return APPROVAL_DOMAIN + canon.canonical({k: g[k] for k in ("approval_id", "op_hash", "mandate_id", "mandate_version", "approver_id", "decision", "at")})


def decide(s, approval_id: str, approver_id: str, decision: str) -> dict:
    ap = s.get(db.Approval, approval_id)
    if not ap:
        raise ApprovalError("approval not found", "NOT_FOUND")
    _expire_if_due(s, ap)
    if ap.status != "PENDING":
        raise ApprovalError(f"approval is {ap.status}", "NOT_PENDING")
    if approver_id not in ap.eligible_approvers:
        raise ApprovalError("approver is not an authorized signatory for this account", "NOT_AUTHORIZED")
    if any(g["approver_id"] == approver_id for g in ap.grants):
        raise ApprovalError("each approver may decide only once (separation of duties)", "DUPLICATE_APPROVER")
    tx = s.get(db.Transaction, ap.tx_id)
    g = {"approval_id": ap.id, "op_hash": ap.op_hash, "mandate_id": ap.mandate_id, "mandate_version": ap.mandate_version, "approver_id": approver_id, "decision": decision, "at": clock.iso()}
    k = keys.customer_consent_key(approver_id)
    g.update(signature=k.sign(_grant_message(g)), key_id=k.kid, assurance=ASSURANCE)
    ap.grants = [*ap.grants, g]
    if decision == "REJECT":
        ap.status = "REJECTED"
        tx.status = "CANCELLED"
        tx.failure_reason = "rejected by human approver"
        ledger.append(s, "HUMAN_APPROVAL_REJECTED", actor_id=approver_id, actor_type="human_approver", principal_id=ap.principal_id, agent_id=tx.agent_id, mandate_id=ap.mandate_id,
                      mandate_version=ap.mandate_version, transaction_id=tx.id, correlation_id=tx.correlation_id, payload={"approval_id": ap.id, "op_hash": ap.op_hash})
    else:
        granted = sum(1 for x in ap.grants if x["decision"] == "APPROVE")
        if granted >= ap.required_count:
            ap.status = "APPROVED"
        ledger.append(s, "HUMAN_APPROVAL_GRANTED", actor_id=approver_id, actor_type="human_approver", principal_id=ap.principal_id, agent_id=tx.agent_id, mandate_id=ap.mandate_id,
                      mandate_version=ap.mandate_version, transaction_id=tx.id, correlation_id=tx.correlation_id,
                      payload={"approval_id": ap.id, "op_hash": ap.op_hash, "granted": granted, "required": ap.required_count, "signature_key_id": k.kid, "assurance": "DEMO_SIMULATED_SESSION"})
    s.flush()
    return to_dict(ap)


def evaluate_supplied(s, approval_id: str | None, op_hash: str, mandate_id: str, mandate_version: int) -> dict:
    """Facts for the PDP: is the supplied approval valid for THIS exact operation right now? Verifies signatures again."""
    if not approval_id:
        return {"supplied": False, "valid": False, "granted_count": 0, "problem": None}
    ap = s.get(db.Approval, approval_id)
    if not ap:
        return {"supplied": True, "valid": False, "granted_count": 0, "problem": "approval not found"}
    _expire_if_due(s, ap)
    problem = None
    if ap.op_hash != op_hash:
        problem = "approval was granted for a different operation payload (transaction substitution prevented)"
    elif (ap.mandate_id, ap.mandate_version) != (mandate_id, mandate_version):
        problem = "approval is bound to a different mandate version"
    elif ap.status == "CONSUMED":
        problem = "approval already used (replay prevented)"
    elif ap.status == "EXPIRED":
        problem = "approval expired"
    elif ap.status == "REJECTED":
        problem = "approval was rejected"
    elif ap.status != "APPROVED":
        problem = f"approval not yet complete ({sum(1 for g in ap.grants if g['decision'] == 'APPROVE')} of {ap.required_count})"
    valid_grants = 0
    for g in ap.grants:
        if g["decision"] != "APPROVE":
            continue
        if keys.verify_ed25519(keys.customer_consent_key(g["approver_id"]).public_b64u, _grant_message(g), g["signature"]) and g["op_hash"] == op_hash and g["approver_id"] in ap.eligible_approvers:
            valid_grants += 1
    distinct = len({g["approver_id"] for g in ap.grants if g["decision"] == "APPROVE"})
    count = min(valid_grants, distinct)
    if problem is None and count < ap.required_count:
        problem = "approval signatures could not be verified"
    return {"supplied": True, "valid": problem is None, "granted_count": count, "problem": problem, "approval_id": ap.id}


def consume(s, approval_id: str) -> None:
    ap = s.get(db.Approval, approval_id)
    ap.status = "CONSUMED"
    ap.consumed_at = clock.iso()
    s.flush()


def to_dict(ap: db.Approval) -> dict:
    return {
        "id": ap.id, "tx_id": ap.tx_id, "status": ap.status, "op_hash": ap.op_hash, "mandate_id": ap.mandate_id, "mandate_version": ap.mandate_version, "principal_id": ap.principal_id,
        "required_approvals": ap.required_count, "eligible_approvers": ap.eligible_approvers, "grants": [{k: v for k, v in g.items() if k != "signature"} for g in ap.grants],
        "reason": ap.reason, "created_at": ap.created_at, "expires_at": ap.expires_at, "display": ap.display, "consumed_at": ap.consumed_at,
        "binding": "SHA-256 of canonical operation (account, beneficiary, amount, currency, purpose, reference) + mandate id/version", "assurance": ASSURANCE,
    }


def list_for(s, user_id: str, role: str) -> list[dict]:
    out = []
    for ap in s.execute(select(db.Approval).order_by(db.Approval.created_at.desc())).scalars():
        _expire_if_due(s, ap)
        if role in ("admin", "investigator") or user_id == ap.principal_id or user_id in ap.eligible_approvers:
            out.append(to_dict(ap))
    return out


_ = config
