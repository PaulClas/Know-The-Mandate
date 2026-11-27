"""Mandate registry and lifecycle: compile, validate, approve, activate, amend, suspend, revoke, delegate.

Immutable mandate content (per version) is stored separately from authoritative lifecycle state,
counters and revocation records. Every transition writes an evidence event in the same transaction.
"""
from __future__ import annotations

import time
import uuid

from pydantic import ValidationError
from sqlalchemy import select

from . import canon, clock, cnl, config, db, keys, kyc, ledger, ontology_service, policy, taxonomy
from .schemas import Mandate

STATES = ["DRAFT", "PENDING_VALIDATION", "VALIDATED", "PENDING_CUSTOMER_APPROVAL", "ACTIVE", "SUSPENDED", "EXPIRED", "REVOKED", "SUPERSEDED", "REJECTED"]
TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"PENDING_VALIDATION", "REJECTED"},
    "PENDING_VALIDATION": {"VALIDATED", "REJECTED"},
    "VALIDATED": {"PENDING_CUSTOMER_APPROVAL", "REJECTED"},
    "PENDING_CUSTOMER_APPROVAL": {"ACTIVE", "REJECTED"},
    "ACTIVE": {"SUSPENDED", "EXPIRED", "REVOKED", "SUPERSEDED"},
    "SUSPENDED": {"ACTIVE", "REVOKED", "EXPIRED", "SUPERSEDED"},
    "EXPIRED": set(),
    "REVOKED": set(),
    "SUPERSEDED": set(),
    "REJECTED": set(),
}
EVENT_FOR = {
    "DRAFT": "MANDATE_PROPOSED", "PENDING_VALIDATION": "MANDATE_PROPOSED", "VALIDATED": "MANDATE_VALIDATED",
    "PENDING_CUSTOMER_APPROVAL": "MANDATE_APPROVAL_REQUESTED", "ACTIVE": "MANDATE_ACTIVATED", "SUSPENDED": "MANDATE_SUSPENDED",
    "EXPIRED": "MANDATE_EXPIRED", "REVOKED": "MANDATE_REVOKED", "SUPERSEDED": "MANDATE_SUPERSEDED", "REJECTED": "MANDATE_REJECTED",
}
CONSENT_DOMAIN = b"KYM-CONSENT-V1\x00"
ASSURANCE = {
    "level": "DEMO_SIMULATED_SESSION",
    "description": "Simulated bank-authenticated session with a server-held demo signing key. Not passkey/WebAuthn, not a qualified electronic signature.",
}


class MandateError(ValueError):
    def __init__(self, message: str, code: str = "MANDATE_ERROR", details: list | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or []


# --------------------------------------------------------------------------- reads


def get_row(s, mandate_id: str, version: int | None = None) -> db.MandateRow:
    q = select(db.MandateRow).where(db.MandateRow.mandate_id == mandate_id)
    q = q.where(db.MandateRow.version == version) if version else q.order_by(db.MandateRow.version.desc())
    row = s.execute(q.limit(1)).scalar_one_or_none()
    if not row:
        raise MandateError(f"mandate {mandate_id} not found", "MANDATE_NOT_FOUND")
    return row


def get_state(s, mandate_id: str, version: int) -> db.MandateState:
    st = s.get(db.MandateState, (mandate_id, version))
    if not st:
        raise MandateError("mandate state missing", "MANDATE_NOT_FOUND")
    return st


def active_version(s, mandate_id: str) -> int | None:
    rows = s.execute(select(db.MandateState).where(db.MandateState.mandate_id == mandate_id, db.MandateState.status.in_(["ACTIVE", "SUSPENDED"]))).scalars().all()
    return max((r.version for r in rows), default=None)


def view(s, mandate_id: str, version: int | None = None) -> dict:
    row = get_row(s, mandate_id, version)
    st = get_state(s, row.mandate_id, row.version)
    versions = [(r.version, get_state(s, r.mandate_id, r.version).status) for r in s.execute(select(db.MandateRow).where(db.MandateRow.mandate_id == mandate_id).order_by(db.MandateRow.version)).scalars()]
    consent = s.execute(select(db.Consent).where(db.Consent.mandate_id == mandate_id, db.Consent.version == row.version)).scalar_one_or_none()
    children = [{"child_id": d.child_id, "child_version": d.child_version} for d in s.execute(select(db.DelegationRow).where(db.DelegationRow.parent_id == mandate_id)).scalars()]
    return {
        "mandate_id": row.mandate_id, "version": row.version, "status": st.status, "digest": row.digest, "content": row.content,
        "created_at": row.created_at, "created_by": row.created_by, "state_history": st.history, "validation": st.validation,
        "versions": [{"version": v, "status": x} for v, x in versions],
        "consent": None if not consent else {"id": consent.id, "receipt": consent.receipt, "signature": consent.signature, "key_id": consent.key_id},
        "children": children, "parent": row.content.get("lineage"),
    }


def list_mandates(s, *, principal_id: str | None = None, agent_id: str | None = None) -> list[dict]:
    q = select(db.MandateRow).order_by(db.MandateRow.created_at.desc(), db.MandateRow.version.desc())
    if principal_id:
        q = q.where(db.MandateRow.principal_id == principal_id)
    if agent_id:
        q = q.where(db.MandateRow.agent_id == agent_id)
    out = []
    for r in s.execute(q).scalars():
        st = get_state(s, r.mandate_id, r.version)
        out.append({"mandate_id": r.mandate_id, "version": r.version, "status": st.status, "principal_id": r.principal_id, "agent_id": r.agent_id,
                    "purpose": r.content["purpose"], "digest": r.digest, "created_at": r.created_at, "expires_at": r.content["validity"]["expires_at"],
                    "parent_mandate_id": r.parent_mandate_id, "currency": r.content["currency"]})
    return out


# --------------------------------------------------------------------------- validation


def _check(checks: list, cid: str, ok: bool, detail: str):
    checks.append({"id": cid, "ok": bool(ok), "detail": detail})


def semantic_checks(s, m: Mandate, *, now=None) -> tuple[list[dict], list[dict]]:
    """Returns (semantic checks, bank policy checks). Identity and authority over resources are checked separately."""
    now = now or clock.now()
    pol = config.policy_config(m.policy_version) if m.policy_version else config.policy_config()
    sem: list[dict] = []
    bank: list[dict] = []
    cust = s.get(db.Customer, m.principal.id)
    _check(sem, "principal.exists", cust is not None, f"Customer {m.principal.id}")
    _check(sem, "principal.identity_verified", bool(cust and cust.kyc_status == "VERIFIED"), "Identity verification status is VERIFIED (simulated KYC)")
    _check(sem, "principal.type", bool(cust and cust.type == m.principal.type), f"Principal type {m.principal.type}")
    _check(sem, "principal.unrestricted", bool(cust and not cust.restrictions), "No customer restrictions")
    for perm in m.permissions:
        for r in perm.resources:
            acct = s.get(db.Account, r)
            _check(sem, f"resource.{perm.action}.{r}.exists", acct is not None, f"Account {r} exists")
            _check(sem, f"resource.{perm.action}.{r}.authority", bool(acct and acct.owner_id == m.principal.id),
                   "Principal controls the account (a customer cannot delegate authority over an account it does not control)")
            if acct:
                _check(sem, f"resource.{perm.action}.{r}.open", acct.status == "OPEN" and not acct.restrictions, "Account open and unrestricted")
                if perm.action in taxonomy.MONEY_MOVING:
                    _check(sem, f"resource.{perm.action}.{r}.currency", acct.currency == m.currency, f"Account currency {acct.currency} = mandate currency {m.currency}")
        c = perm.constraints
        for b in c.allowed_beneficiaries + c.allowed_merchants:
            _check(sem, f"counterparty.{b}.exists", s.get(db.Payee, b) is not None, f"Counterparty {b} is registered")
        for da in c.allowed_destination_accounts:
            d = s.get(db.Account, da)
            _check(sem, f"destination.{da}.own", bool(d and d.owner_id == m.principal.id), "Internal destination account is owned by the principal")
    agent = s.get(db.Agent, m.mandatary.agent_id)
    _check(sem, "agent.exists", agent is not None, f"Agent {m.mandatary.agent_id}")
    if agent:
        _check(sem, "agent.client_binding", agent.client_id == m.mandatary.client_id, "client_id matches registry")
        _check(sem, "agent.operator_binding", agent.declared.get("operator_id") == m.mandatary.operator_id, "operator_id matches registry")
        _check(sem, "agent.eligible", agent.status in pol["agents"]["eligible_for_mandate"], f"Agent status {agent.status} must be one of {pol['agents']['eligible_for_mandate']}")
        caps = set(agent.declared.get("requested_capabilities", []))
        for perm in m.permissions:
            _check(sem, f"agent.capability.{perm.action}", perm.action in caps, f"Agent registered capability {perm.action}")
    # bank policy
    lim = pol["limits"]
    _check(bank, "policy.version", m.policy_version == config.POLICY_VERSION, f"Mandate policy_version {m.policy_version}; bank current {config.POLICY_VERSION}")
    _check(bank, "policy.ontology_version", m.ontology_version == config.ONTOLOGY_VERSION, f"ontology_version {m.ontology_version}")
    _check(bank, "policy.purpose_allowed", m.purpose in lim["allowed_purposes"], f"Purpose {m.purpose} is in the bank's purpose catalogue")
    nb, ex = clock.parse(m.validity.not_before), clock.parse(m.validity.expires_at)
    _check(bank, "policy.not_already_expired", ex > now, "Mandate expires in the future")
    _check(bank, "policy.max_validity", (ex - nb).days <= lim["max_mandate_validity_days"], f"Validity ≤ {lim['max_mandate_validity_days']} days")
    _check(bank, "policy.delegation_depth", m.delegation.maximum_depth <= lim["max_delegation_depth"], f"Delegation depth ≤ {lim['max_delegation_depth']}")
    for perm in m.permissions:
        _check(bank, f"policy.forbidden_action.{perm.action}", perm.action not in lim["forbidden_agent_actions"], f"{perm.action} may not be delegated to agents under this policy")
        if perm.action in taxonomy.MONEY_MOVING:
            mx = perm.constraints.maximum_amount_minor
            _check(bank, f"policy.max_payment.{perm.action}", bool(mx and mx <= lim["max_single_payment_minor"]), f"Per-transaction maximum ≤ bank cap {lim['max_single_payment_minor']}")
    if any(p.action in taxonomy.MONEY_MOVING for p in m.permissions):
        agg = m.aggregate_constraints
        _check(bank, "policy.aggregate_required", bool(agg.maximum_monthly_amount_minor or agg.maximum_daily_amount_minor), "Money-moving mandates must carry a cumulative (daily or monthly) limit")
    return sem, bank


def validate_content(s, content: dict, *, parent: dict | None = None) -> dict:
    """Full validation without persisting: schema, semantic, bank policy, SHACL."""
    report: dict = {"ok": False, "schema": {"ok": False, "errors": []}, "semantic": {"ok": False, "checks": []}, "bank_policy": {"ok": False, "checks": []}, "shacl": {"conforms": False, "results": []}}
    try:
        m = Mandate.model_validate(content)
    except ValidationError as e:
        report["schema"]["errors"] = [{"path": ".".join(str(x) for x in err["loc"]), "message": err["msg"]} for err in e.errors()]
        return report
    report["schema"]["ok"] = True
    sem, bank = semantic_checks(s, m)
    report["semantic"] = {"ok": all(c["ok"] for c in sem), "checks": sem}
    report["bank_policy"] = {"ok": all(c["ok"] for c in bank), "checks": bank}
    g = ontology_service.mandate_graph(m, canon.digest(m.model_dump()))
    if parent:
        pm = Mandate.model_validate(parent)
        ontology_service.add_parent_facts(g, pm, canon.digest(pm.model_dump()))
    report["shacl"] = ontology_service.validate_graph(g)
    report["ok"] = report["schema"]["ok"] and report["semantic"]["ok"] and report["bank_policy"]["ok"] and report["shacl"]["conforms"]
    return report


# --------------------------------------------------------------------------- studio compile


def _jsonable(o):
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def compile_full(s, *, principal_id: str, instruction: str | None = None, cnl_text: str | None = None, resolutions: dict | None = None,
                 reference_time: str | None = None) -> dict:
    """Mandate Studio pipeline. Deterministic for a given input and reference time. Never invents authority."""
    reference_time = reference_time or clock.iso(clock.now()).split(".")[0] + "Z"
    resolver = cnl.Resolver.from_session(s)
    ambiguities = cnl.detect_ambiguities(instruction) if instruction else []
    proposed = None
    unresolved: list[dict] = []
    if cnl_text is None and resolutions:
        try:
            proposed = cnl.propose_cnl(resolutions, resolver)
            cnl_text = proposed
        except ValueError as e:
            unresolved.append({"code": "UNRESOLVED", "message": str(e)})
    out: dict = {
        "original_intent": instruction, "cnl_version": config.CNL_VERSION, "ambiguities": ambiguities, "required_resolutions": [{"id": k, "question": q} for k, q in cnl.REQUIRED_RESOLUTIONS],
        "proposed_cnl": proposed, "ok": False, "errors": unresolved, "reference_time": reference_time,
    }
    if cnl_text is None:
        out["errors"] = out["errors"] or [{"code": "UNRESOLVED", "message": "Authority is not yet fully specified. Resolve the ambiguities; nothing is invented."}]
        return out
    r = cnl.compile_cnl(cnl_text, principal_id, resolver, default_not_before=reference_time)
    out.update(ok=r["ok"], errors=r["errors"], ast=r["ast"], cnl_input=cnl_text)
    if not r["ok"]:
        return out
    m = r["mandate"]
    digest = r["canonical_digest"]
    report = validate_content(s, m)
    mm = Mandate.model_validate(m)
    g = ontology_service.mandate_graph(mm, digest)
    names = {a.id: a.name for a in s.execute(select(db.Account)).scalars()}
    names.update({p.id: p.name for p in s.execute(select(db.Payee)).scalars()})
    for ag in s.execute(select(db.Agent)).scalars():
        names[ag.id] = ag.display_name
        names[ag.declared.get("operator_id", "")] = ag.declared.get("operating_organization", "")
    agent = s.get(db.Agent, m["mandatary"]["agent_id"])
    pol = config.policy_config()
    from . import agents as agents_mod

    out.update(
        normalized_cnl=r["normalized_cnl"], defaults_applied=r["defaults_applied"], mandate=m, canonical_digest=digest,
        json_ld=ontology_service.to_jsonld(g), turtle=ontology_service.to_turtle(g), shacl=report["shacl"], validation=report,
        oauth={
            "scopes": cnl.oauth_scopes(m), "authorization_details": cnl.authorization_details(m, digest),
            "kym_token_claims": {f"{config.CLAIM_NS}mandate_id": m["mandate_id"], f"{config.CLAIM_NS}mandate_version": m["version"], f"{config.CLAIM_NS}mandate_hash": "(bound at approval)"},
            "scope_gaps": [{"dimension": d, "carried_by": c} for d, c in taxonomy.SCOPE_GAPS],
        },
        runtime_policy=_jsonable(policy.runtime_policy(m, digest)),
        consent_summary={"en": cnl.consent_summary(m, names, "en"), "fr": cnl.consent_summary(m, names, "fr")},
        effective_permissions=policy.effective_permissions(
            m, controlled_accounts=kyc.controlled_accounts(s, principal_id), agent_capabilities=set(agents_mod.capabilities(agent)) if agent else set(),
            agent_status=agent.status if agent else "UNREGISTERED", policy=pol),
    )
    return out


# --------------------------------------------------------------------------- lifecycle


def _event(s, state: str, row: db.MandateRow, *, actor_id: str, actor_type: str, payload: dict, correlation_id: str | None = None):
    ledger.append(s, EVENT_FOR[state], actor_id=actor_id, actor_type=actor_type, principal_id=row.principal_id, agent_id=row.agent_id,
                  mandate_id=row.mandate_id, mandate_version=row.version, correlation_id=correlation_id,
                  policy_version=row.content["policy_version"], payload={"to_state": state, "digest": row.digest, **payload})


def transition(s, mandate_id: str, version: int, to: str, *, actor_id: str, actor_type: str, reason: str = "", extra: dict | None = None) -> db.MandateState:
    st = get_state(s, mandate_id, version)
    if to not in TRANSITIONS[st.status]:
        raise MandateError(f"transition {st.status} -> {to} is not allowed", "INVALID_TRANSITION")
    row = get_row(s, mandate_id, version)
    frm = st.status
    st.history = [*st.history, {"from": frm, "to": to, "at": clock.iso(), "actor": actor_id, "reason": reason}]
    st.status, st.updated_at, st.reason = to, clock.iso(), reason
    s.flush()
    _event(s, to, row, actor_id=actor_id, actor_type=actor_type, payload={"from_state": frm, "reason": reason, **(extra or {})})
    return st


def propose(s, content: dict, *, created_by: str, actor_type: str = "customer", artifacts: dict | None = None, mandate_id: str | None = None,
            version: int | None = None, parent: dict | None = None) -> dict:
    """Create an immutable mandate version and run it through validation. It cannot become ACTIVE without customer approval."""
    content = dict(content)
    mid = mandate_id or (content.get("mandate_id") if content.get("mandate_id") not in (None, "mdt_DRAFT") else None) or f"mdt_{uuid.uuid4().hex[:10]}"
    content["mandate_id"] = mid
    content["version"] = version or 1
    try:
        m = Mandate.model_validate(content)
    except ValidationError as e:
        raise MandateError("mandate schema validation failed", "SCHEMA_VIOLATION", [{"path": ".".join(str(x) for x in er["loc"]), "message": er["msg"]} for er in e.errors()]) from e
    content = m.model_dump()
    if s.get(db.MandateRow, (mid, content["version"])):
        raise MandateError("mandate version already exists; versions are immutable", "VERSION_EXISTS")
    digest = canon.digest(content)
    s.add(db.MandateRow(mandate_id=mid, version=content["version"], content=content, digest=digest, created_at=clock.iso(), created_by=created_by,
                        principal_id=m.principal.id, agent_id=m.mandatary.agent_id,
                        parent_mandate_id=m.lineage.parent_mandate_id if m.lineage else None, compile_artifacts=artifacts or {}))
    s.add(db.MandateState(mandate_id=mid, version=content["version"], status="DRAFT", updated_at=clock.iso(), reason="created", history=[{"from": None, "to": "DRAFT", "at": clock.iso(), "actor": created_by, "reason": "created"}]))
    s.flush()
    row = get_row(s, mid, content["version"])
    _event(s, "DRAFT", row, actor_id=created_by, actor_type=actor_type, payload={"from_state": None})
    transition(s, mid, content["version"], "PENDING_VALIDATION", actor_id="meridian-mandate-registry", actor_type="bank_system", reason="validation started")
    report = validate_content(s, content, parent=parent)
    st = get_state(s, mid, content["version"])
    st.validation = report
    if report["ok"]:
        transition(s, mid, content["version"], "VALIDATED", actor_id="meridian-mandate-registry", actor_type="bank_system", reason="schema, semantic, bank policy and SHACL checks passed")
        transition(s, mid, content["version"], "PENDING_CUSTOMER_APPROVAL", actor_id="meridian-mandate-registry", actor_type="bank_system", reason="awaiting customer approval in bank-controlled interface")
    else:
        failed = [c["id"] for c in report["semantic"]["checks"] + report["bank_policy"]["checks"] if not c["ok"]] + [r["message"] for r in report["shacl"]["results"]]
        transition(s, mid, content["version"], "REJECTED", actor_id="meridian-mandate-registry", actor_type="bank_system", reason="validation failed", extra={"failed": failed[:20]})
    return view(s, mid, content["version"])


def _approver_ok(s, approver_id: str, principal_id: str) -> bool:
    return kyc.can_act_for(s, approver_id, principal_id) and (approver_id == principal_id or approver_id in kyc.signatories(s, principal_id))


def approve(s, mandate_id: str, version: int, *, approver_id: str, presented_digest: str, language: str = "en", actor_type: str = "customer") -> dict:
    """Customer approval in the bank-controlled interface. Binds the approval to the exact mandate digest."""
    row = get_row(s, mandate_id, version)
    st = get_state(s, mandate_id, version)
    if st.status != "PENDING_CUSTOMER_APPROVAL":
        raise MandateError(f"mandate is {st.status}, not PENDING_CUSTOMER_APPROVAL", "INVALID_TRANSITION")
    if presented_digest != row.digest:
        raise MandateError("the digest presented to the customer does not match the stored mandate (substitution prevented)", "DIGEST_MISMATCH")
    if not _approver_ok(s, approver_id, row.principal_id):
        raise MandateError("approver is not the principal or an authorized signatory", "NOT_AUTHORIZED")
    if row.parent_mandate_id:
        raise MandateError("delegated mandates are authorized through their parent mandate", "NOT_AUTHORIZED")
    m = row.content
    names = {a.id: a.name for a in s.execute(select(db.Account)).scalars()}
    summary = cnl.consent_summary(m, names, language)
    receipt = {
        "receipt_id": f"cr_{uuid.uuid4().hex[:12]}", "kind": "CUSTOMER_APPROVAL", "mandate_id": mandate_id, "mandate_version": version,
        "mandate_digest": row.digest, "principal_id": row.principal_id, "approver_id": approver_id, "approved_at": clock.iso(),
        "presented_summary_digest": canon.digest({"lang": language, "text": summary}), "assurance": ASSURANCE,
        "legal_note": "Evidence of integrity and key control only; not proof of legally effective consent.",
    }
    key = keys.customer_consent_key(approver_id)
    sig = key.sign(CONSENT_DOMAIN + canon.canonical(receipt))
    s.add(db.Consent(id=receipt["receipt_id"], mandate_id=mandate_id, version=version, digest=row.digest, customer_id=approver_id, receipt=receipt, signature=sig, key_id=key.kid, created_at=clock.iso()))
    s.flush()
    ledger.append(s, "MANDATE_APPROVED", actor_id=approver_id, actor_type=actor_type, principal_id=row.principal_id, agent_id=row.agent_id, mandate_id=mandate_id, mandate_version=version,
                  policy_version=m["policy_version"], payload={"receipt_id": receipt["receipt_id"], "digest": row.digest, "assurance": ASSURANCE["level"], "signature_key_id": key.kid})
    return {"receipt": receipt, "signature": sig, "key_id": key.kid}


def reject(s, mandate_id: str, version: int, *, actor_id: str, reason: str = "rejected by customer") -> dict:
    transition(s, mandate_id, version, "REJECTED", actor_id=actor_id, actor_type="customer", reason=reason)
    return view(s, mandate_id, version)


def verify_consent(s, consent: db.Consent) -> bool:
    pub = keys.customer_consent_key(consent.customer_id).public_b64u
    return keys.verify_ed25519(pub, CONSENT_DOMAIN + canon.canonical(consent.receipt), consent.signature)


def activate(s, mandate_id: str, version: int, *, actor_id: str, actor_type: str = "bank_operator") -> dict:
    """Requires: eligible principal and agent, passing validation re-run, and verified customer approval bound to the digest."""
    row = get_row(s, mandate_id, version)
    st = get_state(s, mandate_id, version)
    if st.status != "PENDING_CUSTOMER_APPROVAL":
        raise MandateError(f"mandate is {st.status}; it cannot be activated", "INVALID_TRANSITION")
    consent = s.execute(select(db.Consent).where(db.Consent.mandate_id == mandate_id, db.Consent.version == version)).scalar_one_or_none()
    if not consent:
        raise MandateError("no customer approval evidence: an unapproved mandate cannot be activated", "APPROVAL_MISSING")
    if consent.digest != row.digest or canon.digest(row.content) != row.digest:
        raise MandateError("approval is not bound to this mandate content", "DIGEST_MISMATCH")
    if not row.parent_mandate_id and not verify_consent(s, consent):
        raise MandateError("consent receipt signature invalid", "APPROVAL_INVALID")
    parent = None
    if row.parent_mandate_id:
        lin = row.content["lineage"]
        pst = get_state(s, lin["parent_mandate_id"], lin["parent_mandate_version"])
        if pst.status != "ACTIVE":
            raise MandateError("parent mandate is not active", "PARENT_NOT_ACTIVE")
        parent = get_row(s, lin["parent_mandate_id"], lin["parent_mandate_version"]).content
    report = validate_content(s, row.content, parent=parent)
    if not report["ok"]:
        raise MandateError("mandate no longer passes validation", "VALIDATION_FAILED", [c for c in report["semantic"]["checks"] + report["bank_policy"]["checks"] if not c["ok"]])
    prev = active_version(s, mandate_id)
    transition(s, mandate_id, version, "ACTIVE", actor_id=actor_id, actor_type=actor_type, reason="approved and validated", extra={"consent_receipt": consent.id})
    if prev and prev != version:
        transition(s, mandate_id, prev, "SUPERSEDED", actor_id="meridian-mandate-registry", actor_type="bank_system", reason=f"superseded by version {version}")
    return view(s, mandate_id, version)


def amend(s, mandate_id: str, new_content: dict, *, actor_id: str) -> dict:
    """Authority changes create a NEW immutable version that needs fresh customer approval."""
    cur_v = active_version(s, mandate_id)
    if cur_v is None:
        raise MandateError("only an active or suspended mandate can be amended", "INVALID_TRANSITION")
    cur = get_row(s, mandate_id, cur_v)
    if not can_amend(s, actor_id, cur.principal_id):
        raise MandateError("not authorized to amend this mandate", "NOT_AUTHORIZED")
    latest = get_row(s, mandate_id).version
    nc = dict(new_content)
    if nc["principal"] != cur.content["principal"] or nc["mandatary"] != cur.content["mandatary"]:
        raise MandateError("amendment cannot change principal or mandatary; create a new mandate", "IMMUTABLE_FIELD")
    parent = None
    if cur.parent_mandate_id:
        lin = cur.content["lineage"]
        parent = get_row(s, lin["parent_mandate_id"], lin["parent_mandate_version"]).content
        nc["lineage"] = lin
    res = propose(s, nc, created_by=actor_id, actor_type="customer", mandate_id=mandate_id, version=latest + 1, parent=parent)
    row = get_row(s, mandate_id, latest + 1)
    ledger.append(s, "MANDATE_AMENDED", actor_id=actor_id, actor_type="customer", principal_id=row.principal_id, agent_id=row.agent_id, mandate_id=mandate_id, mandate_version=row.version,
                  payload={"previous_version": cur_v, "new_digest": row.digest, "previous_digest": cur.digest})
    return res


def can_amend(s, actor_id: str, principal_id: str) -> bool:
    return actor_id in ("admin_001", "demo_scenario_runner") or kyc.can_act_for(s, actor_id, principal_id)


def suspend(s, mandate_id: str, *, actor_id: str, actor_type: str = "customer", reason: str = "suspended by customer") -> dict:
    v = active_version(s, mandate_id)
    if v is None or get_state(s, mandate_id, v).status != "ACTIVE":
        raise MandateError("only an ACTIVE mandate can be suspended", "INVALID_TRANSITION")
    transition(s, mandate_id, v, "SUSPENDED", actor_id=actor_id, actor_type=actor_type, reason=reason)
    return view(s, mandate_id, v)


def resume(s, mandate_id: str, *, actor_id: str, actor_type: str = "customer") -> dict:
    v = active_version(s, mandate_id)
    if v is None or get_state(s, mandate_id, v).status != "SUSPENDED":
        raise MandateError("only a SUSPENDED mandate can be resumed", "INVALID_TRANSITION")
    transition(s, mandate_id, v, "ACTIVE", actor_id=actor_id, actor_type=actor_type, reason="resumed")
    return view(s, mandate_id, v)


def descendants(s, mandate_id: str) -> list[tuple[str, int]]:
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int]] = []
    frontier = [mandate_id]
    visited = {mandate_id}
    while frontier:
        cur = frontier.pop()
        for d in s.execute(select(db.DelegationRow).where(db.DelegationRow.parent_id == cur)).scalars():
            key = (d.child_id, d.child_version)
            if key not in seen:
                seen.add(key)
                out.append(key)
            if d.child_id not in visited:
                visited.add(d.child_id)
                frontier.append(d.child_id)
    return out


def revoke(s, mandate_id: str, *, actor_id: str, actor_type: str = "customer", reason: str = "revoked by customer", cascade_cause: str | None = None, revoke_tokens: bool = True) -> dict:
    """Immediate revocation: later authorization decisions deny regardless of token validity. Cascades to delegated children."""
    t0 = time.perf_counter()
    rows = s.execute(select(db.MandateState).where(db.MandateState.mandate_id == mandate_id)).scalars().all()
    live = [r for r in rows if r.status in ("ACTIVE", "SUSPENDED", "PENDING_CUSTOMER_APPROVAL", "VALIDATED")]
    if not live:
        raise MandateError("no revocable version of this mandate", "INVALID_TRANSITION")
    affected = {mandate_id}
    for r in live:
        if r.status in ("VALIDATED",):
            transition(s, mandate_id, r.version, "REJECTED", actor_id=actor_id, actor_type=actor_type, reason=reason)
        elif r.status == "PENDING_CUSTOMER_APPROVAL":
            transition(s, mandate_id, r.version, "REJECTED", actor_id=actor_id, actor_type=actor_type, reason=reason)
        else:
            transition(s, mandate_id, r.version, "REVOKED", actor_id=actor_id, actor_type=actor_type, reason=reason, extra={"cause": cascade_cause or "DIRECT"})
    cascaded = []
    for cid, cver in descendants(s, mandate_id):
        st = get_state(s, cid, cver)
        affected.add(cid)
        if st.status in ("ACTIVE", "SUSPENDED"):
            transition(s, cid, cver, "REVOKED", actor_id="meridian-mandate-registry", actor_type="bank_system", reason=f"parent mandate {mandate_id} revoked", extra={"cause": "PARENT_REVOKED", "parent": mandate_id})
            cascaded.append({"mandate_id": cid, "version": cver})
    now = clock.iso()
    revoked_tokens = 0
    # Defense in depth only: authority is decided per request from mandate state, so a token that stays "active" at the OAuth layer is still refused.
    for t in s.execute(select(db.Token).where(db.Token.mandate_id.in_(list(affected)), db.Token.revoked_at.is_(None))).scalars() if revoke_tokens else []:
        t.revoked_at = now
        revoked_tokens += 1
    from . import bank

    cancelled = bank.cancel_pending(s, list(affected), reason=f"mandate {mandate_id} revoked", actor_id=actor_id)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    return {"mandate_id": mandate_id, "revoked_versions": [r.version for r in live], "cascaded": cascaded, "tokens_revoked": revoked_tokens,
            "pending_operations_cancelled": cancelled, "propagation_ms": ms,
            "note": "Revocation stops future authorization. It does not reverse payments already executed."}


def expire_due(s) -> list[str]:
    """Sweeper: mark ACTIVE mandates past expiry as EXPIRED (the PDP also checks the validity window on every request)."""
    done = []
    now = clock.now()
    for st in s.execute(select(db.MandateState).where(db.MandateState.status.in_(["ACTIVE", "SUSPENDED"]))).scalars().all():
        row = get_row(s, st.mandate_id, st.version)
        if clock.parse(row.content["validity"]["expires_at"]) <= now:
            transition(s, st.mandate_id, st.version, "EXPIRED", actor_id="meridian-mandate-registry", actor_type="bank_system", reason="validity ended")
            done.append(st.mandate_id)
    return done


# --------------------------------------------------------------------------- delegation


def _chain_agent_ids(s, row: db.MandateRow) -> list[str]:
    ids, seen = [], set()
    cur = row
    while cur is not None and (cur.mandate_id, cur.version) not in seen:
        seen.add((cur.mandate_id, cur.version))
        ids.append(cur.agent_id)
        lin = cur.content.get("lineage")
        cur = get_row(s, lin["parent_mandate_id"], lin["parent_mandate_version"]) if lin else None
    return ids


def delegate(s, parent_id: str, child_content: dict, *, requested_by: str, requested_by_type: str, correlation_id: str | None = None) -> dict:
    """Create a bank-validated child mandate. A child can never expand any dimension of its parent."""
    pv = active_version(s, parent_id)
    if pv is None:
        raise MandateError("parent mandate is not active", "PARENT_NOT_ACTIVE")
    prow = get_row(s, parent_id, pv)
    pst = get_state(s, parent_id, pv)
    if pst.status != "ACTIVE":
        raise MandateError("parent mandate is not ACTIVE", "PARENT_NOT_ACTIVE")
    child = dict(child_content)
    depth = (prow.content["lineage"]["depth"] + 1) if prow.content.get("lineage") else 1
    child["lineage"] = {"parent_mandate_id": parent_id, "parent_mandate_version": pv, "depth": depth}
    try:
        cm = Mandate.model_validate({**child, "mandate_id": "mdt_DRAFT"})
    except ValidationError as e:
        raise MandateError("child mandate schema validation failed", "SCHEMA_VIOLATION", [{"path": ".".join(str(x) for x in er["loc"]), "message": er["msg"]} for er in e.errors()]) from e
    violations = policy.attenuation_violations(prow.content, cm.model_dump(), _chain_agent_ids(s, prow))
    if violations:
        ledger.append(s, "ACTION_DENIED", actor_id=requested_by, actor_type=requested_by_type, principal_id=prow.principal_id, agent_id=prow.agent_id, mandate_id=parent_id, mandate_version=pv,
                      correlation_id=correlation_id, payload={"action": "mandates.delegate", "reason_codes": sorted({v["code"] for v in violations}), "violations": violations, "child_agent": cm.mandatary.agent_id})
        raise MandateError("delegation rejected: child authority exceeds parent", violations[0]["code"], violations)
    res = propose(s, child, created_by=requested_by, actor_type=requested_by_type, parent=prow.content, artifacts={"delegated_by": requested_by})
    cid, cver = res["mandate_id"], res["version"]
    crow = get_row(s, cid, cver)
    if res["status"] != "PENDING_CUSTOMER_APPROVAL":
        raise MandateError("child mandate failed validation", "VALIDATION_FAILED", [c for c in res["validation"]["semantic"]["checks"] + res["validation"]["bank_policy"]["checks"] if not c["ok"]] + res["validation"]["shacl"]["results"])
    parent_consent = s.execute(select(db.Consent).where(db.Consent.mandate_id == parent_id, db.Consent.version == pv)).scalar_one()
    receipt = {"receipt_id": f"cr_{uuid.uuid4().hex[:12]}", "kind": "DELEGATED_WITHIN_PARENT_CONSENT", "mandate_id": cid, "mandate_version": cver, "mandate_digest": crow.digest,
               "parent_consent_receipt": parent_consent.id, "parent_mandate_digest": prow.digest, "principal_id": crow.principal_id, "approved_at": clock.iso(),
               "assurance": {"level": "BANK_VALIDATED_ATTENUATION", "description": "The customer approved delegation within bounds in the parent mandate; the bank verified the child is a strict attenuation."}}
    bk = keys.ledger_key()
    s.add(db.Consent(id=receipt["receipt_id"], mandate_id=cid, version=cver, digest=crow.digest, customer_id=crow.principal_id, receipt=receipt, signature=bk.sign(CONSENT_DOMAIN + canon.canonical(receipt)), key_id=bk.kid, created_at=clock.iso()))
    s.add(db.DelegationRow(id=f"dlg_{uuid.uuid4().hex[:10]}", parent_id=parent_id, parent_version=pv, child_id=cid, child_version=cver, validated_at=clock.iso(), validated_by="meridian-delegation-validator"))
    s.flush()
    transition(s, cid, cver, "ACTIVE", actor_id="meridian-delegation-validator", actor_type="bank_system", reason="bank-validated attenuation of parent mandate", extra={"parent": parent_id})
    ledger.append(s, "MANDATE_DELEGATED", actor_id=requested_by, actor_type=requested_by_type, principal_id=crow.principal_id, agent_id=prow.agent_id, mandate_id=parent_id, mandate_version=pv,
                  correlation_id=correlation_id, payload={"child_mandate_id": cid, "child_version": cver, "child_agent": crow.agent_id, "child_digest": crow.digest, "depth": depth})
    return view(s, cid, cver)
