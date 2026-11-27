"""Agent transparency: detect agents that hide, invent or rewrite what they did.

PRINCIPLE: never trust an agent's account of itself; enforce on what the bank can observe.
An agent's reasoning ("chain of thought") and its own logs can be incomplete, edited or fabricated, and the bank cannot read minds.
What the bank CAN do, and what this module does:

1. Signed, hash-chained ACTIVITY REPORTS. An enrolled agent must periodically submit a report signed with its registered key and chained to
   the previous report (no silent gaps, no rewriting). The bank reconciles every report against the transactions it observed itself:
   an action the bank saw but the report omits (UNREPORTED_ACTION), an action the report claims that the bank never saw (PHANTOM_ACTION),
   or one reported with a different amount or counterparty (DECLARATION_MISMATCH).
2. COMMIT-REVEAL of reasoning logs. Before acting, an agent can commit to a digest of its reasoning/decision log. The bank (or an investigator)
   can later demand the reveal. A reveal that does not match the commitment proves the log was altered after the fact (LOG_SWAPPED); a refusal
   or silence past the deadline is itself a violation (REVEAL_REFUSED).
3. A DEAD-MAN'S SWITCH. No report by the deadline is a violation (REPORT_OVERDUE).

CONSEQUENCE: a violation restricts the agent (existing RESTRICTED status: read-only) and writes a signed evidence event. Only a bank operator
can clear it, after review, which is also recorded. The PDP, the mandate and the payment engine are unchanged.

WHAT THIS CANNOT DO (stated plainly): it cannot see actions an agent takes outside this bank, cannot read or verify an agent's reasoning, and
cannot detect a dishonest log that was committed honestly-looking BEFORE the fact. It makes hiding and after-the-fact rewriting detectable
for actions that touch the bank; it does not make an agent honest.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

import jwt
from sqlalchemy import select

from . import agents as agents_mod
from . import canon, clock, db, ledger

REPORT_TYP = "kym-activity-report+jwt"
COMMIT_TYP = "kym-log-commitment+jwt"
REVEAL_TYP = "kym-log-reveal+jwt"
GENESIS = ledger.GENESIS
MONITOR = "meridian-transparency-monitor"
OBSERVED_KINDS = ("PAYMENT", "TRANSFER")  # money-moving attempts, including denied ones. Reads are not reconciled (noise, low risk).
MAX_ENTRIES = 5000
MAX_BLOB_BYTES = 256_000
IAT_WINDOW_SECONDS = 600


class TransparencyError(ValueError):
    pass


# ----------------------------------------------------------------------------------- shared (agent and bank) helpers


def entry_hash(entry: dict) -> str:
    return canon.digest({k: v for k, v in entry.items() if k != "entry_hash"})


def commitment_digest(blob: Any, nonce: str) -> str:
    """Digest an agent commits to: SHA-256 over nonce, a separator and the canonical JSON of the log blob. The nonce stops guessing short logs."""
    return "sha256:" + hashlib.sha256(nonce.encode() + b"\x00" + canon.canonical(blob)).hexdigest()


def _verify_jws(agent: db.Agent, token: str, typ: str, *, now) -> dict:
    if not isinstance(token, str) or len(token) > 2_000_000:
        raise TransparencyError("jws missing or too large")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise TransparencyError("malformed JWS") from e
    if header.get("typ") != typ or header.get("alg") != "ES256":
        raise TransparencyError(f"JWS header must have typ={typ} and alg=ES256")
    if not agent.public_key_jwk:
        raise TransparencyError("agent has no registered key")
    try:
        claims = jwt.decode(token, jwt.PyJWK(agent.public_key_jwk).key, algorithms=["ES256"],
                            options={"verify_aud": False, "verify_exp": False, "verify_iat": False, "require": ["iat", "agent_id"]})
    except jwt.PyJWTError as e:
        raise TransparencyError(f"signature invalid: {e}") from e
    if claims["agent_id"] != agent.id:
        raise TransparencyError("agent_id does not match the signing key's agent")
    if abs(now.timestamp() - float(claims["iat"])) > IAT_WINDOW_SECONDS:
        raise TransparencyError("iat outside the acceptable window")
    return claims


def _agent(s, agent_id: str) -> db.Agent:
    a = s.get(db.Agent, agent_id)
    if not a:
        raise TransparencyError("unknown agent")
    return a


def _state(a: db.Agent) -> dict:
    return a.transparency or {}


def _enrolled(a: db.Agent) -> dict:
    st = _state(a)
    if not st.get("enrolled"):
        raise TransparencyError("agent is not enrolled in transparency monitoring")
    return st


# ----------------------------------------------------------------------------------- operator actions


def enroll(s, agent_id: str, *, interval_hours: int = 24, grace_minutes: int = 60, actor_id: str) -> dict:
    a = _agent(s, agent_id)
    if not (1 <= interval_hours <= 24 * 31 and 0 <= grace_minutes <= 24 * 60):
        raise TransparencyError("interval_hours must be 1..744 and grace_minutes 0..1440")
    now = clock.iso()
    a.transparency = {"enrolled": True, "interval_hours": interval_hours, "grace_minutes": grace_minutes, "enrolled_at": now, "last_report_at": None,
                      "last_window_end": now, "last_head": GENESIS, "last_seq": 0, "status": "CLEAR", "violations": [], "restricted_by_monitor": False}
    s.flush()
    ledger.append(s, "AGENT_TRANSPARENCY_ENROLLED", actor_id=actor_id, actor_type="bank_operator", agent_id=agent_id,
                  payload={"interval_hours": interval_hours, "grace_minutes": grace_minutes, "anchor": now})
    return status(s, agent_id)


def demand_reveal(s, commitment_id: str, *, within_hours: int = 24, reason: str, actor_id: str) -> dict:
    c = s.get(db.AgentCommitment, commitment_id)
    if not c:
        raise TransparencyError("unknown commitment")
    if c.status != "COMMITTED":
        raise TransparencyError(f"commitment is already {c.status}")
    if not 1 <= within_hours <= 24 * 30:
        raise TransparencyError("within_hours must be 1..720")
    c.due_at = clock.iso(clock.now() + timedelta(hours=within_hours))
    s.flush()
    ledger.append(s, "AGENT_REVEAL_DEMANDED", actor_id=actor_id, actor_type="bank_operator", agent_id=c.agent_id,
                  payload={"commitment_id": c.id, "due_at": c.due_at, "reason": reason[:300]})
    return _commitment_dict(c)


def clear(s, agent_id: str, *, reason: str, actor_id: str) -> dict:
    """Human review closes a violation. The unreported gap is acknowledged (not erased: the event records the old anchor and head), the log chain restarts, and the agent is re-verified."""
    a = _agent(s, agent_id)
    st = _enrolled(a)
    if st.get("status") != "VIOLATION":
        raise TransparencyError("no open transparency violation")
    if not reason.strip():
        raise TransparencyError("a review reason is required")
    now = clock.iso()
    for c in s.execute(select(db.AgentCommitment).where(db.AgentCommitment.agent_id == agent_id, db.AgentCommitment.status == "COMMITTED", db.AgentCommitment.due_at.is_not(None))).scalars():
        c.status = "WAIVED"
    ledger.append(s, "AGENT_TRANSPARENCY_CLEARED", actor_id=actor_id, actor_type="bank_operator", agent_id=agent_id,
                  payload={"reason": reason[:300], "acknowledged_violations": [v["code"] for v in st.get("violations", [])], "previous_anchor": st["last_window_end"], "previous_head": st["last_head"]})
    a.transparency = {**st, "status": "CLEAR", "violations": [], "last_window_end": now, "last_report_at": now, "last_head": GENESIS, "last_seq": 0}
    restore = st.get("restricted_by_monitor") and a.status == "RESTRICTED"
    a.transparency = {**a.transparency, "restricted_by_monitor": False}
    s.flush()
    if restore:
        agents_mod.verify(s, agent_id, actor_id=actor_id)
    return status(s, agent_id)


# ----------------------------------------------------------------------------------- enforcement


def _violate(s, a: db.Agent, violations: list[dict], *, report_id: str | None = None) -> None:
    st = dict(_state(a))
    known = {v["code"] for v in st.get("violations", [])}
    new = [v for v in violations if v["code"] not in known or v.get("ref")]
    st["status"] = "VIOLATION"
    st["violations"] = [*st.get("violations", []), *new][-50:]
    if a.status == "VERIFIED":
        try:
            agents_mod.set_status(s, a.id, "RESTRICTED", actor_id=MONITOR, reason="transparency violation: " + ", ".join(sorted({v["code"] for v in violations})))
            st["restricted_by_monitor"] = True
        except agents_mod.AgentError:
            pass
    a.transparency = st
    s.flush()
    ledger.append(s, "AGENT_TRANSPARENCY_VIOLATION", actor_id=MONITOR, actor_type="bank_system", agent_id=a.id, payload={"report_id": report_id, "violations": violations[:50], "action": "agent restricted to read-only"})
    agents_mod.add_incident(s, a.id, "Transparency violation: " + ", ".join(sorted({v["code"] for v in violations})), "HIGH")


def enforce(s, a: db.Agent | None, now=None) -> None:
    """Dead-man's switch and reveal deadlines. Called from the gateway before every decision, so silence cannot outrun enforcement."""
    if a is None or not _state(a).get("enrolled") or _state(a).get("status") == "VIOLATION":
        return
    st = _state(a)
    now = now or clock.now()
    found: list[dict] = []
    deadline = clock.parse(st.get("last_report_at") or st["enrolled_at"]) + timedelta(hours=st["interval_hours"], minutes=st["grace_minutes"])
    if now > deadline:
        found.append({"code": "REPORT_OVERDUE", "detail": f"no valid activity report since {st.get('last_report_at') or st['enrolled_at']}; was due by {clock.iso(deadline)}"})
    for c in s.execute(select(db.AgentCommitment).where(db.AgentCommitment.agent_id == a.id, db.AgentCommitment.status == "COMMITTED", db.AgentCommitment.due_at.is_not(None))).scalars():
        if clock.parse(c.due_at) < now:
            found.append({"code": "REVEAL_REFUSED", "detail": f"commitment {c.id} was demanded by {c.due_at} and has not been revealed", "ref": c.id})
    if found:
        _violate(s, a, found)


# ----------------------------------------------------------------------------------- agent submissions


def submit_report(s, agent_id: str, token: str) -> dict:
    now = clock.now()
    a = _agent(s, agent_id)
    st = _enrolled(a)
    rid = "rpt_" + hashlib.sha256(token.encode()).hexdigest()[:20]
    prior = s.get(db.ActivityReport, rid)
    if prior:  # idempotent: resubmitting the same signed report returns the original result and changes nothing
        return {"report_id": prior.id, "ok": not prior.discrepancies, "discrepancies": prior.discrepancies, "replayed": True, "status": _state(a).get("status")}
    claims = _verify_jws(a, token, REPORT_TYP, now=now)
    w = claims.get("window") or {}
    entries = claims.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES or not all(isinstance(e, dict) for e in entries):
        raise TransparencyError(f"entries must be a list of at most {MAX_ENTRIES} objects")
    try:
        w0, w1 = clock.parse(w["start"]), clock.parse(w["end"])
    except (KeyError, ValueError, TypeError) as e:
        raise TransparencyError("window.start and window.end must be ISO timestamps") from e
    if not (w0 < w1 <= now + timedelta(seconds=60)):
        raise TransparencyError("window must be non-empty and not end in the future")

    found: list[dict] = []
    if w0 != clock.parse(st["last_window_end"]):
        found.append({"code": "WINDOW_GAP", "detail": f"report starts {w['start']} but the previous window ended {st['last_window_end']}: a gap leaves time unreported and an overlap re-reports it; windows must be contiguous"})
    prev, seq, chain_ok = st["last_head"], st["last_seq"], True
    for e in entries:
        if e.get("seq") != seq + 1 or e.get("prev_hash") != prev or e.get("entry_hash") != entry_hash(e):
            found.append({"code": "LOG_CHAIN_BREAK", "detail": f"entry seq={e.get('seq')} does not extend the agent's committed log (expected seq {seq + 1} after head {prev[:19]}...)"})
            chain_ok = False
            break
        prev, seq = e["entry_hash"], e["seq"]
    if chain_ok and claims.get("head") != prev:
        found.append({"code": "LOG_CHAIN_BREAK", "detail": "declared head does not equal the last entry's hash"})
        chain_ok = False

    observed = {t.id: t for t in s.execute(select(db.Transaction).where(db.Transaction.agent_id == a.id, db.Transaction.kind.in_(OBSERVED_KINDS))).scalars()}
    in_window = {i: t for i, t in observed.items() if w0 <= clock.parse(t.created_at) < w1}
    reported = {e["ref"]: e for e in entries if e.get("kind") == "bank_request" and isinstance(e.get("ref"), str)}
    for tid, t in in_window.items():
        if tid not in reported:
            found.append({"code": "UNREPORTED_ACTION", "ref": tid, "detail": f"the bank observed {t.action} of {t.amount_minor} {t.currency} (status {t.status}) that the report does not mention"})
    for ref, e in reported.items():
        t = observed.get(ref)
        if t is None:
            found.append({"code": "PHANTOM_ACTION", "ref": ref, "detail": "the report claims a bank request the bank has no record of for this agent"})
            continue
        if e.get("amount_minor") is not None and e["amount_minor"] != t.amount_minor:
            found.append({"code": "DECLARATION_MISMATCH", "ref": ref, "detail": f"reported amount {e['amount_minor']} but the bank recorded {t.amount_minor}"})
        cp = (t.operation or {}).get("counterparty_id")
        if e.get("counterparty") is not None and e["counterparty"] != cp:
            found.append({"code": "DECLARATION_MISMATCH", "ref": ref, "detail": f"reported counterparty {e['counterparty']} but the bank recorded {cp}"})

    s.add(db.ActivityReport(id=rid, agent_id=a.id, window_start=w["start"], window_end=w["end"], head=str(claims.get("head")), entry_count=len(entries), discrepancies=found, jws=token, received_at=clock.iso(now)))
    s.flush()
    if chain_ok and not any(v["code"] == "WINDOW_GAP" for v in found):
        a.transparency = {**_state(a), "last_head": prev, "last_seq": seq, "last_window_end": w["end"], "last_report_at": clock.iso(now)}
    if found:
        _violate(s, a, found, report_id=rid)
    else:
        ledger.append(s, "AGENT_ACTIVITY_REPORTED", actor_id=a.id, actor_type="agent", agent_id=a.id,
                      payload={"report_id": rid, "window": w, "entries": len(entries), "head": prev, "bank_observed_in_window": len(in_window), "reconciled": True})
    return {"report_id": rid, "ok": not found, "discrepancies": found, "observed_in_window": len(in_window), "reported_bank_requests": len(reported), "status": _state(a).get("status")}


def commit(s, agent_id: str, token: str) -> dict:
    now = clock.now()
    a = _agent(s, agent_id)
    claims = _verify_jws(a, token, COMMIT_TYP, now=now)
    digest = claims.get("commitment")
    if not (isinstance(digest, str) and digest.startswith("sha256:") and len(digest) == 71):
        raise TransparencyError("commitment must be sha256:<64 hex>")
    ref = claims.get("ref")
    if ref is not None and not (isinstance(ref, str) and len(ref) <= 128):
        raise TransparencyError("ref must be a string of at most 128 characters")
    cid = "cmt_" + hashlib.sha256((agent_id + digest).encode()).hexdigest()[:20]
    existing = s.get(db.AgentCommitment, cid)
    if existing:
        return _commitment_dict(existing)
    c = db.AgentCommitment(id=cid, agent_id=agent_id, commitment=digest, ref=ref, jws=token, created_at=clock.iso(now), status="COMMITTED")
    s.add(c)
    s.flush()
    ledger.append(s, "AGENT_LOG_COMMITTED", actor_id=agent_id, actor_type="agent", agent_id=agent_id, payload={"commitment_id": cid, "commitment": digest, "ref": ref})
    return _commitment_dict(c)


def reveal(s, agent_id: str, commitment_id: str, token: str) -> dict:
    now = clock.now()
    a = _agent(s, agent_id)
    c = s.get(db.AgentCommitment, commitment_id)
    if not c or c.agent_id != agent_id:
        raise TransparencyError("unknown commitment for this agent")
    if c.status in ("REVEALED", "MISMATCH"):
        return _commitment_dict(c)
    claims = _verify_jws(a, token, REVEAL_TYP, now=now)
    if claims.get("commitment_id") != commitment_id or not isinstance(claims.get("nonce"), str) or "blob" not in claims:
        raise TransparencyError("reveal must carry commitment_id, nonce and blob")
    if len(canon.canonical(claims["blob"])) > MAX_BLOB_BYTES:
        raise TransparencyError("blob too large")
    matches = commitment_digest(claims["blob"], claims["nonce"]) == c.commitment
    c.status, c.revealed, c.revealed_at = ("REVEALED" if matches else "MISMATCH"), {"blob": claims["blob"], "note": "agent-supplied; untrusted"}, clock.iso(now)
    s.flush()
    ledger.append(s, "AGENT_LOG_REVEALED", actor_id=agent_id, actor_type="agent", agent_id=agent_id,
                  payload={"commitment_id": c.id, "matches_commitment": matches, "blob_digest": canon.digest(claims["blob"])})
    if not matches:
        _violate(s, a, [{"code": "LOG_SWAPPED", "ref": c.id, "detail": "the revealed log does not match the digest the agent committed to before acting: it was altered or replaced"}])
    return _commitment_dict(c)


# ----------------------------------------------------------------------------------- read models


def _commitment_dict(c: db.AgentCommitment) -> dict:
    return {"id": c.id, "agent_id": c.agent_id, "commitment": c.commitment, "ref": c.ref, "created_at": c.created_at, "due_at": c.due_at, "status": c.status,
            "revealed": c.revealed, "revealed_at": c.revealed_at}


def status(s, agent_id: str) -> dict:
    a = _agent(s, agent_id)
    st = _state(a)
    reports = s.execute(select(db.ActivityReport).where(db.ActivityReport.agent_id == agent_id).order_by(db.ActivityReport.received_at.desc()).limit(20)).scalars().all()
    commits = s.execute(select(db.AgentCommitment).where(db.AgentCommitment.agent_id == agent_id).order_by(db.AgentCommitment.created_at.desc()).limit(50)).scalars().all()
    next_due = None
    if st.get("enrolled"):
        next_due = clock.iso(clock.parse(st.get("last_report_at") or st["enrolled_at"]) + timedelta(hours=st["interval_hours"], minutes=st["grace_minutes"]))
    return {"agent_id": agent_id, "agent_status": a.status, "transparency": {k: v for k, v in st.items()}, "next_report_due_by": next_due,
            "reports": [{"id": r.id, "window": [r.window_start, r.window_end], "entries": r.entry_count, "discrepancies": r.discrepancies, "received_at": r.received_at} for r in reports],
            "commitments": [_commitment_dict(c) for c in commits],
            "limits": ["Only actions that touch this bank are reconciled.", "Agent reasoning is never verified, only committed to and revealed.", "A report is evidence of what the agent claims, not of what it did elsewhere."]}
