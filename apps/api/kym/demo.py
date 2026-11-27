"""Helpers shared by the scenario runner, sandbox and tests. They use the real service layer and HTTP surface.

Actor `demo_scenario_runner` performs the *customer* approval step on behalf of seeded synthetic customers.
Evidence events record it so the demonstration is never mistaken for real customer consent.
"""
from __future__ import annotations

from datetime import timedelta

from . import agents as agents_mod
from . import clock, cnl, db, mandates
from .agent_sdk import AgentClient, TokenSet
from .auth import login

RUNNER = "demo_scenario_runner"


def iso_in(days: float = 0, hours: float = 0) -> str:
    return clock.iso(clock.now() + timedelta(days=days, hours=hours)).split(".")[0] + "Z"


def new_mandate(principal_id: str, cnl_text: str, *, approver_id: str | None = None, activate: bool = True, reference_time: str | None = None) -> dict:
    """compile -> propose -> customer approval -> activate. Raises on any failure."""
    with db.write() as s:
        c = mandates.compile_full(s, principal_id=principal_id, cnl_text=cnl_text, reference_time=reference_time or iso_in(hours=-1))
        if not c["ok"]:
            raise RuntimeError(f"compile failed: {c['errors']}")
        res = mandates.propose(s, c["mandate"], created_by=RUNNER, actor_type="demo_scenario_runner", artifacts={"normalized_cnl": c["normalized_cnl"]})
        if res["status"] != "PENDING_CUSTOMER_APPROVAL":
            raise RuntimeError(f"mandate rejected: {res['validation']}")
        if activate:
            mandates.approve(s, res["mandate_id"], res["version"], approver_id=approver_id or principal_id, presented_digest=res["digest"], actor_type="customer_simulated_by_runner")
            res = mandates.activate(s, res["mandate_id"], res["version"], actor_id=RUNNER, actor_type="demo_scenario_runner")
        return res


def agent_client(http, agent_id: str) -> AgentClient:
    with db.read() as s:
        a = s.get(db.Agent, agent_id)
        client_id = a.client_id
    return AgentClient.for_demo_agent(http, agent_id, client_id)


def customer_approver(http, customer_id: str):
    """Returns the bank-hosted approval callback used by the OAuth flow (the customer signs in to the bank, not to the agent)."""
    token = login(customer_id)

    def approve(request_uri: str) -> dict:
        r = http.post("/oauth/authorize/approve", json={"request_uri": request_uri}, headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            raise RuntimeError(f"authorize approve failed: {r.status_code} {r.text}")
        return r.json()

    return approve


def connect(http, agent_id: str, mandate: dict, customer_id: str) -> tuple[AgentClient, TokenSet]:
    from . import cnl as cnl_mod

    client = agent_client(http, agent_id)
    details = cnl_mod.authorization_details(mandate["content"])
    return client, client.authorize(details, customer_approver(http, customer_id))


def session_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {login(user_id)}"}


_ = (agents_mod, cnl)


def child_from_parent(parent: dict, child_agent: db.Agent, *, max_amount_minor: int, monthly_minor: int | None = None) -> dict:
    """Builds a candidate child mandate from a parent. The bank still validates strict attenuation; a larger number WILL be rejected."""
    c = {k: v for k, v in parent.items() if k not in ("lineage",)}
    c["mandate_id"] = "mdt_DRAFT"
    c["version"] = 1
    c["mandatary"] = {"agent_id": child_agent.id, "operator_id": child_agent.declared["operator_id"], "client_id": child_agent.client_id}
    perms = []
    for p in parent["permissions"]:
        if p["action"] in ("payments.initiate", "payments.pay_invoice"):
            cons = {**p["constraints"], "maximum_amount_minor": max_amount_minor}
            perms.append({**p, "constraints": cons})
    c["permissions"] = perms or parent["permissions"]
    c["delegation"] = {"allowed": False, "maximum_depth": 0}
    c["prohibitions"] = sorted({*parent["prohibitions"], "mandates.delegate"})
    agg = dict(parent["aggregate_constraints"])
    if monthly_minor is not None:
        agg["maximum_monthly_amount_minor"] = monthly_minor
    c["aggregate_constraints"] = agg
    return c


def prepare_isolated_state() -> None:
    """DEMO/TEST ONLY: start a fresh risk window and top up synthetic balances so repeated scenario runs stay independent.

    Balances are topped up with a balanced double-entry pair (kind DEMO_TOPUP) so the trial balance still balances.
    Never used by the enforcement path; the epoch only narrows the lookback of synthetic risk signals.
    """
    from . import seed

    with db.write() as s:
        row = s.get(db.Setting, "risk_epoch")
        if row:
            row.value = clock.iso()
        else:
            s.add(db.Setting(key="risk_epoch", value=clock.iso()))
        for aid, owner, _name, _typ, ccy, bal, _ref in seed.ACCOUNTS:
            if owner is None:
                continue
            a = s.get(db.Account, aid)
            if a and a.balance_minor < bal:
                diff = bal - a.balance_minor
                gl = s.get(db.Account, f"gl_settlement_{ccy}")
                tx_id = f"demo_topup_{aid}_{clock.iso()}"
                s.add(db.Posting(tx_id=tx_id, account_id=gl.id, debit_minor=diff, credit_minor=0, currency=ccy, kind="DEMO_TOPUP", created_at=clock.iso()))
                s.add(db.Posting(tx_id=tx_id, account_id=aid, debit_minor=0, credit_minor=diff, currency=ccy, kind="DEMO_TOPUP", created_at=clock.iso()))
                gl.balance_minor -= diff
                a.balance_minor += diff
