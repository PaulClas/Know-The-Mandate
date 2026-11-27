"""KYM API (FastAPI): control plane (/api), simulated open banking gateway (/bank), sandbox OAuth server (/oauth)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import agents as agents_mod
from . import (
    approvals,
    auth,
    bank,
    clock,
    cnl,
    config,
    db,
    gateway,
    keys,
    kyc,
    ledger,
    mandates,
    oauth,
    policy,
    security,
    seed,
    taxonomy,
    transparency,
)
from .auth import User, current_user, require_role
from .metrics import METRICS

TAGS = [
    {"name": "session", "description": "Demo sessions (DEMO ONLY)"}, {"name": "agents", "description": "Know Your Agent registry"},
    {"name": "mandates", "description": "Mandate studio, registry and lifecycle"}, {"name": "authorization", "description": "Deterministic policy decision point"},
    {"name": "approvals", "description": "Bank-controlled human approval"}, {"name": "ledger", "description": "KYM Evidence Ledger"},
    {"name": "bank", "description": "Simulated open banking gateway (policy enforcement point)"}, {"name": "oauth", "description": "Sandbox OAuth/OIDC authorization server"},
    {"name": "ontology", "description": "Ontology, SHACL, JSON-LD and read-only SPARQL"}, {"name": "transactions", "description": "Transactions, evidence and disputes"},
    {"name": "compliance", "description": "Standards and regulatory control mappings (not compliance claims)"}, {"name": "scenarios", "description": "One-click demonstration scenarios"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    import logging

    if config.is_demo():
        logging.getLogger("uvicorn.error").warning("KYM_ENV=demo: no-password sessions and destructive reset are ENABLED. Synthetic data only. Never expose this publicly.")
    db.init_db()
    with db.write() as s:
        seed.seed(s)
    yield


app = FastAPI(
    title="KYM - Know Your Mandate (experimental proof of concept)", version="0.1.0", lifespan=lifespan, openapi_tags=TAGS,
    description="Bank the agent. Verify the mandate. Govern the execution. Record the evidence.\n\nSynthetic data only. Sandbox security mechanisms. Not compliant or certified with any regulation or standard.",
)
app.middleware("http")(security.security_middleware)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(mandates.MandateError)
async def _mandate_err(_, e: mandates.MandateError):
    code = 404 if e.code == "MANDATE_NOT_FOUND" else 403 if e.code in ("NOT_AUTHORIZED",) else 409 if e.code in ("INVALID_TRANSITION", "VERSION_EXISTS") else 422
    return JSONResponse({"error": e.code, "message": str(e), "details": e.details}, status_code=code)


@app.exception_handler(approvals.ApprovalError)
async def _approval_err(_, e: approvals.ApprovalError):
    return JSONResponse({"error": e.code, "message": str(e)}, status_code=404 if e.code == "NOT_FOUND" else 403 if e.code == "NOT_AUTHORIZED" else 409)


@app.exception_handler(agents_mod.AgentError)
async def _agent_err(_, e: agents_mod.AgentError):
    return JSONResponse({"error": "AGENT_ERROR", "message": str(e)}, status_code=422)


@app.exception_handler(transparency.TransparencyError)
async def _transparency_err(_, e: transparency.TransparencyError):
    return JSONResponse({"error": "TRANSPARENCY_ERROR", "message": str(e)}, status_code=422)


@app.exception_handler(oauth.OAuthError)
async def _oauth_err(request: Request, e: oauth.OAuthError):
    if e.error == "invalid_client":
        security.FAILED_CLIENT_AUTH.record(security.client_ip(request))
    return JSONResponse(e.body(), status_code=e.status, headers={"Cache-Control": "no-store"})


def _caller(request: Request, method: str | None = None) -> gateway.Caller:
    return gateway.Caller(method or request.method, gateway.public_url(str(request.url), request.url.path), request.headers.get("authorization"), request.headers.get("dpop"))


async def _json_obj(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError as e:
        raise HTTPException(400, "request body must be valid JSON") from e
    if not isinstance(body, dict):
        raise HTTPException(400, "request body must be a JSON object")
    return body


async def _params(request: Request) -> dict:
    ct = request.headers.get("content-type", "")
    if "json" in ct:
        return await request.json()
    form = await request.form()
    out = dict(form)
    if isinstance(out.get("authorization_details"), str):
        try:
            out["authorization_details"] = json.loads(out["authorization_details"])
        except ValueError as e:
            raise oauth.OAuthError("invalid_authorization_details", "authorization_details is not valid JSON") from e
    return out


# --------------------------------------------------------------------------- health / session


@app.get("/health", tags=["session"])
def health():
    with db.read() as s:
        return {"status": "ok", "seeded": seed.is_seeded(s), "version": "0.1.0", "policy_version": config.POLICY_VERSION, "ontology_version": config.ONTOLOGY_VERSION}


class LoginBody(BaseModel):
    user_id: str


@app.post("/api/session", tags=["session"])
def create_session(body: LoginBody):
    """DEMO ONLY: no password. Production uses OIDC with passkeys."""
    try:
        return {"token": auth.login(body.user_id), "user": {"id": body.user_id, **auth.DEMO_USERS[body.user_id]}, "warning": "demo session; no real authentication"}
    except KeyError as e:
        raise HTTPException(404, "unknown demo user") from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


@app.get("/api/session/users", tags=["session"])
def demo_users():
    return [{"id": k, **v} for k, v in auth.DEMO_USERS.items()]


@app.get("/api/me", tags=["session"])
def me(user: User = Depends(current_user)):
    return {"id": user.id, "role": user.role, **auth.DEMO_USERS.get(user.id, {})}


@app.get("/api/metrics", tags=["session"])
def metrics(user: User = Depends(require_role("admin", "investigator"))):
    return METRICS.snapshot()


# --------------------------------------------------------------------------- agents


class AgentRegistration(BaseModel):
    agent_id: str | None = None
    declared: dict
    generate_demo_keys: bool = True
    public_key_jwk: dict | None = None


@app.post("/api/agents", tags=["agents"], status_code=201)
def register_agent(body: AgentRegistration, user: User = Depends(require_role("admin"))):
    with db.write() as s:
        return agents_mod.register(s, body.declared, actor_id=user.id, agent_id=body.agent_id, generate_demo_keys=body.generate_demo_keys, public_key_jwk=body.public_key_jwk)


@app.get("/api/agents", tags=["agents"])
def list_agents(user: User = Depends(current_user)):
    with db.read() as s:
        return agents_mod.list_agents(s)


@app.get("/api/agents/{agent_id}", tags=["agents"])
def get_agent(agent_id: str, user: User = Depends(current_user)):
    with db.read() as s:
        a = s.get(db.Agent, agent_id)
        if not a:
            raise HTTPException(404, "agent not found")
        d = agents_mod.to_dict(a)
        d["mandates"] = mandates.list_mandates(s, agent_id=agent_id) if user.role != "customer" else [m for m in mandates.list_mandates(s, agent_id=agent_id) if kyc.can_act_for(s, user.id, m["principal_id"])]
        return d


@app.post("/api/agents/{agent_id}/verify", tags=["agents"])
def verify_agent(agent_id: str, user: User = Depends(require_role("admin"))):
    with db.write() as s:
        return agents_mod.verify(s, agent_id, actor_id=user.id)


class StatusBody(BaseModel):
    reason: str = "operator action"


class EnrollBody(BaseModel):
    interval_hours: int = 24
    grace_minutes: int = 60


class JwsBody(BaseModel):
    jws: str


class DemandBody(BaseModel):
    within_hours: int = 24
    reason: str


@app.post("/api/agents/{agent_id}/transparency/enroll", tags=["transparency"])
def transparency_enroll(agent_id: str, body: EnrollBody, user: User = Depends(require_role("admin"))):
    """Require this agent to submit signed activity reports on a schedule. Silence or a mismatch with the bank's own records restricts the agent."""
    with db.write() as s:
        return transparency.enroll(s, agent_id, interval_hours=body.interval_hours, grace_minutes=body.grace_minutes, actor_id=user.id)


@app.get("/api/agents/{agent_id}/transparency", tags=["transparency"])
def transparency_status(agent_id: str, user: User = Depends(require_role("admin", "investigator"))):
    with db.write() as s:  # enforcement (overdue reports, missed reveals) is evaluated on read too, so a status page can never show a stale CLEAR
        transparency.enforce(s, s.get(db.Agent, agent_id))
        return transparency.status(s, agent_id)


@app.post("/api/agents/{agent_id}/transparency/clear", tags=["transparency"])
def transparency_clear(agent_id: str, body: StatusBody, user: User = Depends(require_role("admin"))):
    """Close a violation after human review (recorded in the ledger) and re-verify the agent."""
    with db.write() as s:
        return transparency.clear(s, agent_id, reason=body.reason, actor_id=user.id)


@app.post("/api/commitments/{commitment_id}/demand-reveal", tags=["transparency"])
def transparency_demand(commitment_id: str, body: DemandBody, user: User = Depends(require_role("admin", "investigator"))):
    """Demand that the agent reveal the log it committed to. A mismatch proves tampering; silence past the deadline is a violation."""
    with db.write() as s:
        return transparency.demand_reveal(s, commitment_id, within_hours=body.within_hours, reason=body.reason, actor_id=user.id)


@app.post("/bank/agents/{agent_id}/activity-reports", tags=["transparency"])
def submit_activity_report(agent_id: str, body: JwsBody):
    """Agent-signed (ES256, registered key), hash-chained report. The bank reconciles it against the transactions it observed itself."""
    with db.write() as s:
        return transparency.submit_report(s, agent_id, body.jws)


@app.post("/bank/agents/{agent_id}/commitments", tags=["transparency"])
def submit_commitment(agent_id: str, body: JwsBody):
    """Commit (before acting) to a digest of the agent's reasoning/decision log."""
    with db.write() as s:
        return transparency.commit(s, agent_id, body.jws)


@app.post("/bank/agents/{agent_id}/commitments/{commitment_id}/reveal", tags=["transparency"])
def submit_reveal(agent_id: str, commitment_id: str, body: JwsBody):
    with db.write() as s:
        return transparency.reveal(s, agent_id, commitment_id, body.jws)


@app.post("/api/agents/{agent_id}/suspend", tags=["agents"])
def suspend_agent(agent_id: str, body: StatusBody, user: User = Depends(require_role("admin"))):
    with db.write() as s:
        return agents_mod.set_status(s, agent_id, "SUSPENDED", actor_id=user.id, reason=body.reason)


@app.post("/api/agents/{agent_id}/restrict", tags=["agents"])
def restrict_agent(agent_id: str, body: StatusBody, user: User = Depends(require_role("admin"))):
    with db.write() as s:
        return agents_mod.set_status(s, agent_id, "RESTRICTED", actor_id=user.id, reason=body.reason)


@app.post("/api/agents/{agent_id}/revoke", tags=["agents"])
def revoke_agent(agent_id: str, body: StatusBody, user: User = Depends(require_role("admin"))):
    with db.write() as s:
        return agents_mod.set_status(s, agent_id, "REVOKED", actor_id=user.id, reason=body.reason)


# --------------------------------------------------------------------------- mandates


def _principal_access(s, user: User, principal_id: str):
    auth.assert_can_act_for(s, user, principal_id)


class CompileBody(BaseModel):
    principal_id: str
    instruction: str | None = None
    cnl: str | None = None
    resolutions: dict | None = None
    reference_time: str | None = None


@app.post("/api/mandates/compile", tags=["mandates"])
def compile_mandate(body: CompileBody, user: User = Depends(current_user)):
    """Deterministic KYM-CNL compiler. An LLM may propose CNL text but can never issue or approve a mandate."""
    import time

    t0 = time.perf_counter()
    with db.read() as s:
        _principal_access(s, user, body.principal_id)
        out = mandates.compile_full(s, principal_id=body.principal_id, instruction=body.instruction, cnl_text=body.cnl, resolutions=body.resolutions, reference_time=body.reference_time)
    METRICS.observe("mandate_compilation", (time.perf_counter() - t0) * 1000)
    return out


class ValidateBody(BaseModel):
    content: dict


@app.post("/api/mandates/validate", tags=["mandates"])
def validate_mandate(body: ValidateBody, user: User = Depends(current_user)):
    with db.read() as s:
        pid = body.content.get("principal", {}).get("id", "")
        _principal_access(s, user, pid)
        return mandates.validate_content(s, body.content)


class CreateMandateBody(BaseModel):
    principal_id: str
    cnl: str | None = None
    content: dict | None = None
    reference_time: str | None = None


@app.post("/api/mandates", tags=["mandates"], status_code=201)
def create_mandate(body: CreateMandateBody, user: User = Depends(current_user)):
    """Creates an immutable DRAFT version and validates it. It becomes ACTIVE only after customer approval + activation."""
    with db.write() as s:
        _principal_access(s, user, body.principal_id)
        if body.cnl:
            c = mandates.compile_full(s, principal_id=body.principal_id, cnl_text=body.cnl, reference_time=body.reference_time)
            if not c["ok"]:
                raise HTTPException(422, {"error": "COMPILE_FAILED", "errors": c["errors"]})
            content = c["mandate"]
            artifacts = {"normalized_cnl": c["normalized_cnl"], "canonical_digest_draft": c["canonical_digest"]}
        elif body.content:
            content, artifacts = body.content, {}
            if content.get("principal", {}).get("id") != body.principal_id:
                raise HTTPException(403, "principal mismatch")
        else:
            raise HTTPException(422, "cnl or content required")
        return mandates.propose(s, content, created_by=user.id, actor_type=user.role, artifacts=artifacts)


@app.get("/api/mandates", tags=["mandates"])
def list_mandates(principal_id: str | None = None, agent_id: str | None = None, user: User = Depends(current_user)):
    with db.read() as s:
        rows = mandates.list_mandates(s, principal_id=principal_id, agent_id=agent_id)
        return rows if user.role != "customer" else [r for r in rows if kyc.can_act_for(s, user.id, r["principal_id"])]


@app.get("/api/mandates/{mandate_id}", tags=["mandates"])
def get_mandate(mandate_id: str, version: int | None = None, user: User = Depends(current_user)):
    with db.read() as s:
        v = mandates.view(s, mandate_id, version)
        _principal_access(s, user, v["content"]["principal"]["id"])
        return v


@app.get("/api/mandates/{mandate_id}/semantic", tags=["mandates", "ontology"])
def mandate_semantic(mandate_id: str, version: int | None = None, user: User = Depends(current_user)):
    from . import ontology_service as o
    from .schemas import Mandate

    with db.read() as s:
        v = mandates.view(s, mandate_id, version)
        _principal_access(s, user, v["content"]["principal"]["id"])
        g = o.mandate_graph(Mandate.model_validate(v["content"]), v["digest"])
        return {"json_ld": o.to_jsonld(g), "turtle": o.to_turtle(g), "shacl": o.validate_graph(g)}


class ApproveBody(BaseModel):
    digest: str
    version: int | None = None
    language: str = "en"


@app.post("/api/mandates/{mandate_id}/approve", tags=["mandates"])
def approve_mandate(mandate_id: str, body: ApproveBody, user: User = Depends(require_role("customer"))):
    with db.write() as s:
        v = body.version or mandates.get_row(s, mandate_id).version
        return mandates.approve(s, mandate_id, v, approver_id=user.id, presented_digest=body.digest, language=body.language)


@app.post("/api/mandates/{mandate_id}/reject", tags=["mandates"])
def reject_mandate(mandate_id: str, version: int | None = None, user: User = Depends(require_role("customer"))):
    with db.write() as s:
        row = mandates.get_row(s, mandate_id, version)
        _principal_access(s, user, row.principal_id)
        return mandates.reject(s, mandate_id, row.version, actor_id=user.id)


@app.post("/api/mandates/{mandate_id}/activate", tags=["mandates"])
def activate_mandate(mandate_id: str, version: int | None = None, user: User = Depends(current_user)):
    """Requires verified customer approval evidence bound to the mandate digest; there is no way to activate an unapproved mandate."""
    with db.write() as s:
        row = mandates.get_row(s, mandate_id, version)
        _principal_access(s, user, row.principal_id)
        return mandates.activate(s, mandate_id, row.version, actor_id=user.id, actor_type=user.role)


class AmendBody(BaseModel):
    cnl: str | None = None
    content: dict | None = None


@app.post("/api/mandates/{mandate_id}/amend", tags=["mandates"], status_code=201)
def amend_mandate(mandate_id: str, body: AmendBody, user: User = Depends(current_user)):
    with db.write() as s:
        cur = mandates.get_row(s, mandate_id)
        _principal_access(s, user, cur.principal_id)
        if body.cnl:
            c = mandates.compile_full(s, principal_id=cur.principal_id, cnl_text=body.cnl)
            if not c["ok"]:
                raise HTTPException(422, {"error": "COMPILE_FAILED", "errors": c["errors"]})
            content = c["mandate"]
        elif body.content:
            content = body.content
        else:
            raise HTTPException(422, "cnl or content required")
        return mandates.amend(s, mandate_id, content, actor_id=user.id)


class ReasonBody(BaseModel):
    reason: str = "revoked by customer"
    revoke_tokens: bool = True


@app.post("/api/mandates/{mandate_id}/revoke", tags=["mandates"])
def revoke_mandate(mandate_id: str, body: ReasonBody = ReasonBody(), user: User = Depends(current_user)):
    with db.write() as s:
        row = mandates.get_row(s, mandate_id)
        _principal_access(s, user, row.principal_id)
        return mandates.revoke(s, mandate_id, actor_id=user.id, actor_type="bank_operator" if user.is_admin else "customer", reason=body.reason, revoke_tokens=body.revoke_tokens)


@app.post("/api/mandates/{mandate_id}/suspend", tags=["mandates"])
def suspend_mandate(mandate_id: str, body: ReasonBody = ReasonBody(reason="suspended"), user: User = Depends(current_user)):
    with db.write() as s:
        row = mandates.get_row(s, mandate_id)
        _principal_access(s, user, row.principal_id)
        return mandates.suspend(s, mandate_id, actor_id=user.id, reason=body.reason)


@app.post("/api/mandates/{mandate_id}/resume", tags=["mandates"])
def resume_mandate(mandate_id: str, user: User = Depends(current_user)):
    with db.write() as s:
        row = mandates.get_row(s, mandate_id)
        _principal_access(s, user, row.principal_id)
        return mandates.resume(s, mandate_id, actor_id=user.id)


class DelegateBody(BaseModel):
    child_content: dict | None = None
    child_cnl: str | None = None
    child_agent_ref: str | None = None


@app.post("/api/mandates/{mandate_id}/delegate", tags=["mandates"], status_code=201)
def delegate_mandate(mandate_id: str, body: DelegateBody, request: Request, authorization: str | None = Header(default=None)):
    """Delegation is a bank-validated record. Caller: the parent agent (DPoP token) or the customer/operator (demo session)."""
    with db.write() as s:
        scheme = (authorization or "").split(" ", 1)[0].lower()
        if scheme == "dpop":
            ok, result, facts = gateway.authorize_delegation(s, _caller(request), mandate_id)
            if not ok:
                return JSONResponse({"status": "DENIED", "decision": result["decision"], "reason_codes": result["reason_codes"], "failed_checks": [c for c in result["trace"] if c["outcome"] == "FAIL"]}, status_code=403)
            requester, rtype = facts["actor"], "agent"
        else:
            user = current_user(authorization)
            row = mandates.get_row(s, mandate_id)
            _principal_access(s, user, row.principal_id)
            requester, rtype = user.id, user.role
        parent = mandates.get_row(s, mandate_id, mandates.active_version(s, mandate_id))
        if body.child_content:
            child = body.child_content
        elif body.child_cnl:
            c = mandates.compile_full(s, principal_id=parent.principal_id, cnl_text=body.child_cnl)
            if not c["ok"]:
                raise HTTPException(422, {"error": "COMPILE_FAILED", "errors": c["errors"]})
            child = c["mandate"]
        else:
            raise HTTPException(422, "child_content or child_cnl required")
        child["mandate_id"] = "mdt_DRAFT"
        return mandates.delegate(s, mandate_id, child, requested_by=requester, requested_by_type=rtype)


@app.get("/api/delegation/graph", tags=["mandates"])
def delegation_graph(principal_id: str | None = None, user: User = Depends(current_user)):
    with db.read() as s:
        nodes, edges = [], []
        for m in mandates.list_mandates(s, principal_id=principal_id):
            if user.role == "customer" and not kyc.can_act_for(s, user.id, m["principal_id"]):
                continue
            row = mandates.get_row(s, m["mandate_id"], m["version"])
            c = row.content
            nodes.append({"id": f"{m['mandate_id']}:v{m['version']}", "mandate_id": m["mandate_id"], "version": m["version"], "status": m["status"], "agent_id": m["agent_id"], "principal_id": m["principal_id"],
                          "depth": (c["lineage"]["depth"] if c.get("lineage") else 0), "delegation": c["delegation"], "currency": c["currency"], "expires_at": c["validity"]["expires_at"],
                          "max_amount_minor": max([p["constraints"].get("maximum_amount_minor") or 0 for p in c["permissions"]] or [0]),
                          "monthly_minor": c["aggregate_constraints"].get("maximum_monthly_amount_minor"), "actions": sorted({p["action"] for p in c["permissions"]}),
                          "beneficiaries": sorted({b for p in c["permissions"] for b in p["constraints"].get("allowed_beneficiaries", [])})})
        ids = {n["id"] for n in nodes}
        for d in s.execute(select(db.DelegationRow)).scalars():
            a, b = f"{d.parent_id}:v{d.parent_version}", f"{d.child_id}:v{d.child_version}"
            if a in ids and b in ids:
                edges.append({"source": a, "target": b})
        return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------- approvals


@app.get("/api/approvals", tags=["approvals"])
def list_approvals(user: User = Depends(current_user)):
    with db.write() as s:
        return approvals.list_for(s, user.id, user.role)


@app.post("/api/approvals/{approval_id}/approve", tags=["approvals"])
def approve_approval(approval_id: str, user: User = Depends(require_role("customer"))):
    """Approve ONCE: bound to the exact operation hash; does not expand the mandate."""
    with db.write() as s:
        return approvals.decide(s, approval_id, user.id, "APPROVE")


@app.post("/api/approvals/{approval_id}/reject", tags=["approvals"])
def reject_approval(approval_id: str, user: User = Depends(require_role("customer"))):
    with db.write() as s:
        return approvals.decide(s, approval_id, user.id, "REJECT")


# --------------------------------------------------------------------------- authorization playground


class EvaluateBody(BaseModel):
    agent_id: str
    mandate_id: str
    version: int | None = None
    action: str
    account_id: str
    beneficiary_id: str | None = None
    merchant_id: str | None = None
    to_account_id: str | None = None
    amount_minor: int | None = Field(default=None)
    currency: str | None = None
    purpose: str | None = None
    token_profile: str = "valid"
    approval_id: str | None = None


@app.post("/api/authorization/evaluate", tags=["authorization"])
def evaluate_authorization(body: EvaluateBody, user: User = Depends(current_user)):
    """Dry-run through the SAME gateway, PDP and risk engine as the bank API (real signed token, optionally defective on purpose)."""
    from . import sandbox

    with db.write() as s:
        row = mandates.get_row(s, body.mandate_id, body.version)
        _principal_access(s, user, row.principal_id)
        return sandbox.playground_evaluate(s, body.model_dump(), row)


class RiskBody(BaseModel):
    account_id: str
    beneficiary_id: str | None = None
    merchant_id: str | None = None
    amount_minor: int
    agent_id: str


@app.post("/api/risk/evaluate", tags=["authorization"])
def evaluate_risk(body: RiskBody, user: User = Depends(current_user)):
    from . import risk as risk_mod

    with db.read() as s:
        acct = s.get(db.Account, body.account_id)
        if not acct:
            raise HTTPException(404, "account not found")
        _principal_access(s, user, acct.owner_id or "")
        payee = s.get(db.Payee, body.beneficiary_id or body.merchant_id or "")
        if not payee:
            raise HTTPException(404, "payee not found")
        agent = s.get(db.Agent, body.agent_id)
        principal = s.get(db.Customer, acct.owner_id)
        ctx = gateway._risk_ctx(s, {"account_id": acct.id, "amount_minor": body.amount_minor, "principal_id": acct.owner_id}, principal, agent, payee, None, clock.now())
        return risk_mod.assess(ctx, config.policy_config())


# --------------------------------------------------------------------------- ledger


@app.get("/api/ledger/events", tags=["ledger"])
def ledger_events(event_type: str | None = None, correlation_id: str | None = None, mandate_id: str | None = None, transaction_id: str | None = None, q: str | None = None,
                  limit: int = 100, offset: int = 0, user: User = Depends(current_user)):
    with db.read() as s:
        events, total = ledger.list_events(s, event_type=event_type, correlation_id=correlation_id, mandate_id=mandate_id, transaction_id=transaction_id, q=q, limit=min(limit, 500), offset=offset)
        if user.role == "customer":
            events = [e for e in events if e.get("principal_id") and kyc.can_act_for(s, user.id, e["principal_id"])]
        return {"events": events, "total": total}


@app.get("/api/ledger/events/{event_id}", tags=["ledger"])
def ledger_event(event_id: str, user: User = Depends(current_user)):
    with db.read() as s:
        e = ledger.get_event(s, event_id)
        if not e:
            raise HTTPException(404, "event not found")
        if user.role == "customer" and not (e.get("principal_id") and kyc.can_act_for(s, user.id, e["principal_id"])):
            raise HTTPException(403, "cross-customer access denied")
        return e


@app.post("/api/ledger/verify", tags=["ledger"])
def ledger_verify(user: User = Depends(current_user)):
    import time

    t0 = time.perf_counter()
    with db.read() as s:
        r = ledger.verify_authoritative(s)
    METRICS.observe("ledger_verify", (time.perf_counter() - t0) * 1000)
    return r


@app.get("/api/ledger/checkpoints", tags=["ledger"])
def ledger_checkpoints(user: User = Depends(current_user)):
    with db.read() as s:
        return {"checkpoints": ledger.checkpoints(s), "public_keys": keys.public_key_registry()}


@app.post("/api/ledger/checkpoints", tags=["ledger"], status_code=201)
def create_checkpoint(user: User = Depends(require_role("admin"))):
    with db.write() as s:
        return ledger.create_checkpoint(s)


# --------------------------------------------------------------------------- transactions


@app.get("/api/transactions", tags=["transactions"])
def list_transactions(status: str | None = None, agent_id: str | None = None, principal_id: str | None = None, limit: int = 200, user: User = Depends(current_user)):
    with db.read() as s:
        q = select(db.Transaction).order_by(db.Transaction.seq.desc()).limit(min(limit, 1000))
        if status:
            q = q.where(db.Transaction.status == status)
        if agent_id:
            q = q.where(db.Transaction.agent_id == agent_id)
        if principal_id:
            q = q.where(db.Transaction.principal_id == principal_id)
        rows = s.execute(q).scalars().all()
        if user.role == "customer":
            rows = [t for t in rows if kyc.can_act_for(s, user.id, t.principal_id)]
        return [gateway.tx_view(t) for t in rows]


@app.get("/api/transactions/{tx_id}", tags=["transactions"])
def get_transaction(tx_id: str, user: User = Depends(current_user)):
    with db.read() as s:
        t = s.get(db.Transaction, tx_id)
        if not t:
            raise HTTPException(404, "transaction not found")
        _principal_access(s, user, t.principal_id)
        d = s.get(db.Decision, t.decision_id) if t.decision_id else None
        return {**gateway.tx_view(t), "operation": t.operation, "decision": None if not d else {"id": d.id, "decision": d.decision, "reason_codes": d.reason_codes, "trace": d.trace, "policy_version": d.policy_version, "inputs_digest": d.inputs_digest}}


class RiskReviewBody(BaseModel):
    decision: str
    note: str = ""


@app.post("/api/transactions/{tx_id}/risk-review", tags=["transactions"])
def risk_review(tx_id: str, body: RiskReviewBody, user: User = Depends(require_role("admin"))):
    """Bank risk analyst closes a REFER_TO_RISK_REVIEW item. Clearing does not execute: the agent must resubmit and be re-evaluated."""
    with db.write() as s:
        t = s.get(db.Transaction, tx_id)
        if not t or t.status != "RISK_REVIEW":
            raise HTTPException(409, "transaction is not in RISK_REVIEW")
        t.status = "CANCELLED" if body.decision == "REJECT" else "REVIEW_CLEARED"
        t.failure_reason = f"risk review: {body.decision}. {body.note}"
        return gateway.tx_view(t)


@app.post("/api/transactions/{tx_id}/reverse", tags=["transactions"])
def reverse_tx(tx_id: str, user: User = Depends(require_role("admin"))):
    with db.write() as s:
        try:
            return bank.reverse(s, tx_id, actor_id=user.id, reason="operator reversal")
        except bank.EngineError as e:
            raise HTTPException(409, str(e)) from e


# --------------------------------------------------------------------------- bank gateway (PEP)


def _out(status_body: tuple[int, dict]) -> JSONResponse:
    status, body = status_body
    body = {k: v for k, v in body.items() if k != "_data"}
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store", **({"WWW-Authenticate": 'DPoP error="invalid_token"'} if status == 401 else {})})


@app.get("/bank/accounts", tags=["bank"])
def bank_accounts(request: Request):
    return _out(gateway.list_accounts(_caller(request)))


@app.get("/bank/accounts/{account_id}", tags=["bank"])
def bank_account(account_id: str, request: Request):
    return _out(gateway.read_data(_caller(request), "accounts.read", account_id))


@app.get("/bank/accounts/{account_id}/balances", tags=["bank"])
def bank_balances(account_id: str, request: Request):
    return _out(gateway.read_data(_caller(request), "balances.read", account_id))


@app.get("/bank/accounts/{account_id}/transactions", tags=["bank"])
def bank_transactions(account_id: str, request: Request):
    return _out(gateway.read_data(_caller(request), "transactions.read", account_id))


@app.get("/bank/beneficiaries", tags=["bank"])
def bank_beneficiaries(request: Request):
    return _out(gateway.beneficiaries(_caller(request)))


@app.post("/bank/payments/proposals", tags=["bank"])
async def bank_prepare(request: Request):
    body = await _json_obj(request)
    return _out(gateway.handle(_caller(request), {**body, "kind": "PREPARE"}))


@app.post("/bank/payments", tags=["bank"])
async def bank_payment(request: Request, idempotency_key: str | None = Header(default=None)):
    body = await _json_obj(request)
    if not idempotency_key:
        return JSONResponse({"error": "invalid_request", "error_description": "Idempotency-Key header required"}, status_code=400)
    return _out(gateway.handle(_caller(request), {**body, "kind": "PAYMENT"}, idempotency_key=idempotency_key))


@app.post("/bank/transfers", tags=["bank"])
async def bank_transfer(request: Request, idempotency_key: str | None = Header(default=None)):
    body = await _json_obj(request)
    if not idempotency_key:
        return JSONResponse({"error": "invalid_request", "error_description": "Idempotency-Key header required"}, status_code=400)
    return _out(gateway.handle(_caller(request), {**body, "kind": "TRANSFER"}, idempotency_key=idempotency_key))


@app.get("/bank/payments/{tx_id}", tags=["bank"])
def bank_payment_status(tx_id: str, request: Request):
    return _out(gateway.get_payment(_caller(request), tx_id))


# --------------------------------------------------------------------------- OAuth


@app.get("/.well-known/oauth-authorization-server", tags=["oauth"])
def oauth_metadata():
    return oauth.metadata()


@app.get("/.well-known/jwks.json", tags=["oauth"])
def oauth_jwks():
    return oauth.jwks()


def _client_creds(request: Request, params: dict) -> dict:
    import base64

    h = request.headers.get("authorization", "")
    if h.lower().startswith("basic "):
        cid, _, sec = base64.b64decode(h.split(" ", 1)[1]).decode().partition(":")
        params = {**params, "client_id": cid, "client_secret": sec}
    return params


@app.post("/oauth/par", tags=["oauth"], status_code=201)
def oauth_par(request: Request, params: dict = Depends(_params)):
    params = _client_creds(request, params)
    with db.read() as s:  # scrypt runs OUTSIDE the global write lock so bad credentials cannot stall every writer
        client = oauth.authenticate_client(s, params.get("client_id"), params.get("client_secret"))
    with db.write() as s:
        return oauth.pushed_authorization_request(s, client, params)


class ApproveAuthBody(BaseModel):
    request_uri: str


@app.post("/oauth/authorize/approve", tags=["oauth"])
def oauth_authorize_approve(body: ApproveAuthBody, user: User = Depends(require_role("customer"))):
    """Bank-hosted authorization endpoint step: the signed-in customer approves the pushed request."""
    with db.write() as s:
        return oauth.authorize_approve(s, body.request_uri, user.id)


@app.post("/oauth/token", tags=["oauth"])
def oauth_token(request: Request, params: dict = Depends(_params)):
    params = _client_creds(request, params)
    err: oauth.OAuthError | None = None
    out: dict = {}
    with db.read() as s:
        client = oauth.authenticate_client(s, params.get("client_id"), params.get("client_secret"))
    with db.write() as s:
        try:
            out = oauth.token_endpoint(s, params, dpop=request.headers.get("dpop"), url=gateway.public_url(str(request.url), request.url.path), client=client)
        except oauth.OAuthError as e:
            err = e  # commit side effects of failed attempts (burned authorization code, recorded DPoP jti) before answering
    if err:
        raise err
    return JSONResponse(out, headers={"Cache-Control": "no-store"})


@app.post("/oauth/introspect", tags=["oauth"])
def oauth_introspect(request: Request, params: dict = Depends(_params)):
    params = _client_creds(request, params)
    with db.read() as s:
        client = oauth.authenticate_client(s, params.get("client_id"), params.get("client_secret"))
        return oauth.introspect(s, client, params.get("token", ""))


@app.post("/oauth/revoke", tags=["oauth"])
def oauth_revoke(request: Request, params: dict = Depends(_params)):
    params = _client_creds(request, params)
    with db.read() as s:
        client = oauth.authenticate_client(s, params.get("client_id"), params.get("client_secret"))
    with db.write() as s:
        oauth.revoke_token(s, client, params.get("token", ""))
    return JSONResponse({}, status_code=200)


# --------------------------------------------------------------------------- overview


@app.get("/api/overview", tags=["session"])
def overview(user: User = Depends(current_user)):
    with db.read() as s:
        def cnt(model, *cond):
            return s.execute(select(func.count()).select_from(model).where(*cond)).scalar_one()

        txs = s.execute(select(db.Transaction)).scalars().all()
        dist: dict[str, int] = {}
        for t in txs:
            if t.outcome:
                dist[t.outcome] = dist.get(t.outcome, 0) + 1
        authorized = sum(t.amount_minor for t in txs if t.status == "EXECUTED")
        states = [mandates.get_state(s, r.mandate_id, r.version).status for r in s.execute(select(db.MandateRow)).scalars()]
        integrity = ledger.verify_authoritative(s)
        recent, _ = ledger.list_events(s, limit=12)
        return {
            "registered_agents": cnt(db.Agent), "verified_agents": cnt(db.Agent, db.Agent.status == "VERIFIED"),
            "active_mandates": states.count("ACTIVE"), "revoked_mandates": states.count("REVOKED"), "pending_customer_approvals": states.count("PENDING_CUSTOMER_APPROVAL"),
            "pending_transaction_approvals": cnt(db.Approval, db.Approval.status == "PENDING"),
            "total_authorized_payments_minor": authorized, "executed_payments": sum(1 for t in txs if t.status == "EXECUTED"),
            "denied_actions": sum(1 for t in txs if t.status == "DENIED"), "decision_distribution": dist,
            "ledger": {"ok": integrity["ok"], "events": integrity["events_checked"], "head_hash": integrity["head_hash"], "checkpoints": integrity["checkpoints_checked"], "problems": integrity["problems"][:3]},
            "recent_events": recent, "trial_balance": bank.trial_balance(s), "disclaimer": "Synthetic demo. Not compliant or certified.",
        }


@app.get("/api/accounts", tags=["bank"])
def customer_accounts(user: User = Depends(current_user)):
    """Customer banking portal view (bank-authenticated session, not the agent API)."""
    with db.read() as s:
        rows = s.execute(select(db.Account).where(db.Account.owner_id.is_not(None))).scalars().all()
        if user.role == "customer":
            rows = [a for a in rows if kyc.can_act_for(s, user.id, a.owner_id)]
        return [{**bank.account_view(a), **bank.balance_view(a), "owner_id": a.owner_id, "cnl_ref": a.cnl_ref} for a in rows]


@app.get("/api/customers", tags=["session"])
def customers(user: User = Depends(current_user)):
    with db.read() as s:
        rows = s.execute(select(db.Customer)).scalars().all()
        out = [{"id": c.id, "type": c.type, "name": c.name, "jurisdiction": c.jurisdiction, "kyc_status": c.kyc_status, "kyc_date": c.kyc_date, "kyc_evidence_ref": c.kyc_evidence_ref,
                "risk_class": c.risk_class, "restrictions": c.restrictions, "cnl_ref": c.cnl_ref,
                "representatives": [{"person_id": r.person_id, "role": r.role, "can_sign": r.can_sign, "account_ids": r.account_ids} for r in s.execute(select(db.Representative).where(db.Representative.business_id == c.id)).scalars()]}
               for c in rows]
        return out if user.role != "customer" else [c for c in out if kyc.can_act_for(s, user.id, c["id"])]


@app.get("/api/payees", tags=["bank"])
def payees(user: User = Depends(current_user)):
    with db.read() as s:
        return [{"id": p.id, "kind": p.kind, "name": p.name, "country": p.country, "category": p.category, "cnl_ref": p.cnl_ref} for p in s.execute(select(db.Payee)).scalars()]


_ = (policy, taxonomy, cnl, timedelta)


# --------------------------------------------------------------------------- scenarios, sandbox, disputes, ontology, compliance, adapters


@app.get("/api/scenarios", tags=["scenarios"])
def scenarios_catalog(user: User = Depends(current_user)):
    from . import scenarios

    return scenarios.CATALOG


@app.post("/api/scenarios/{scenario_id}/run", tags=["scenarios"])
def run_scenario(scenario_id: str, user: User = Depends(require_role("admin", "investigator"))):
    """Runs the scenario through the real HTTP API, PDP and evidence ledger. The runner simulates the customer approval step."""
    from . import scenarios

    try:
        return scenarios.run(scenario_id)
    except KeyError as e:
        raise HTTPException(404, "unknown scenario") from e


@app.post("/api/demo/reset", tags=["scenarios"])
def demo_reset(user: User = Depends(require_role("admin"))):
    """DESTRUCTIVE (deletes the evidence ledger and exported checkpoints). Demo only; refused when KYM_ENV != demo."""
    from . import scenarios

    if not config.is_demo():
        raise HTTPException(403, "reset is disabled outside KYM_ENV=demo")

    return scenarios.reset()


@app.get("/api/sandbox/agents", tags=["scenarios"])
def sandbox_agents(user: User = Depends(current_user)):
    from . import sandbox

    with db.read() as s:
        out = []
        for a in sandbox.SANDBOX_AGENTS:
            ms = [m for m in mandates.list_mandates(s, agent_id=a["id"]) if m["status"] == "ACTIVE"]
            out.append({**a, "status": s.get(db.Agent, a["id"]).status, "active_mandates": ms})
        return out


class ChatBody(BaseModel):
    agent_id: str
    message: str
    customer_id: str | None = None
    mandate_id: str | None = None
    untrusted_document: str | None = None


@app.post("/api/sandbox/chat", tags=["scenarios"])
def sandbox_chat(body: ChatBody, user: User = Depends(current_user)):
    """Deterministic scripted agent. Every action is a real HTTP call to the bank gateway (PEP)."""
    from . import sandbox

    customer = body.customer_id or (user.id if user.role == "customer" else "customer_001")
    with db.read() as s:
        _principal_access(s, user, customer)
    return sandbox.chat(agent_id=body.agent_id, message=body.message, customer_id=customer, mandate_id=body.mandate_id, untrusted_document=body.untrusted_document)


class DisputeBody(BaseModel):
    reason: str


@app.post("/api/transactions/{tx_id}/dispute", tags=["transactions"])
def open_dispute(tx_id: str, body: DisputeBody, user: User = Depends(current_user)):
    from . import disputes

    with db.write() as s:
        t = s.get(db.Transaction, tx_id)
        if not t:
            raise HTTPException(404, "transaction not found")
        _principal_access(s, user, t.principal_id)
        try:
            return disputes.open_dispute(s, tx_id, opened_by=user.id, reason=body.reason)
        except disputes.DisputeError as e:
            raise HTTPException(409, str(e)) from e


@app.get("/api/transactions/{tx_id}/evidence", tags=["transactions"])
def transaction_evidence(tx_id: str, user: User = Depends(current_user)):
    from . import disputes

    with db.read() as s:
        t = s.get(db.Transaction, tx_id)
        if not t:
            raise HTTPException(404, "transaction not found")
        _principal_access(s, user, t.principal_id)
        return disputes.build_package(s, tx_id)


@app.get("/api/transactions/{tx_id}/evidence/download", tags=["transactions"])
def transaction_evidence_download(tx_id: str, user: User = Depends(current_user)):
    from . import disputes

    with db.read() as s:
        t = s.get(db.Transaction, tx_id)
        if not t:
            raise HTTPException(404, "transaction not found")
        _principal_access(s, user, t.principal_id)
        pkg = disputes.build_package(s, tx_id)
    return JSONResponse(pkg, headers={"Content-Disposition": f'attachment; filename="kym-evidence-{tx_id}.json"'})


@app.post("/api/evidence/verify", tags=["ledger"])
def verify_uploaded_package(pkg: dict, user: User = Depends(current_user)):
    """Offline-style verification of an exported evidence package (uses only the package contents)."""
    from . import disputes

    return disputes.verify_package(pkg, trusted_keys=keys.public_key_registry())


@app.get("/api/responsibility/matrix", tags=["transactions"])
def responsibility_matrix(user: User = Depends(current_user)):
    from . import responsibility

    return responsibility.matrix()


@app.get("/api/responsibility/faults", tags=["transactions"])
def responsibility_faults(user: User = Depends(current_user)):
    from . import responsibility

    return {"faults": responsibility.FAULTS, "levels": responsibility.matrix()["levels"], "disclaimer": "No liability determination is made by this system."}


@app.get("/api/compliance/controls", tags=["compliance"])
def compliance_controls(jurisdiction: str | None = None, user: User = Depends(current_user)):
    from . import compliance

    return {"disclaimer": compliance.DISCLAIMER, "controls": compliance.controls_for(jurisdiction)}


@app.get("/api/compliance/profiles", tags=["compliance"])
def compliance_profiles(user: User = Depends(current_user)):
    from . import compliance

    return {"disclaimer": compliance.DISCLAIMER, "profiles": compliance.profiles()}


@app.get("/api/standards", tags=["compliance"])
def standards_matrix(user: User = Depends(current_user)):
    from . import compliance

    return {"disclaimer": compliance.DISCLAIMER, "standards": compliance.standards()}


@app.get("/api/adapters", tags=["compliance"])
def adapters_registry(user: User = Depends(current_user)):
    from . import adapters

    return adapters.REGISTRY


class Ap2Body(BaseModel):
    artifact_type: str


@app.post("/api/adapters/ap2/map", tags=["compliance"])
def ap2_map(body: Ap2Body, user: User = Depends(current_user)):
    from . import adapters

    return adapters.ap2_map(body.artifact_type)


@app.post("/adapters/mcp", tags=["bank"])
async def mcp_endpoint(request: Request):
    """Minimal MCP-shaped adapter (sandbox, not a conformant MCP server). Tool discovery is not permission."""
    from . import adapters

    return JSONResponse(adapters.mcp_handle(await _json_obj(request), _caller(request, "POST")))


# ---- ontology


def _ont_summary() -> dict:
    from rdflib import OWL, RDF, RDFS

    from . import ontology_service as o

    g = o.ontology()
    def label(n):
        return str(n).rsplit("#", 1)[-1]
    classes = []
    for c in sorted(g.subjects(RDF.type, OWL.Class), key=str):
        if str(c).startswith(config.KYM_NS):
            classes.append({"id": label(c), "label": str(g.value(c, RDFS.label) or label(c)), "comment": str(g.value(c, RDFS.comment) or ""),
                            "parents": [label(p) if str(p).startswith(config.KYM_NS) else str(p).replace("http://www.w3.org/ns/prov#", "prov:").replace("http://www.w3.org/ns/odrl/2/", "odrl:") for p in g.objects(c, RDFS.subClassOf)],
                            "action_id": str(g.value(c, o.KYM.actionId) or "") or None})
    def props(kind):
        return [{"id": label(p), "label": str(g.value(p, RDFS.label) or label(p)), "domain": label(g.value(p, RDFS.domain)) if g.value(p, RDFS.domain) else None, "range": label(g.value(p, RDFS.range)) if g.value(p, RDFS.range) else None}
                for p in sorted(g.subjects(RDF.type, kind), key=str) if str(p).startswith(config.KYM_NS)]
    return {"version": config.ONTOLOGY_VERSION, "namespace": config.KYM_NS, "experimental": True, "note": "EXPERIMENTAL placeholder vocabulary (example.org). Reuses PROV-O and ODRL. Not used for runtime authorization.",
            "classes": classes, "object_properties": props(OWL.ObjectProperty), "datatype_properties": props(OWL.DatatypeProperty), "triples": len(g)}


@app.get("/api/ontology", tags=["ontology"])
def ontology_summary(user: User = Depends(current_user)):
    return _ont_summary()


@app.get("/api/ontology/classes", tags=["ontology"])
def ontology_classes(user: User = Depends(current_user)):
    return _ont_summary()["classes"]


@app.get("/api/ontology/turtle", tags=["ontology"])
def ontology_turtle(user: User = Depends(current_user)):
    from . import ontology_service as o

    return {"turtle": (o.ONT_DIR / "kym-v1.ttl").read_text(), "shapes": (o.ONT_DIR / "shapes.ttl").read_text(), "context": o.jsonld_context()}


CATEGORY_OF = [("customer", ("customer/", "Customer", "Human", "AuthorizedRepresentative", "LegalEntity", "Organization", "Principal")), ("agent", ("agent/", "operator/", "AIAgent", "AgentOperator", "AgentDeveloper")),
               ("resource", ("account/", "BankAccount", "FinancialResource", "PaymentInstrument", "beneficiary/", "merchant/", "Beneficiary", "Merchant")), ("permission", ("permission", "Permission", "Prohibition", "FinancialAction", "prohibition")),
               ("constraint", ("constraint", "Constraint", "Obligation", "obligation")), ("evidence", ("LedgerEvent", "Evidence", "ConsentReceipt", "consent/", "decision/", "approval/", "Approval", "PolicyDecision", "Transaction", "tx/", "RiskAssessment")),
               ("delegation", ("Delegation", "delegat")), ("responsibility", ("ResponsibilityAssignment", "Jurisdiction", "jurisdiction/", "RegulatoryControl")), ("mandate", ("mandate/", "Mandate", "revocation/"))]


def _category(iri: str) -> str:
    tail = iri.replace("https://example.org/kym/id/", "").replace(config.KYM_NS, "")
    for cat, keys_ in CATEGORY_OF:
        if any(k in tail for k in keys_):
            if cat == "permission" and "constraint" in tail:
                return "constraint"
            return cat
    return "mandate"


@app.get("/api/ontology/graph", tags=["ontology"])
def ontology_graph(mode: str = "schema", categories: str | None = None, mandate_id: str | None = None, user: User = Depends(current_user)):
    from rdflib import OWL, RDF, RDFS, Literal, URIRef

    from . import ontology_service as o

    wanted = set(categories.split(",")) if categories else None
    nodes, edges = {}, []
    if mode == "schema":
        g = o.ontology()
        for c in g.subjects(RDF.type, OWL.Class):
            if str(c).startswith(config.KYM_NS):
                nid = str(c).rsplit("#", 1)[-1]
                nodes[nid] = {"id": nid, "label": nid, "category": _category(str(c)), "type": "class"}
                for p in g.objects(c, RDFS.subClassOf):
                    if str(p).startswith(config.KYM_NS):
                        edges.append({"source": nid, "target": str(p).rsplit("#", 1)[-1], "label": "subClassOf"})
        for p in g.subjects(RDF.type, OWL.ObjectProperty):
            d, r = g.value(p, RDFS.domain), g.value(p, RDFS.range)
            if d and r and str(d).startswith(config.KYM_NS) and str(r).startswith(config.KYM_NS):
                edges.append({"source": str(d).rsplit("#", 1)[-1], "target": str(r).rsplit("#", 1)[-1], "label": str(p).rsplit("#", 1)[-1]})
    else:
        with db.read() as s:
            g = o.registry_graph(s)
            for sub, p, obj in g:
                if not isinstance(sub, URIRef) or not str(sub).startswith("https://example.org/kym/id/") or isinstance(obj, Literal) or p == RDF.type:
                    continue
                if not str(obj).startswith("https://example.org/kym/id/") and not str(obj).startswith(config.KYM_NS):
                    continue
                if mandate_id and mandate_id not in str(sub) and mandate_id not in str(obj):
                    continue
                a, b = str(sub).replace("https://example.org/kym/id/", ""), str(obj).replace("https://example.org/kym/id/", "").replace(config.KYM_NS, "kym:")
                for nid, iri in ((a, str(sub)), (b, str(obj))):
                    nodes.setdefault(nid, {"id": nid, "label": nid.split("/", 1)[-1][:34], "category": _category(iri), "type": nid.split("/")[0]})
                edges.append({"source": a, "target": b, "label": str(p).rsplit("#", 1)[-1].rsplit("/", 1)[-1]})
    if wanted:
        nodes = {k: v for k, v in nodes.items() if v["category"] in wanted}
        edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    return {"nodes": list(nodes.values())[:400], "edges": edges[:900], "mode": mode}


@app.get("/api/ontology/triples", tags=["ontology"])
def ontology_triples(node: str, user: User = Depends(current_user)):
    from rdflib import Graph, URIRef

    from . import ontology_service as o

    iri = node if node.startswith("http") else (f"{config.KYM_NS}{node}" if "/" not in node else f"https://example.org/kym/id/{node}")
    with db.read() as s:
        g = o.registry_graph(s)
    ref = URIRef(iri)
    sub = Graph()
    for t in list(g.triples((ref, None, None))) + list(g.triples((None, None, ref))):
        sub.add(t)
    o.bind(sub)
    return {"node": iri, "triples": [[str(a), str(b), str(c)] for a, b, c in sub][:300], "json_ld": o.to_jsonld(sub) if len(sub) else {}, "turtle": o.to_turtle(sub)}


@app.get("/api/ontology/examples", tags=["ontology"])
def ontology_examples(user: User = Depends(current_user)):
    from . import ontology_service as o

    return o.sparql_examples()


class QueryBody(BaseModel):
    query: str


@app.post("/api/ontology/query", tags=["ontology"])
def ontology_query(body: QueryBody, user: User = Depends(current_user)):
    """Read-only local SPARQL (SELECT/ASK). SERVICE/FROM/updates rejected; query size, rows and time limited."""
    from . import ontology_service as o

    with db.read() as s:
        g = o.registry_graph(s)
        if user.role == "customer":
            raise HTTPException(403, "ontology queries are an operator/investigator tool in this demo")
    try:
        return o.safe_sparql(g, body.query)
    except o.SparqlError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/redteam", tags=["scenarios"])
def redteam_catalog(user: User = Depends(current_user)):
    from . import redteam

    return [{"id": a[0], "title": a[1], "category": a[2], "refs": a[3]} for a in redteam.ATTACKS]


@app.post("/api/redteam/run", tags=["scenarios"])
def redteam_run(attack_id: str | None = None, user: User = Depends(require_role("admin", "investigator"))):
    """Executable proof: runs attacks against scope-only and OAuth+static-RAR baselines and against KYM. Demo only (creates synthetic mandates and transactions)."""
    from . import redteam

    if not config.is_demo():
        raise HTTPException(403, "red-team runs are disabled outside KYM_ENV=demo")
    if attack_id:
        if attack_id not in {a[0] for a in redteam.ATTACKS}:
            raise HTTPException(404, "unknown attack")
        return redteam.run_attack(attack_id)
    return redteam.run_all()
