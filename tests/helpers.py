"""Pure builders for PDP tests. No database: the policy engine is a pure function of a JSON snapshot."""
from __future__ import annotations

import copy
from datetime import timedelta

from kym import canon, clock, config, schemas

POLICY = config.policy_config()


def ts(days: float = 0) -> str:
    return clock.iso(clock.now() + timedelta(days=days)).split(".")[0] + "Z"


def make_mandate(**over) -> dict:
    base = {
        "mandate_id": "mdt_t1", "principal": {"id": "customer_001", "type": "individual"},
        "mandatary": {"agent_id": "agent_finance_001", "operator_id": "organization_001", "client_id": "client_finance_001"},
        "purpose": "household_bill_management", "currency": "CAD",
        "permissions": [
            {"action": "balances.read", "resources": ["account_001"], "constraints": {}},
            {"action": "payments.initiate", "resources": ["account_001"], "constraints": {"currency": "CAD", "maximum_amount_minor": 25000, "allowed_beneficiaries": ["beneficiary_hydro_quebec"]}},
        ],
        "prohibitions": ["transfers.external"], "aggregate_constraints": {"maximum_daily_amount_minor": 25000, "maximum_monthly_amount_minor": 50000},
        "obligations": {"human_approval_above_minor": 10000, "required_approvals": 1, "notify_customer": True}, "delegation": {"allowed": False, "maximum_depth": 0},
        "validity": {"not_before": ts(-1), "expires_at": ts(30), "budget_timezone": "America/Toronto"}, "jurisdictions": ["CA", "CA-QC"], "policy_version": config.POLICY_VERSION,
    }
    base.update(over)
    return schemas.Mandate.model_validate(base).model_dump()


def snap(content: dict, status: str = "ACTIVE") -> dict:
    return {"found": True, "content": content, "digest": canon.digest(content), "status": status, "version": content["version"], "current_version": content["version"]}


def make_inputs(mandate: dict, *, chain: tuple = (), action="payments.initiate", amount=5000, beneficiary="beneficiary_hydro_quebec", status="ACTIVE", usage=None,
                risk_score=0, approval=None, account_id="account_001", currency="CAD", purpose=None, token_over=None, now=None, sanctions=False) -> dict:
    m = snap(mandate, status)
    token = {"present": True, "signature_valid": True, "expired": False, "revoked": False, "audience_ok": True, "dpop_ok": True, "actor_ok": True, "scopes": ["balances.read", "payments.initiate", "transfers.initiate", "accounts.read", "transactions.read", "payments.prepare"],
             "jti": "tok_t", "client_id": mandate["mandatary"]["client_id"], "sub": mandate["principal"]["id"], "mandate_id": mandate["mandate_id"], "mandate_version": mandate["version"], "mandate_hash": m["digest"], "actor": mandate["mandatary"]["agent_id"]}
    token.update(token_over or {})
    money_moving = action in ("payments.initiate", "payments.pay_invoice", "purchases.goods", "transfers.execute", "transfers.external")
    return {
        "request": {"action": action, "account_id": account_id, "amount_minor": amount if money_moving else None, "currency": currency if money_moving else None, "purpose": purpose or (mandate["purpose"] if money_moving else None),
                    "counterparty_kind": "beneficiary" if money_moving else None, "counterparty_id": beneficiary if money_moving else None, "counterparty_country": "CA", "counterparty_category": "4900", "op_hash": "h", "now": (now or clock.iso())},
        "token": token, "bank_policy": POLICY,
        "customer": {"id": mandate["principal"]["id"], "kyc_status": "VERIFIED", "restrictions": []},
        "agent": {"id": mandate["mandatary"]["agent_id"], "status": "VERIFIED", "capabilities": ["balances.read", "payments.initiate", "payments.pay_invoice", "transfers.external", "transfers.execute", "mandates.delegate", "accounts.read", "transactions.read", "payments.prepare"], "client_id": mandate["mandatary"]["client_id"]},
        "account": {"id": account_id, "owner_id": mandate["principal"]["id"], "status": "OPEN", "restrictions": [], "currency": "CAD", "controlled_by_principal": True, "available_minor": 10**9},
        "mandate": m, "chain": [snap(c, "ACTIVE") if isinstance(c, dict) and "permissions" in c else c for c in chain],
        "usage": usage or {}, "risk": {"score": risk_score, "level": "LOW", "signals": [], "sanctions_hit": sanctions} if money_moving else None,
        "approval": approval or {"supplied": False, "valid": False, "granted_count": 0, "problem": None},
    }


def mutate(inputs: dict, path: str, value):
    out = copy.deepcopy(inputs)
    cur = out
    keys = path.split(".")
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    cur[keys[-1]] = value
    return out
