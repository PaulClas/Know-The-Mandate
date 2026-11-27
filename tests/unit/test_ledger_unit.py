import copy

from kym import canon, ledger


def make_chain(n=6):
    """Build a real signed chain in memory using the ledger's own primitives (no DB)."""
    from kym import clock, keys

    events, prev = [], ledger.GENESIS
    k = keys.ledger_key()
    for i in range(1, n + 1):
        body = {"event_id": f"evt_{i}", "sequence": i, "event_type": "ACTION_REQUESTED", "timestamp": clock.iso(), "actor_id": "a", "actor_type": "agent", "principal_id": "p", "agent_id": "ag",
                "mandate_id": "m", "mandate_version": 1, "transaction_id": None, "correlation_id": "c", "policy_version": "pv", "ontology_version": "1", "payload_digest": canon.digest({"i": i}),
                "previous_hash": prev, "signer_id": "s", "signing_key_id": k.kid}
        h = canon.domain_hash(ledger.EVENT_DOMAIN, body)
        events.append({**body, "event_hash": h, "signature": k.sign(ledger.SIG_DOMAIN + bytes.fromhex(h))})
        prev = h
    return events


def test_valid_chain_verifies():
    r = ledger.verify(make_chain())
    assert r["ok"] and r["events_checked"] == 6


def test_content_tamper_detected():
    ev = make_chain()
    ev[2]["actor_id"] = "mallory"
    r = ledger.verify(ev)
    assert not r["ok"] and {"hash", "signature"} & {p["check"] for p in r["problems"]}


def test_rehash_without_key_fails_signature_and_chain():
    ev = make_chain()
    ev[2]["actor_id"] = "mallory"
    body = {k: v for k, v in ev[2].items() if k not in ("event_hash", "signature")}
    ev[2]["event_hash"] = canon.domain_hash(ledger.EVENT_DOMAIN, body)
    r = ledger.verify(ev)
    assert {"signature", "chain"} <= {p["check"] for p in r["problems"]}


def test_deletion_and_reordering_detected():
    ev = make_chain()
    assert not ledger.verify(ev[:2] + ev[3:])["ok"]
    swapped = copy.deepcopy(ev)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    assert not ledger.verify(swapped)["ok"]


def test_payload_digest_mismatch_detected():
    ev = make_chain()
    r = ledger.verify(ev, {"evt_1": {"payload": {"i": 999}, "digest": "x", "redacted": False}})
    assert any(p["check"] == "payload" for p in r["problems"])


def test_redacted_payload_does_not_break_chain():
    ev = make_chain()
    assert ledger.verify(ev, {"evt_1": {"payload": None, "digest": "x", "redacted": True}})["ok"]


def test_truncation_detected_by_signed_checkpoint():
    from kym import keys

    ev = make_chain()
    body = {"checkpoint_id": "cp_0001", "sequence": 6, "head_hash": ev[-1]["event_hash"], "event_count": 6, "created_at": "t", "ontology_version": "1"}
    msg = ledger.CHECKPOINT_DOMAIN + canon.canonical(body)
    cp = {**body, "signature": keys.ledger_key().sign(msg), "key_id": keys.ledger_key().kid, "witness_signature": keys.witness_key().sign(msg), "witness_key_id": keys.witness_key().kid}
    assert ledger.verify(ev, cps=[cp])["ok"]
    assert not ledger.verify(ev[:4], cps=[cp])["ok"]


def test_canonical_json_is_rfc8785_and_domain_separated():
    assert canon.canonical({"b": 1, "a": [1.5, "x"]}) == b'{"a":[1.5,"x"],"b":1}'
    assert canon.domain_hash("A", {"x": 1}) != canon.domain_hash("B", {"x": 1})
