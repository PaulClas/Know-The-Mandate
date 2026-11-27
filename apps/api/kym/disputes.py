"""Dispute reconstruction and exportable evidence packages."""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from . import canon, clock, config, db, keys, ledger, mandates, ontology_service, policy, responsibility
from .canon import domain_hash
from .schemas import Mandate


class DisputeError(ValueError):
    pass


TITLES = {
    "ACTION_REQUESTED": "Agent requested the operation", "POLICY_EVALUATED": "Policy decision point evaluated", "RISK_EVALUATED": "Risk engine assessed",
    "ACTION_DENIED": "Action denied", "HUMAN_APPROVAL_REQUESTED": "Human approval requested", "HUMAN_APPROVAL_GRANTED": "Human approval granted",
    "HUMAN_APPROVAL_REJECTED": "Human approval rejected", "PAYMENT_EXECUTED": "Payment executed", "PAYMENT_FAILED": "Payment failed",
    "TOKEN_ISSUED": "Mandate-bound credential issued", "MANDATE_APPROVED": "Customer approved the mandate", "MANDATE_ACTIVATED": "Mandate activated",
    "MANDATE_REVOKED": "Mandate revoked", "MANDATE_AMENDED": "Mandate amended", "MANDATE_SUSPENDED": "Mandate suspended", "MANDATE_DELEGATED": "Authority delegated",
    "DISPUTE_OPENED": "Dispute opened", "MANDATE_VALIDATED": "Mandate validated", "MANDATE_PROPOSED": "Mandate proposed", "AGENT_SUSPENDED": "Agent status changed",
}


def _detail(e: dict, payload: dict | None) -> str:
    p = payload or {}
    et = e["event_type"]
    if et == "POLICY_EVALUATED":
        return f"{p.get('decision')} {p.get('reason_codes') or ''} (policy {e['policy_version']})"
    if et == "RISK_EVALUATED":
        return f"score {p.get('score')} ({p.get('level')}), triggered: {', '.join(p.get('triggered', [])) or 'none'}"
    if et == "ACTION_REQUESTED":
        return f"{p.get('action')} amount {p.get('amount_minor')} {p.get('currency') or ''} -> {p.get('counterparty')}"
    if et == "PAYMENT_EXECUTED":
        return f"{p.get('amount_minor')} {p.get('currency')} from {p.get('debit_account')} to {p.get('credit_account')}"
    if et.startswith("MANDATE_"):
        return f"v{e['mandate_version']} {p.get('from_state', '')} -> {p.get('to_state', '')} {p.get('reason', '')}".strip()
    return json.dumps({k: v for k, v in p.items() if k not in ("inputs",)})[:200]


def build_package(s, tx_id: str) -> dict:
    tx = s.get(db.Transaction, tx_id)
    if not tx:
        raise DisputeError("transaction not found")
    cust = s.get(db.Customer, tx.principal_id)
    agent = s.get(db.Agent, tx.agent_id)
    decision = s.get(db.Decision, tx.decision_id) if tx.decision_id else None
    mrow = s.get(db.MandateRow, (tx.mandate_id, tx.mandate_version)) if tx.mandate_id else None
    mstate = mandates.get_state(s, tx.mandate_id, tx.mandate_version) if mrow else None
    consent = s.execute(select(db.Consent).where(db.Consent.mandate_id == tx.mandate_id, db.Consent.version == tx.mandate_version)).scalar_one_or_none() if mrow else None
    jti = (decision.inputs.get("token", {}) or {}).get("jti") if decision else None
    token = s.get(db.Token, jti) if jti else None
    approvals = s.execute(select(db.Approval).where(db.Approval.tx_id == tx.id)).scalars().all()
    postings = [{"account_id": p.account_id, "debit_minor": p.debit_minor, "credit_minor": p.credit_minor, "currency": p.currency, "kind": p.kind} for p in s.execute(select(db.Posting).where(db.Posting.tx_id == tx.id)).scalars()]

    all_events = ledger.all_events(s)
    payloads = ledger.payload_map(s)
    related_mandates = {tx.mandate_id, *(tx.mandate_chain or [])} - {None}
    tx_events = [e for e in all_events if e.get("transaction_id") == tx.id]
    mandate_events = [e for e in all_events if e.get("mandate_id") in related_mandates and e["event_type"].startswith(("MANDATE_", "TOKEN_")) and (e["event_type"] != "TOKEN_ISSUED" or (payloads.get(e["event_id"], {}).get("payload") or {}).get("jti") == jti)]
    agent_events = [e for e in all_events if e.get("agent_id") == tx.agent_id and e["event_type"] in ("AGENT_REGISTERED", "AGENT_VERIFIED", "AGENT_SUSPENDED")]
    cust_events = [e for e in all_events if e["event_type"] == "CUSTOMER_VERIFIED" and e.get("principal_id") == tx.principal_id]
    included = {e["event_id"]: e for e in [*cust_events, *agent_events, *mandate_events, *tx_events]}
    last_tx_seq = max((e["sequence"] for e in tx_events), default=0)
    subsequent = [e for e in mandate_events if e["sequence"] > last_tx_seq and e["event_type"] in ("MANDATE_REVOKED", "MANDATE_AMENDED", "MANDATE_SUSPENDED", "MANDATE_SUPERSEDED", "MANDATE_DELEGATED")]
    events = sorted(included.values(), key=lambda e: e["sequence"])
    max_seq = events[-1]["sequence"] if events else 0
    spine = [{"sequence": e["sequence"], "event_hash": e["event_hash"], "previous_hash": e["previous_hash"]} for e in all_events if e["sequence"] <= max_seq]
    cps = [c for c in ledger.checkpoints(s) if c["sequence"] <= max_seq or True]
    replay = None
    if decision:
        r = policy.replay(decision.inputs)
        replay = {"matches": r["decision"] == decision.decision and r["reason_codes"] == decision.reason_codes, "replayed_decision": r["decision"], "replayed_reason_codes": r["reason_codes"],
                  "policy_version": decision.policy_version, "inputs_digest_ok": canon.digest(decision.inputs) == decision.inputs_digest}

    timeline = [{"at": e["timestamp"], "seq": e["sequence"], "event_type": e["event_type"], "event_id": e["event_id"], "title": TITLES.get(e["event_type"], e["event_type"]), "actor": f"{e['actor_type']}:{e['actor_id']}",
                 "detail": _detail(e, (payloads.get(e["event_id"]) or {}).get("payload"))} for e in events]
    operator_name = agent.declared.get("operating_organization") if agent else None
    approvers = sorted({g["approver_id"] for a in approvals for g in a.grants if g["decision"] == "APPROVE"})
    pkg = {
        "package_version": "1.0", "generated_at": clock.iso(), "ontology_version": config.ONTOLOGY_VERSION,
        "transaction": {"id": tx.id, "status": tx.status, "action": tx.action, "amount_minor": tx.amount_minor, "currency": tx.currency, "account_id": tx.account_id, "payee_id": tx.payee_id,
                        "created_at": tx.created_at, "updated_at": tx.updated_at, "failure_reason": tx.failure_reason, "correlation_id": tx.correlation_id, "dispute": tx.dispute},
        "customer": None if not cust else {"id": cust.id, "name": cust.name, "type": cust.type, "jurisdiction": cust.jurisdiction, "kyc_status": cust.kyc_status, "kyc_evidence_ref": cust.kyc_evidence_ref,
                                          "note": "Simulated KYC; synthetic person"},
        "agent": None if not agent else {"id": agent.id, "display_name": agent.display_name, "status_now": agent.status, "client_id": agent.client_id, "build_digest": agent.declared.get("build_digest"),
                                        "key_thumbprint": agent.verified.get("key_thumbprint"), "verified_facts": agent.verified, "declared_metadata": {k: v for k, v in agent.declared.items() if k != "proof_of_possession"}},
        "operator": {"id": agent.declared.get("operator_id") if agent else None, "name": operator_name, "responsible_party": agent.declared.get("responsible_party") if agent else None},
        "mandate": None if not mrow else {"content": mrow.content, "digest": mrow.digest, "status_now": mstate.status, "state_history": mstate.history,
                                         "json_ld": ontology_service.to_jsonld(ontology_service.mandate_graph(Mandate.model_validate(mrow.content), mrow.digest)), "chain": tx.mandate_chain},
        "consent": None if not consent else {"receipt": consent.receipt, "signature": consent.signature, "key_id": consent.key_id, "signature_valid": (mandates.verify_consent(s, consent) if consent.receipt.get("kind") == "CUSTOMER_APPROVAL" else None)},
        "oauth_grant": None if not token else {"jti": token.jti, "scope": token.scope, "aud": token.aud, "issued_at": token.issued_at, "expires_at": token.expires_at, "revoked_at": token.revoked_at,
                                              "cnf_jkt": token.cnf_jkt, "mandate_id": token.mandate_id, "mandate_version": token.mandate_version, "authorization_details": token.authorization_details,
                                              "note": "Token metadata only; the reusable token is never stored."},
        "operation": {"operation": tx.operation, "op_hash": tx.op_hash},
        "policy": None if not decision else {"version": decision.policy_version, "decision_id": decision.id, "decision": decision.decision, "reason_codes": decision.reason_codes, "trace": decision.trace,
                                            "inputs_digest": decision.inputs_digest, "inputs": decision.inputs, "signature": decision.signature, "key_id": decision.key_id, "replay": replay},
        "risk": tx.risk or None,
        "approvals": [{"id": a.id, "status": a.status, "op_hash": a.op_hash, "required": a.required_count, "grants": [{k: v for k, v in g.items() if k != "signature"} for g in a.grants], "expires_at": a.expires_at, "bound_to_operation": a.op_hash == tx.op_hash} for a in approvals],
        "execution": {"status": tx.status, "postings": postings, "balanced": sum(p["debit_minor"] for p in postings) == sum(p["credit_minor"] for p in postings)},
        "subsequent_events": subsequent,
        "ledger_events": [{**e, "payload": (payloads.get(e["event_id"]) or {}).get("payload")} for e in events],
        "chain_spine": spine, "checkpoints": cps, "public_keys": keys.public_key_registry(),
        "timeline": timeline,
        "responsibility": {
            "attribution": responsibility.attribution(principal_name=cust.name if cust else tx.principal_id, agent={"id": tx.agent_id, "display_name": agent.display_name if agent else tx.agent_id}, operator_name=operator_name or "unknown",
                                                      approvers=approvers, executed=tx.status == "EXECUTED", ledger_ref=f"{len(events)} signed events, head seq {max_seq}"),
            "can_establish": responsibility.CAN_ESTABLISH, "cannot_establish": responsibility.CANNOT_ESTABLISH, "levels": responsibility.matrix()["levels"], "faults": responsibility.FAULTS,
            "disclaimer": "No liability determination is made. Final adjudicated liability is outside this system.",
        },
        "limitations": ["A valid signature demonstrates integrity and control of a signing key under stated assumptions; it does not establish legally effective consent.",
                        "Demo keys are server-held; synthetic data only."],
    }
    pkg["verification"] = verify_package(pkg, trusted_keys=keys.public_key_registry())
    return pkg


def _ed_keys(reg: dict) -> dict:
    return {v["kid"]: v["x"] for v in reg.values() if isinstance(v, dict) and "x" in v and v.get("alg") == "Ed25519"}


def _binding_problems(pkg: dict) -> list[dict]:
    """The displayed transaction, decision and replay result are unsigned report fields. Bind them to the signed ledger payloads and recompute the
    replay locally, so a package cannot show one story while its signed evidence says another (or says nothing)."""
    out: list[dict] = []
    txn = pkg.get("transaction") or {}
    tx_id = txn.get("id")
    mine = [e for e in pkg.get("ledger_events", []) if e.get("transaction_id") == tx_id]

    def payload(event_type: str, **match) -> dict | None:
        for e in mine:
            p = e.get("payload")
            if e["event_type"] == event_type and isinstance(p, dict) and all(p.get(k) == v for k, v in match.items()):
                return p
        return None

    req = payload("ACTION_REQUESTED")
    if req is None:
        return [{"check": "evidence_binding", "detail": "no signed ACTION_REQUESTED evidence (with its payload) exists for the displayed transaction"}]
    shown = {"amount_minor": txn.get("amount_minor") or 0, "currency": txn.get("currency") or "", "account_id": txn.get("account_id"), "op_hash": (pkg.get("operation") or {}).get("op_hash")}
    signed = {"amount_minor": req.get("amount_minor") or 0, "currency": req.get("currency") or "", "account_id": req.get("account_id"), "op_hash": req.get("op_hash")}
    for k in shown:
        if shown[k] != signed[k]:
            out.append({"check": "evidence_binding", "detail": f"displayed {k}={shown[k]!r} differs from signed evidence {signed[k]!r}"})
    if txn.get("payee_id") and txn["payee_id"] != req.get("counterparty"):
        out.append({"check": "evidence_binding", "detail": "displayed payee differs from the signed evidence"})
    pol = pkg.get("policy")
    if pol:
        ev = payload("POLICY_EVALUATED", decision_id=pol.get("decision_id"))
        if ev is None:
            out.append({"check": "evidence_binding", "detail": "no signed POLICY_EVALUATED evidence for the displayed decision"})
        else:
            digest_ok = canon.digest(pol.get("inputs")) == ev.get("inputs_digest")
            replayed = policy.replay(pol["inputs"]) if digest_ok else None
            if not digest_ok:
                out.append({"check": "decision_inputs", "detail": "decision inputs do not match the signed inputs_digest"})
            elif replayed["decision"] != ev.get("decision") or replayed["reason_codes"] != ev.get("reason_codes"):
                out.append({"check": "decision_replay", "detail": "recomputed replay differs from the signed decision (policy engine or inputs changed)"})
            if pol.get("decision") != ev.get("decision"):
                out.append({"check": "evidence_binding", "detail": "displayed decision differs from the signed evidence"})
    if txn.get("status") == "EXECUTED":
        done = payload("PAYMENT_EXECUTED")
        if done is None or (done.get("amount_minor") or 0) != shown["amount_minor"] or (pol and done.get("decision_id") != pol.get("decision_id")):
            out.append({"check": "evidence_binding", "detail": "status EXECUTED is not backed by matching signed PAYMENT_EXECUTED evidence"})
    return out


def verify_package(pkg: dict, trusted_keys: dict | None = None) -> dict:
    """Verify event hashes, signatures, spine linkage, checkpoints and decision replay.

    `trusted_keys` MUST be supplied by the verifier (obtained out of band). Without it the package's own embedded keys are
    used, which only proves internal consistency: an attacker can forge a package with their own keys. The report says which mode ran.
    """
    problems = []
    embedded = _ed_keys(pkg.get("public_keys", {}))
    if trusted_keys is not None:
        pub = _ed_keys(trusted_keys)
        if embedded != pub:
            problems.append({"check": "untrusted_package_keys", "detail": "keys embedded in the package differ from the verifier's trusted keys"})
    else:
        pub = embedded
    spine = {x["sequence"]: x for x in pkg["chain_spine"]}
    prev = ledger.GENESIS
    for seq in sorted(spine):
        if spine[seq]["previous_hash"] != prev:
            problems.append({"check": "spine_linkage", "detail": f"sequence {seq} does not link to its predecessor"})
        prev = spine[seq]["event_hash"]
    ev_ok = 0
    for e in pkg["ledger_events"]:
        body = {k: v for k, v in e.items() if k not in ("event_hash", "signature", "payload")}
        if domain_hash(ledger.EVENT_DOMAIN, body) != e["event_hash"]:
            problems.append({"check": "event_hash", "event_id": e["event_id"], "detail": "hash mismatch"})
        elif spine.get(e["sequence"], {}).get("event_hash") != e["event_hash"]:
            problems.append({"check": "event_in_spine", "event_id": e["event_id"], "detail": "event is not part of the chain spine"})
        elif not (pub.get(body["signing_key_id"]) and keys.verify_ed25519(pub[body["signing_key_id"]], ledger.SIG_DOMAIN + bytes.fromhex(e["event_hash"]), e["signature"])):
            problems.append({"check": "event_signature", "event_id": e["event_id"], "detail": "signature invalid"})
        else:
            ev_ok += 1
        if e.get("payload") is not None and canon.digest(e["payload"]) != body["payload_digest"]:
            problems.append({"check": "payload_digest", "event_id": e["event_id"], "detail": "payload does not match committed digest"})
    for cp in pkg["checkpoints"]:
        cb = {k: cp[k] for k in ("checkpoint_id", "sequence", "head_hash", "event_count", "created_at", "ontology_version")}
        msg = ledger.CHECKPOINT_DOMAIN + canon.canonical(cb)
        for sk, kk in (("signature", "key_id"), ("witness_signature", "witness_key_id")):
            if not (pub.get(cp.get(kk)) and keys.verify_ed25519(pub[cp[kk]], msg, cp.get(sk, ""))):
                problems.append({"check": "checkpoint_signature", "detail": f"{cb['checkpoint_id']} {sk} invalid"})
        if cb["sequence"] in spine and spine[cb["sequence"]]["event_hash"] != cb["head_hash"]:
            problems.append({"check": "checkpoint_head", "detail": f"{cb['checkpoint_id']} head differs from spine"})
    if pkg.get("policy") and pkg["policy"].get("replay") and not pkg["policy"]["replay"]["matches"]:
        problems.append({"check": "decision_replay", "detail": "replaying stored inputs produced a different decision"})
    problems += _binding_problems(pkg)
    if pkg.get("consent") and pkg["consent"].get("signature_valid") is False:
        problems.append({"check": "consent_signature", "detail": "consent receipt signature invalid"})
    return {"ok": not problems, "key_trust": "PINNED_BY_VERIFIER" if trusted_keys is not None else "UNPINNED_EMBEDDED_KEYS (internal consistency only)", "events_verified": ev_ok, "events_in_package": len(pkg["ledger_events"]), "spine_length": len(spine), "problems": problems, "verified_at": clock.iso(),
            "assumptions": ["Verification proves integrity and signing-key control under the listed public keys; it cannot detect wholesale replacement of the database and keys beyond external checkpoints."]}


def open_dispute(s, tx_id: str, *, opened_by: str, reason: str) -> dict:
    tx = s.get(db.Transaction, tx_id)
    if not tx:
        raise DisputeError("transaction not found")
    if tx.dispute:
        raise DisputeError("dispute already open")
    tx.dispute = {"opened_by": opened_by, "reason": reason, "opened_at": clock.iso(), "status": "OPEN"}
    ledger.append(s, "DISPUTE_OPENED", actor_id=opened_by, actor_type="customer", principal_id=tx.principal_id, agent_id=tx.agent_id, mandate_id=tx.mandate_id, mandate_version=tx.mandate_version,
                  transaction_id=tx.id, correlation_id=tx.correlation_id, payload={"reason": reason})
    return tx.dispute


_ = timedelta
