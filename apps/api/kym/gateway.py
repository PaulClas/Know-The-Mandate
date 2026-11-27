"""Policy Enforcement Point and simulated open-banking gateway.

Every agent request follows: identity -> OAuth verification -> mandate verification -> policy evaluation ->
transaction risk -> human approval if required -> payment execution -> evidence ledger.
The PDP and risk engine run inside the same locked transaction as execution, so budgets cannot be bypassed
by concurrent requests and the decision used to execute is evaluated immediately before execution.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select

from . import agents as agents_mod
from . import (
    approvals,
    bank,
    canon,
    clock,
    config,
    db,
    ledger,
    mandates,
    money,
    oauth,
    policy,
    risk,
    security,
    taxonomy,
)
from .metrics import METRICS


@dataclass
class Caller:
    method: str
    url: str
    authorization: str | None = None
    dpop: str | None = None


class BadRequest(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _token_from(caller: Caller) -> str | None:
    if not caller.authorization:
        return None
    parts = caller.authorization.split(None, 1)
    return parts[1].strip() if len(parts) == 2 and parts[0].lower() in ("dpop", "bearer") else None


def public_url(url: str, path: str) -> str:
    return (config.PUBLIC_BASE_URL.rstrip("/") + path) if config.PUBLIC_BASE_URL else url.split("?")[0]


# --------------------------------------------------------------------------- snapshot construction


def _chain(s, content: dict) -> list[dict]:
    chain, seen = [], set()
    lin = content.get("lineage")
    while lin and (lin["parent_mandate_id"], lin["parent_mandate_version"]) not in seen:
        key = (lin["parent_mandate_id"], lin["parent_mandate_version"])
        seen.add(key)
        row = s.get(db.MandateRow, key)
        if not row:
            chain.append({"found": False})
            break
        st = mandates.get_state(s, *key)
        chain.append({"found": True, "content": row.content, "digest": row.digest, "status": st.status, "version": row.version})
        lin = row.content.get("lineage")
    return chain


def _usage(s, principal_id: str, mandate_ids: dict[str, str], now) -> dict:
    """Executed + reserved spend per mandate (including spend through delegated children), by calendar day/month in the budget timezone."""
    txs = s.execute(select(db.Transaction).where(db.Transaction.principal_id == principal_id, db.Transaction.status.in_(bank.BUDGET_STATES))).scalars().all()
    out = {}
    for mid, tz in mandate_ids.items():
        w = policy.window_bounds(now, tz)
        day = month = count = 0
        for t in txs:
            if mid not in t.mandate_chain:
                continue
            at = clock.parse(t.created_at)
            if w["month"][0] <= at < w["month"][1]:
                month += t.amount_minor
                count += 1
                if w["day"][0] <= at < w["day"][1]:
                    day += t.amount_minor
        out[mid] = {"day_minor": day, "month_minor": month, "month_count": count}
    return out


def _risk_ctx(s, req: dict, principal: db.Customer | None, agent: db.Agent | None, payee: db.Payee | None, threshold: int | None, now) -> dict | None:
    if not payee:
        return None
    hist = [-h.amount_minor for h in s.execute(select(db.HistoryEntry).where(db.HistoryEntry.account_id == req["account_id"], db.HistoryEntry.amount_minor < 0)).scalars()]
    done = s.execute(select(db.Transaction).where(db.Transaction.principal_id == req["principal_id"], db.Transaction.status.in_(bank.BUDGET_STATES))).scalars().all()
    epoch = s.get(db.Setting, "risk_epoch")  # DEMO ONLY: scenario runs start a fresh risk window so repeated runs stay independent
    since = clock.parse(epoch.value) if epoch else None
    if since:
        done = [t for t in done if clock.parse(t.created_at) >= since]
    hist += [t.amount_minor for t in done]
    known = {h.payee_id for h in s.execute(select(db.HistoryEntry).where(db.HistoryEntry.account_id == req["account_id"])).scalars() if h.payee_id}
    known |= {t.payee_id for t in done if t.payee_id}
    recent = [{"minutes_ago": (now - clock.parse(t.created_at)).total_seconds() / 60, "amount_minor": t.amount_minor} for t in done]
    window = config.policy_config()["risk"]["parameters"]["auth_failure_window_minutes"]
    fails = [t for t in s.execute(select(db.Transaction).where(db.Transaction.agent_id == (agent.id if agent else ""), db.Transaction.status == "DENIED")).scalars()
             if (now - clock.parse(t.created_at)) <= timedelta(minutes=window) and (since is None or clock.parse(t.created_at) >= since)]
    return {
        "amount_minor": req["amount_minor"], "payee": {"id": payee.id, "kind": payee.kind, "country": payee.country, "category": payee.category, "watchlist": payee.watchlist},
        "customer_country": (principal.jurisdiction.split("-")[0] if principal else "CA"), "history_amounts": hist, "known_payee_ids": sorted(known), "recent_payments": recent,
        "approval_threshold_minor": threshold, "auth_failures": len(fails), "agent_incidents": len(agent.incidents) if agent else 0,
    }


def build_inputs(s, claims: dict | None, facts: dict, req: dict, *, approval_id: str | None, now) -> dict:
    pol = config.policy_config()
    principal = s.get(db.Customer, facts.get("sub") or "") if facts.get("present") else None
    agent = s.execute(select(db.Agent).where(db.Agent.client_id == facts.get("client_id"))).scalar_one_or_none() if facts.get("present") else None
    acct = s.get(db.Account, req["account_id"]) if req.get("account_id") else None
    inputs: dict = {"request": {**{k: v for k, v in req.items() if k not in ("principal_id",)}, "now": clock.iso(now)}, "token": facts, "bank_policy": pol,
                    "customer": None if not principal else {"id": principal.id, "kyc_status": principal.kyc_status, "restrictions": principal.restrictions},
                    "agent": None if not agent else {"id": agent.id, "status": agent.status, "capabilities": agents_mod.capabilities(agent), "client_id": agent.client_id},
                    "account": None if not acct else {"id": acct.id, "owner_id": acct.owner_id, "status": acct.status, "restrictions": acct.restrictions, "currency": acct.currency,
                                                      "controlled_by_principal": bool(principal and acct.owner_id == principal.id), "available_minor": acct.balance_minor - acct.reserved_minor}}
    mid, mver = facts.get("mandate_id"), facts.get("mandate_version")
    row = s.get(db.MandateRow, (mid, mver)) if mid and isinstance(mver, int) else None
    if not row:
        inputs["mandate"], inputs["chain"] = {"found": False}, []
        inputs["usage"], inputs["risk"], inputs["approval"] = {}, None, {"supplied": False, "valid": False, "granted_count": 0, "problem": None}
        return inputs
    st = mandates.get_state(s, mid, mver)
    cur = mandates.active_version(s, mid)
    inputs["mandate"] = {"found": True, "content": row.content, "digest": row.digest, "status": st.status, "version": row.version, "current_version": cur if cur is not None else mandates.get_row(s, mid).version}
    chain = _chain(s, row.content)
    inputs["chain"] = chain
    tz = {row.mandate_id: row.content["validity"]["budget_timezone"]}
    tz.update({c["content"]["mandate_id"]: c["content"]["validity"]["budget_timezone"] for c in chain if c.get("found")})
    inputs["usage"] = _usage(s, row.principal_id, tz, now) if req["action"] in taxonomy.MONEY_MOVING else {}
    thresholds = [m["content"]["obligations"].get("human_approval_above_minor") for m in [{"content": row.content}, *[c for c in chain if c.get("found")]]]
    thresholds = [t for t in thresholds if t is not None]
    payee = s.get(db.Payee, req["counterparty_id"]) if req.get("counterparty_kind") in ("beneficiary", "merchant") and req.get("counterparty_id") else None
    inputs["risk"] = risk.assess(_risk_ctx(s, {**req, "principal_id": row.principal_id}, principal, agent, payee, min(thresholds) if thresholds else None, now), pol) if (req["action"] in taxonomy.MONEY_MOVING and payee) else None
    if req["action"] in taxonomy.MONEY_MOVING and inputs["risk"] is None and req.get("counterparty_kind") == "account":
        inputs["risk"] = {"score": 0, "level": "LOW", "signals": [], "sanctions_hit": False, "thresholds": {}, "disclaimer": risk.DISCLAIMER, "note": "internal transfer between the principal's own accounts"}
    inputs["approval"] = approvals.evaluate_supplied(s, approval_id, req.get("op_hash", ""), row.mandate_id, row.version)
    return inputs


# --------------------------------------------------------------------------- operation normalization


def normalize_operation(s, spec: dict, principal_id: str) -> tuple[dict, dict | None]:
    """Server derives the action class and counterparty facts; the client cannot mislabel an operation."""
    kind = spec["kind"]
    if kind == "READ":
        return {"action": spec["action"], "account_id": spec["account_id"]}, None
    try:
        amount = money.require_minor(spec.get("amount_minor"), "amount_minor")
    except money.MoneyError as e:
        raise BadRequest(str(e)) from e
    ccy = spec.get("currency")
    if not isinstance(ccy, str) or len(ccy) != 3 or not ccy.isupper():
        raise BadRequest("currency must be a 3-letter uppercase ISO 4217 code")
    if not isinstance(spec.get("account_id"), str):
        raise BadRequest("account_id required")
    op = {"account_id": spec["account_id"], "amount_minor": amount, "currency": ccy, "purpose": spec.get("purpose"), "reference": spec.get("reference")}
    if kind in ("PAYMENT", "PREPARE"):
        action = "payments.prepare" if kind == "PREPARE" else spec.get("action", "payments.initiate")
        if kind == "PAYMENT" and action not in taxonomy.PAYMENT_ACTIONS:
            raise BadRequest(f"action must be one of {sorted(taxonomy.PAYMENT_ACTIONS)}")
        if bool(spec.get("beneficiary_id")) == bool(spec.get("merchant_id")):
            raise BadRequest("exactly one of beneficiary_id or merchant_id is required")
        cp_kind, cp_id = ("beneficiary", spec["beneficiary_id"]) if spec.get("beneficiary_id") else ("merchant", spec["merchant_id"])
    else:
        if spec.get("to_account_id"):
            if spec["to_account_id"] == spec["account_id"]:
                raise BadRequest("source and destination accounts must differ")
            dest = s.get(db.Account, spec["to_account_id"])
            internal = bool(dest and dest.owner_id == principal_id)
            action, cp_kind, cp_id = ("transfers.execute" if internal else "transfers.external"), "account", spec["to_account_id"]
        elif spec.get("beneficiary_id"):
            action, cp_kind, cp_id = "transfers.external", "beneficiary", spec["beneficiary_id"]
        else:
            raise BadRequest("to_account_id or beneficiary_id required")
    op.update(action=action, counterparty_kind=cp_kind, counterparty_id=cp_id)
    payee = s.get(db.Payee, cp_id) if cp_kind in ("beneficiary", "merchant") else None
    return op, ({"country": payee.country, "category": payee.category} if payee else None)


# --------------------------------------------------------------------------- core


def _problem(status: int, tx: db.Transaction | None, dec: dict, **extra) -> tuple[int, dict]:
    body = {"status": tx.status if tx else "REJECTED", "transaction_id": tx.id if tx else None, "decision": dec["decision"], "reason_codes": dec["reason_codes"], "policy_version": dec["policy_version"],
            "failed_checks": [c for c in dec["trace"] if c["outcome"] == "FAIL"], "decision_id": extra.pop("decision_id", None), **extra}
    return status, body


def handle(caller: Caller, spec: dict, *, idempotency_key: str | None = None, dry_run: bool = False) -> tuple[int, dict]:
    t0 = time.perf_counter()
    with db.write() as s:
        status, body = _handle(s, caller, spec, idempotency_key, dry_run)
    METRICS.observe("authorization_request", (time.perf_counter() - t0) * 1000)
    return status, body


def _handle(s, caller: Caller, spec: dict, idem: str | None, dry_run: bool) -> tuple[int, dict]:
    corr = f"corr_{uuid.uuid4().hex[:12]}"
    token = _token_from(caller)
    try:
        claims, facts = oauth.verify_access_token(s, token, method=caller.method, url=caller.url, dpop=caller.dpop)
    except oauth.TokenInvalid as e:
        _record_token_rejected(s, corr, str(e), caller.url)
        return 401, {"error": "invalid_token", "error_description": "access token could not be verified"}
    return _process(s, claims, facts, spec, idem, dry_run, corr)


def _record_token_rejected(s, corr: str, reason: str, url: str = "") -> None:
    """Unauthenticated callers must not be able to flood the signed evidence ledger: excess rejections are counted, not written."""
    if security.REJECT_EVENTS.allow("global"):
        ledger.append(s, "TOKEN_REJECTED", actor_id="unauthenticated", actor_type="unknown", correlation_id=corr, payload={"reason": reason[:160], "path": url.split("?")[0][-60:]})
    else:
        METRICS.count("token_rejected_suppressed")


def _process(s, claims: dict, facts: dict, spec: dict, idem: str | None, dry_run: bool, corr: str) -> tuple[int, dict]:
    now = clock.now()
    principal_id = facts["sub"]
    agent = s.execute(select(db.Agent).where(db.Agent.client_id == facts["client_id"])).scalar_one_or_none()
    agent_id = agent.id if agent else (facts.get("actor") or "unknown")
    try:
        op, payee_facts = normalize_operation(s, spec, principal_id)
    except BadRequest as e:
        return 400, {"error": "invalid_request", "error_description": e.message}
    action = op["action"]
    money_moving = action in taxonomy.MONEY_MOVING
    op_h = ""
    if money_moving:
        op_h = bank.op_hash(op, facts.get("mandate_id") or "", facts.get("mandate_version") or 0, principal_id, agent_id)

    if idem is not None and (not isinstance(idem, str) or not 1 <= len(idem) <= 128):
        return 400, {"error": "invalid_request", "error_description": "Idempotency-Key must be 1-128 characters"}
    tx = None
    if idem and money_moving and not dry_run:
        tx = s.execute(select(db.Transaction).where(db.Transaction.agent_id == agent_id, db.Transaction.idempotency_key == idem)).scalar_one_or_none()
        if tx:
            if tx.op_hash != op_h:
                return 409, {"error": "idempotency_key_reused", "error_description": "this Idempotency-Key was used with a different operation payload"}
            if tx.status not in ("PENDING_APPROVAL", "RISK_REVIEW"):
                return _existing(s, tx)
            corr = tx.correlation_id
    if tx is None and not dry_run:
        n = (s.execute(select(db.Transaction.seq).order_by(db.Transaction.seq.desc()).limit(1)).scalar_one_or_none() or 0) + 1
        tx = db.Transaction(id=f"txn_{uuid.uuid4().hex[:14]}", seq=n, kind=spec["kind"], action=action, status="PROPOSED", principal_id=principal_id, agent_id=agent_id,
                            mandate_id=facts.get("mandate_id"), mandate_version=facts.get("mandate_version"), mandate_chain=[], operation=op, op_hash=op_h,
                            amount_minor=op.get("amount_minor", 0), currency=op.get("currency", ""), account_id=op["account_id"],
                            payee_id=op.get("counterparty_id") if op.get("counterparty_kind") in ("beneficiary", "merchant") else None,
                            idempotency_key=idem if money_moving else None, correlation_id=corr, created_at=clock.iso(now), updated_at=clock.iso(now))
        s.add(tx)
        s.flush()
        ledger.append(s, "ACTION_REQUESTED", actor_id=agent_id, actor_type="agent", principal_id=principal_id, agent_id=agent_id, mandate_id=tx.mandate_id, mandate_version=tx.mandate_version,
                      transaction_id=tx.id, correlation_id=corr, payload={"action": action, "account_id": op["account_id"], "amount_minor": op.get("amount_minor"), "currency": op.get("currency"),
                                                                           "counterparty": op.get("counterparty_id"), "op_hash": op_h, "token_jti": facts.get("jti"), "dry_run": dry_run})

    req = {"action": action, "account_id": op["account_id"], "amount_minor": op.get("amount_minor"), "currency": op.get("currency"), "purpose": op.get("purpose"),
           "counterparty_kind": op.get("counterparty_kind"), "counterparty_id": op.get("counterparty_id"),
           "counterparty_country": (payee_facts or {}).get("country"), "counterparty_category": (payee_facts or {}).get("category"), "op_hash": op_h, "principal_id": principal_id}
    inputs = build_inputs(s, claims, facts, req, approval_id=spec.get("approval_id"), now=now)
    t1 = time.perf_counter()
    result = policy.evaluate(inputs)
    METRICS.observe("policy_evaluation", (time.perf_counter() - t1) * 1000)
    inputs_digest = canon.digest(inputs)
    cert = bank.issue_certificate(s, tx.id if tx else None, result, op_h=op_h, inputs_digest=inputs_digest, ttl=config.policy_config()["approval"]["decision_ttl_seconds"])
    dec = db.Decision(id=cert["decision_id"], tx_id=tx.id if tx else None, decision=result["decision"], reason_codes=result["reason_codes"], trace=result["trace"], inputs=inputs, inputs_digest=inputs_digest,
                      policy_version=result["policy_version"], op_hash=op_h, created_at=cert["issued_at"], expires_at=cert["expires_at"], signature=cert["signature"], key_id=cert["key_id"], dry_run=dry_run)
    s.add(dec)
    s.flush()
    METRICS.count(f"decision_{result['decision']}")
    ledger.append(s, "POLICY_EVALUATED", actor_id="meridian-policy-decision-point", actor_type="bank_system", principal_id=principal_id, agent_id=agent_id, mandate_id=facts.get("mandate_id"),
                  mandate_version=facts.get("mandate_version"), transaction_id=tx.id if tx else None, correlation_id=corr, policy_version=result["policy_version"],
                  payload={"decision_id": dec.id, "decision": result["decision"], "reason_codes": result["reason_codes"], "inputs_digest": inputs_digest, "passed": result["passed"], "failed": result["failed"], "dry_run": dry_run})
    if inputs.get("risk") and money_moving:
        r = inputs["risk"]
        ledger.append(s, "RISK_EVALUATED", actor_id="meridian-risk-engine", actor_type="bank_system", principal_id=principal_id, agent_id=agent_id, mandate_id=facts.get("mandate_id"),
                      mandate_version=facts.get("mandate_version"), transaction_id=tx.id if tx else None, correlation_id=corr,
                      payload={"score": r["score"], "level": r["level"], "triggered": [x["id"] for x in r["signals"] if x["triggered"]], "synthetic": True})
    trace_summary = {"decision_id": dec.id, "inputs_digest": inputs_digest}
    if dry_run:
        return 200, {"dry_run": True, "decision": result["decision"], "reason_codes": result["reason_codes"], "trace": result["trace"], "risk": inputs.get("risk"), "policy_version": result["policy_version"], **trace_summary,
                     "approvals_required": result["approvals_required"]}

    tx.decision_id = dec.id
    tx.outcome = result["decision"]
    tx.reason_codes = result["reason_codes"]
    tx.risk = inputs.get("risk") or {}
    tx.updated_at = clock.iso()
    m = inputs.get("mandate") or {}
    if m.get("found"):
        tx.mandate_chain = [m["content"]["mandate_id"], *[c["content"]["mandate_id"] for c in inputs["chain"] if c.get("found")]]
    if result["decision"] == "DENY":
        tx.status = "DENIED"
        if agent:
            agent.stats = {**agent.stats, "payments_denied": agent.stats.get("payments_denied", 0) + (1 if money_moving else 0)}
        ledger.append(s, "ACTION_DENIED", actor_id="meridian-policy-enforcement-point", actor_type="bank_system", principal_id=principal_id, agent_id=agent_id, mandate_id=tx.mandate_id,
                      mandate_version=tx.mandate_version, transaction_id=tx.id, correlation_id=corr, payload={"reason_codes": result["reason_codes"], "decision_id": dec.id, "action": action})
        return _problem(403, tx, result, **trace_summary)
    if result["decision"] == "REFER_TO_RISK_REVIEW":
        tx.status = "RISK_REVIEW"
        return _problem(202, tx, result, **trace_summary)
    if result["decision"] == "REQUIRE_HUMAN_APPROVAL":
        tx.status = "PENDING_APPROVAL"
        existing = s.get(db.Approval, spec["approval_id"]) if spec.get("approval_id") else None
        if existing and existing.op_hash == op_h and existing.status == "PENDING":
            ap = existing
            tx.approval_id = ap.id
        else:
            ap = approvals.create(s, tx, required=result["approvals_required"], reason=next((c["detail"] for c in result["trace"] if c["id"] == "approval.required"), "approval required"),
                                  display=_approval_display(s, tx, op, agent, inputs), policy=config.policy_config())
        return _problem(202, tx, result, approval_id=ap.id, **trace_summary)
    # ALLOW
    if not money_moving:
        tx.status = "COMPLETED"
        return 200, {"status": "COMPLETED", "transaction_id": tx.id, "payment_proposal_id": tx.id if tx.kind == "PREPARE" else None, "decision": "ALLOW", **trace_summary, "_data": True}
    tx.status = "AUTHORIZED"
    try:
        final = bank.execute_authorized(s, tx, cert)
    except bank.EngineError as e:
        tx.status = "FAILED"
        tx.failure_reason = e.code
        return 500, {"status": "FAILED", "error": e.code}
    if spec.get("approval_id") and inputs["approval"].get("valid"):
        approvals.consume(s, spec["approval_id"])
    return (201 if final == "EXECUTED" else 422), {"status": final, "transaction_id": tx.id, "decision": "ALLOW", "reason_codes": [], "failure_reason": tx.failure_reason, **trace_summary,
                                                    "amount_minor": tx.amount_minor, "currency": tx.currency}


def _existing(s, tx: db.Transaction) -> tuple[int, dict]:
    code = {"EXECUTED": 201, "DENIED": 403, "FAILED": 422}.get(tx.status, 200)
    return code, {"status": tx.status, "transaction_id": tx.id, "decision": tx.outcome, "reason_codes": tx.reason_codes, "idempotent_replay": True, "decision_id": tx.decision_id}


def _approval_display(s, tx: db.Transaction, op: dict, agent: db.Agent | None, inputs: dict) -> dict:
    payee = s.get(db.Payee, op.get("counterparty_id")) if op.get("counterparty_kind") in ("beneficiary", "merchant") else None
    acct = s.get(db.Account, op["account_id"])
    m = inputs["mandate"]["content"]
    return {"requesting_agent": agent.display_name if agent else tx.agent_id, "agent_id": tx.agent_id, "agent_operator": agent.declared.get("operating_organization") if agent else None,
            "account": f"{acct.name} ({acct.id})", "action": tx.action, "amount_minor": tx.amount_minor, "currency": tx.currency,
            "beneficiary": f"{payee.name} ({payee.id})" if payee else op.get("counterparty_id"), "mandate": f"{m['mandate_id']} v{m['version']}", "purpose": m["purpose"]}


# --------------------------------------------------------------------------- data endpoints


def read_data(caller: Caller, action: str, account_id: str, *, correlation_hint: str | None = None) -> tuple[int, dict]:
    status, body = handle(caller, {"kind": "READ", "action": action, "account_id": account_id})
    if status != 200 or not body.get("_data"):
        return status, body
    with db.read() as s:
        a = s.get(db.Account, account_id)
        if action == "balances.read":
            return 200, bank.balance_view(a)
        if action == "transactions.read":
            return 200, {"accountId": account_id, "transactions": bank.history_view(s, account_id)}
        return 200, bank.account_view(a)


def list_accounts(caller: Caller) -> tuple[int, dict]:
    """One token/DPoP verification, then an independent PDP evaluation per candidate account."""
    with db.write() as s:
        corr = f"corr_{uuid.uuid4().hex[:12]}"
        try:
            claims, facts = oauth.verify_access_token(s, _token_from(caller), method=caller.method, url=caller.url, dpop=caller.dpop)
        except oauth.TokenInvalid as e:
            _record_token_rejected(s, corr, str(e))
            return 401, {"error": "invalid_token"}
        ids = [a.id for a in s.execute(select(db.Account).where(db.Account.owner_id == facts["sub"])).scalars()]
        allowed, last = [], None
        for aid in ids:
            status, body = _process(s, claims, facts, {"kind": "READ", "action": "accounts.read", "account_id": aid}, None, False, corr)
            if status == 200:
                allowed.append(aid)
            last = (status, body)
        if allowed:
            return 200, {"accounts": [bank.account_view(s.get(db.Account, a)) for a in allowed]}
        return last or (403, {"error": "no accounts authorized"})


def get_payment(caller: Caller, tx_id: str) -> tuple[int, dict]:
    with db.write() as s:
        try:
            claims, facts = oauth.verify_access_token(s, _token_from(caller), method=caller.method, url=caller.url, dpop=caller.dpop)
        except oauth.TokenInvalid:
            return 401, {"error": "invalid_token"}
        if not (facts["actor_ok"] and facts["dpop_ok"] and not facts["revoked"] and not facts["expired"]):
            return 401, {"error": "invalid_token"}
        tx = s.get(db.Transaction, tx_id)
        if not tx or tx.principal_id != facts["sub"] or tx.agent_id != facts["actor"]:
            return 404, {"error": "not_found"}
        return 200, tx_view(tx)


def beneficiaries(caller: Caller) -> tuple[int, dict]:
    """Least-privilege reference data: only payees named in the caller's ACTIVE mandate."""
    with db.write() as s:
        try:
            claims, facts = oauth.verify_access_token(s, _token_from(caller), method=caller.method, url=caller.url, dpop=caller.dpop)
        except oauth.TokenInvalid:
            return 401, {"error": "invalid_token"}
        row = s.get(db.MandateRow, (facts["mandate_id"], facts["mandate_version"]))
        if not (facts["actor_ok"] and facts["dpop_ok"] and not facts["revoked"] and not facts["expired"] and row and mandates.get_state(s, row.mandate_id, row.version).status == "ACTIVE"):
            return 403, {"error": "forbidden"}
        ids = sorted({b for p in row.content["permissions"] for b in p["constraints"].get("allowed_beneficiaries", []) + p["constraints"].get("allowed_merchants", [])})
        return 200, {"beneficiaries": [{"id": p.id, "name": p.name, "country": p.country, "kind": p.kind} for p in (s.get(db.Payee, i) for i in ids) if p]}


def tx_view(tx: db.Transaction) -> dict:
    return {"id": tx.id, "kind": tx.kind, "action": tx.action, "status": tx.status, "principal_id": tx.principal_id, "agent_id": tx.agent_id, "mandate_id": tx.mandate_id, "mandate_version": tx.mandate_version,
            "account_id": tx.account_id, "payee_id": tx.payee_id, "amount_minor": tx.amount_minor, "currency": tx.currency, "decision_id": tx.decision_id, "outcome": tx.outcome,
            "reason_codes": tx.reason_codes, "approval_id": tx.approval_id, "correlation_id": tx.correlation_id, "created_at": tx.created_at, "updated_at": tx.updated_at, "failure_reason": tx.failure_reason,
            "risk": {"score": tx.risk.get("score"), "level": tx.risk.get("level")} if tx.risk else None}


_ = (mandates, timedelta)


def authorize_delegation(s, caller: Caller, parent_mandate_id: str) -> tuple[bool, dict, dict]:
    """An agent asks to delegate part of its authority. The PDP decides whether this mandate allows delegation at all."""
    corr = f"corr_{uuid.uuid4().hex[:12]}"
    try:
        claims, facts = oauth.verify_access_token(s, _token_from(caller), method=caller.method, url=caller.url, dpop=caller.dpop)
    except oauth.TokenInvalid as e:
        _record_token_rejected(s, corr, str(e))
        return False, {"decision": "DENY", "reason_codes": ["INVALID_TOKEN"], "trace": []}, {}
    now = clock.now()
    req = {"action": "mandates.delegate", "account_id": None, "amount_minor": None, "currency": None, "purpose": None, "counterparty_kind": None, "counterparty_id": None, "op_hash": ""}
    inputs = build_inputs(s, claims, facts, req, approval_id=None, now=now)
    result = policy.evaluate(inputs)
    if facts.get("mandate_id") != parent_mandate_id:
        result["decision"] = "DENY"
        result["reason_codes"] = [*result["reason_codes"], "MANDATE_VERSION_MISMATCH"]
        result["trace"].append({"id": "delegation.mandate_binding", "name": "Token bound to the parent mandate", "outcome": "FAIL", "detail": "Token does not reference the mandate being delegated", "reason_code": "MANDATE_VERSION_MISMATCH", "rule": None})
    agent_id = facts.get("actor") or "unknown"
    ledger.append(s, "POLICY_EVALUATED", actor_id="meridian-policy-decision-point", actor_type="bank_system", principal_id=facts["sub"], agent_id=agent_id, mandate_id=facts.get("mandate_id"), mandate_version=facts.get("mandate_version"),
                  correlation_id=corr, payload={"action": "mandates.delegate", "decision": result["decision"], "reason_codes": result["reason_codes"], "inputs_digest": canon.digest(inputs)})
    if result["decision"] != "ALLOW":
        ledger.append(s, "ACTION_DENIED", actor_id="meridian-policy-enforcement-point", actor_type="bank_system", principal_id=facts["sub"], agent_id=agent_id, mandate_id=facts.get("mandate_id"),
                      mandate_version=facts.get("mandate_version"), correlation_id=corr, payload={"action": "mandates.delegate", "reason_codes": result["reason_codes"]})
    return result["decision"] == "ALLOW", result, facts
