"""KYM Evidence Ledger: append-only, hash-chained, Ed25519-signed record of the exercise of authority.

Separate from the double-entry accounting ledger in bank.py (which records movement of money).
Event payloads live in a protected store; the chain commits only to the payload digest.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select

from . import clock, config, db, keys
from .canon import canonical, digest, domain_hash

EVENT_DOMAIN = "KYM-EVIDENCE-EVENT-V1"
SIG_DOMAIN = b"KYM-EVIDENCE-SIG-V1\x00"
CHECKPOINT_DOMAIN = b"KYM-CHECKPOINT-V1\x00"
GENESIS = "0" * 64

EVENT_TYPES = [
    "CUSTOMER_VERIFIED", "AGENT_REGISTERED", "AGENT_VERIFIED", "AGENT_SUSPENDED", "MANDATE_PROPOSED",
    "MANDATE_VALIDATED", "MANDATE_APPROVED", "MANDATE_ACTIVATED", "MANDATE_AMENDED", "MANDATE_DELEGATED",
    "MANDATE_REVOKED", "MANDATE_SUSPENDED", "MANDATE_APPROVAL_REQUESTED", "MANDATE_REJECTED", "MANDATE_EXPIRED", "MANDATE_SUPERSEDED",
    "TOKEN_ISSUED", "TOKEN_REJECTED", "TOKEN_REVOKED", "ACTION_REQUESTED", "POLICY_EVALUATED", "ACTION_DENIED",
    "RISK_EVALUATED", "HUMAN_APPROVAL_REQUESTED", "HUMAN_APPROVAL_GRANTED", "HUMAN_APPROVAL_REJECTED",
    "PAYMENT_EXECUTED", "PAYMENT_FAILED", "DISPUTE_OPENED",
]


def append(
    s,
    event_type: str,
    *,
    actor_id: str,
    actor_type: str,
    principal_id: str | None = None,
    agent_id: str | None = None,
    mandate_id: str | None = None,
    mandate_version: int | None = None,
    transaction_id: str | None = None,
    correlation_id: str | None = None,
    policy_version: str | None = None,
    payload: dict | None = None,
) -> dict:
    assert event_type in EVENT_TYPES, event_type
    last = s.execute(select(db.EvidenceEvent).order_by(db.EvidenceEvent.seq.desc()).limit(1)).scalar_one_or_none()
    seq = (last.seq + 1) if last else 1
    prev = last.event_hash if last else GENESIS
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    payload = payload or {}
    key = keys.ledger_key()
    body: dict[str, Any] = {
        "event_id": event_id,
        "sequence": seq,
        "event_type": event_type,
        "timestamp": max(clock.iso(), last.body["timestamp"]) if last else clock.iso(),  # monotonic: a regressing wall clock cannot reorder history
        "actor_id": actor_id,
        "actor_type": actor_type,
        "principal_id": principal_id,
        "agent_id": agent_id,
        "mandate_id": mandate_id,
        "mandate_version": mandate_version,
        "transaction_id": transaction_id,
        "correlation_id": correlation_id or f"corr_{uuid.uuid4().hex[:12]}",
        "policy_version": policy_version or config.POLICY_VERSION,
        "ontology_version": config.ONTOLOGY_VERSION,
        "payload_digest": digest(payload),
        "previous_hash": prev,
        "signer_id": "meridian-bank-evidence-service",
        "signing_key_id": key.kid,
    }
    h = domain_hash(EVENT_DOMAIN, body)
    sig = key.sign(SIG_DOMAIN + bytes.fromhex(h))
    s.add(
        db.EvidenceEvent(
            seq=seq, event_id=event_id, event_type=event_type, body=body, event_hash=h, signature=sig,
            correlation_id=body["correlation_id"], mandate_id=mandate_id, transaction_id=transaction_id,
        )
    )
    s.add(db.EvidencePayload(event_id=event_id, payload=payload, digest=body["payload_digest"]))
    s.flush()
    return {**body, "event_hash": h, "signature": sig}


def _export(row: db.EvidenceEvent) -> dict:
    return {**row.body, "event_hash": row.event_hash, "signature": row.signature}


def list_events(s, *, event_type=None, correlation_id=None, mandate_id=None, transaction_id=None, q=None, limit=200, offset=0, ascending=False):
    stmt = select(db.EvidenceEvent)
    if event_type:
        stmt = stmt.where(db.EvidenceEvent.event_type == event_type)
    if correlation_id:
        stmt = stmt.where(db.EvidenceEvent.correlation_id == correlation_id)
    if mandate_id:
        stmt = stmt.where(db.EvidenceEvent.mandate_id == mandate_id)
    if transaction_id:
        stmt = stmt.where(db.EvidenceEvent.transaction_id == transaction_id)
    stmt = stmt.order_by(db.EvidenceEvent.seq.asc() if ascending else db.EvidenceEvent.seq.desc())
    rows = s.execute(stmt).scalars().all()
    out = [_export(r) for r in rows]
    if q:
        ql = q.lower()
        out = [e for e in out if ql in json.dumps(e).lower()]
    return out[offset : offset + limit], len(out)


def get_event(s, event_id: str) -> dict | None:
    row = s.execute(select(db.EvidenceEvent).where(db.EvidenceEvent.event_id == event_id)).scalar_one_or_none()
    if not row:
        return None
    pl = s.get(db.EvidencePayload, event_id)
    return {**_export(row), "payload": None if (pl is None or pl.redacted) else pl.payload, "payload_redacted": bool(pl and pl.redacted)}


def all_events(s) -> list[dict]:
    return [_export(r) for r in s.execute(select(db.EvidenceEvent).order_by(db.EvidenceEvent.seq)).scalars()]


def payload_map(s) -> dict[str, dict]:
    return {p.event_id: {"payload": p.payload, "digest": p.digest, "redacted": p.redacted} for p in s.execute(select(db.EvidencePayload)).scalars()}


def checkpoints(s) -> list[dict]:
    return [
        {**c.body, "signature": c.signature, "key_id": c.key_id, "witness_signature": c.witness_signature, "witness_key_id": c.witness_key_id}
        for c in s.execute(select(db.Checkpoint).order_by(db.Checkpoint.id)).scalars()
    ]


def create_checkpoint(s) -> dict:
    last = s.execute(select(db.EvidenceEvent).order_by(db.EvidenceEvent.seq.desc()).limit(1)).scalar_one_or_none()
    if last is None:
        raise ValueError("ledger is empty")
    count = s.execute(select(func.count()).select_from(db.EvidenceEvent)).scalar_one()
    n = s.execute(select(func.count()).select_from(db.Checkpoint)).scalar_one() + 1
    body = {
        "checkpoint_id": f"cp_{n:04d}",
        "sequence": last.seq,
        "head_hash": last.event_hash,
        "event_count": count,
        "created_at": clock.iso(),
        "ontology_version": config.ONTOLOGY_VERSION,
    }
    msg = CHECKPOINT_DOMAIN + canonical(body)
    lk, wk = keys.ledger_key(), keys.witness_key()
    row = db.Checkpoint(body=body, signature=lk.sign(msg), key_id=lk.kid, witness_signature=wk.sign(msg), witness_key_id=wk.kid)
    s.add(row)
    s.flush()
    exported = {**body, "signature": row.signature, "key_id": lk.kid, "witness_signature": row.witness_signature, "witness_key_id": wk.kid}
    # Locally exported trusted checkpoint, held outside the database (demo stand-in for an external witness).
    config.ensure_dirs()
    (config.DATA_DIR / "checkpoints" / f"{body['checkpoint_id']}.json").write_text(json.dumps(exported, indent=2))
    return exported


def public_keys() -> dict[str, str]:
    reg = keys.public_key_registry()
    return {reg["ledger"]["kid"]: reg["ledger"]["x"], reg["witness"]["kid"]: reg["witness"]["x"]}


def verify(events: list[dict], payloads: dict[str, dict] | None = None, cps: list[dict] | None = None,
           pubkeys: dict[str, str] | None = None, exported_cps: list[dict] | None = None) -> dict:
    """Pure verifier over exported data. Works on copies, packages and the authoritative ledger alike."""
    pubkeys = pubkeys or public_keys()
    payloads = payloads or {}
    cps = cps or []
    problems: list[dict] = []
    prev = GENESIS
    prev_ts = ""
    expected_seq = events[0]["sequence"] if events else 1
    for e in events:
        eid = e.get("event_id")
        body = {k: v for k, v in e.items() if k not in ("event_hash", "signature", "payload", "payload_redacted")}
        if e["sequence"] != expected_seq:
            problems.append({"event_id": eid, "check": "sequence", "detail": f"expected {expected_seq}, found {e['sequence']} (missing or reordered events)"})
            expected_seq = e["sequence"]
        expected_seq += 1
        if body.get("previous_hash") != prev:
            problems.append({"event_id": eid, "check": "chain", "detail": "previous_hash does not match preceding event hash"})
        recomputed = domain_hash(EVENT_DOMAIN, body)
        if recomputed != e.get("event_hash"):
            problems.append({"event_id": eid, "check": "hash", "detail": "event hash does not match event content"})
        pub = pubkeys.get(body.get("signing_key_id"))
        if pub is None:
            problems.append({"event_id": eid, "check": "signature", "detail": f"unknown signing key {body.get('signing_key_id')}"})
        elif not keys.verify_ed25519(pub, SIG_DOMAIN + bytes.fromhex(e["event_hash"]), e["signature"]):
            problems.append({"event_id": eid, "check": "signature", "detail": "invalid signature"})
        if prev_ts and body["timestamp"] < prev_ts:
            problems.append({"event_id": eid, "check": "ordering", "detail": "timestamp earlier than predecessor"})
        prev_ts = body["timestamp"]
        pl = payloads.get(eid)
        if pl and not pl.get("redacted") and pl.get("payload") is not None and digest(pl["payload"]) != body["payload_digest"]:
            problems.append({"event_id": eid, "check": "payload", "detail": "payload digest mismatch"})
        prev = e["event_hash"]
    by_seq = {e["sequence"]: e for e in events}
    last_seq = events[-1]["sequence"] if events else 0
    for cp in cps + (exported_cps or []):
        cb = {k: cp[k] for k in ("checkpoint_id", "sequence", "head_hash", "event_count", "created_at", "ontology_version")}
        msg = CHECKPOINT_DOMAIN + canonical(cb)
        for sig_key, kid_key in (("signature", "key_id"), ("witness_signature", "witness_key_id")):
            pub = pubkeys.get(cp.get(kid_key))
            if not pub or not keys.verify_ed25519(pub, msg, cp.get(sig_key, "")):
                problems.append({"event_id": None, "check": "checkpoint", "detail": f"{cb['checkpoint_id']}: invalid {sig_key}"})
        if cb["sequence"] > last_seq and events and events[0]["sequence"] == 1:
            problems.append({"event_id": None, "check": "checkpoint", "detail": f"{cb['checkpoint_id']}: events up to {cb['sequence']} were signed but chain ends at {last_seq} (truncation / missing events)"})
        elif cb["sequence"] in by_seq and by_seq[cb["sequence"]]["event_hash"] != cb["head_hash"]:
            problems.append({"event_id": None, "check": "checkpoint", "detail": f"{cb['checkpoint_id']}: head hash differs from chain at sequence {cb['sequence']} (history rewritten)"})
    return {
        "ok": not problems,
        "events_checked": len(events),
        "checkpoints_checked": len(cps) + len(exported_cps or []),
        "head_hash": events[-1]["event_hash"] if events else GENESIS,
        "problems": problems,
        "checks": ["hash_chain", "signatures", "sequence_continuity", "timestamp_ordering", "payload_digests", "checkpoints"],
        "verified_at": clock.iso(),
        "assumptions": [
            "Valid signatures prove integrity and control of the signing key; they do not prove legally effective consent.",
            "A local chain cannot detect wholesale replacement of the database AND signing keys; compare against externally held checkpoints.",
        ],
    }


def verify_authoritative(s) -> dict:
    exported = []
    cp_dir = config.DATA_DIR / "checkpoints"
    if cp_dir.exists():
        exported = [json.loads(p.read_text()) for p in sorted(cp_dir.glob("cp_*.json"))]
    return verify(all_events(s), payload_map(s), checkpoints(s), exported_cps=exported)


def erase_payload(s, event_id: str) -> None:
    """Crypto-shredding style erasure: chain remains verifiable because it commits only to the digest."""
    pl = s.get(db.EvidencePayload, event_id)
    if pl:
        pl.payload = None
        pl.redacted = True
