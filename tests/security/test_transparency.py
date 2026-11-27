"""Agent transparency: hidden actions, invented actions, rewritten logs and silence are detected and restrict the agent. See transparency.py."""
import uuid

import pytest

from kym import agents as agents_mod
from kym import clock, db, demo, scenarios, transparency
from kym.agent_sdk import ActivityLog
from kym.demo import session_headers

AGENT = "agent_billpay_001"


def H(u):
    return session_headers(u)


def _reset_agent():
    with db.write() as s:
        a = s.get(db.Agent, AGENT)
        a.transparency = {}
        a.status = "VERIFIED"
        for c in s.query(db.AgentCommitment).filter_by(agent_id=AGENT).all():
            s.delete(c)


@pytest.fixture
def env(http):
    _reset_agent()
    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    client, tok = demo.connect(http, AGENT, m, "customer_001")
    r = http.post(f"/api/agents/{AGENT}/transparency/enroll", json={"interval_hours": 24}, headers=H("admin_001"))
    assert r.status_code == 200, r.text
    log = ActivityLog(AGENT, client.key, anchor=r.json()["transparency"]["last_window_end"])
    yield http, client, tok, log
    _reset_agent()


def pay(client, tok, amount, ben="beneficiary_hydro_quebec"):
    body = {"account_id": "account_001", "beneficiary_id": ben, "amount_minor": amount, "currency": "CAD", "purpose": "household_bill_management"}
    return client.call(tok, "POST", "/bank/payments", json_body=body, idempotency_key=uuid.uuid4().hex)


def submit(http, jws):
    return http.post(f"/bank/agents/{AGENT}/activity-reports", json={"jws": jws})


def agent_status(http):
    return http.get(f"/api/agents/{AGENT}/transparency", headers=H("admin_001")).json()


def codes(res):
    return sorted({d["code"] for d in res.json()["discrepancies"]})


def test_an_honest_log_reconciles_and_the_chain_continues_across_reports(env):
    http, client, tok, log = env
    for amt, ben in ((5000, "beneficiary_hydro_quebec"), (5000, "beneficiary_videotron")):  # one allowed, one denied: both are real bank requests
        r = pay(client, tok, amt, ben)
        log.record_response(r, amount_minor=amt, counterparty=ben)
    res = submit(http, log.report())
    assert res.status_code == 200 and res.json()["ok"] and res.json()["observed_in_window"] == 2 == res.json()["reported_bank_requests"]
    r = pay(client, tok, 4000)
    log.record_response(r, amount_minor=4000, counterparty="beneficiary_hydro_quebec")
    assert submit(http, log.report()).json()["ok"]  # second window chains onto the first
    st = agent_status(http)
    assert st["transparency"]["status"] == "CLEAR" and st["agent_status"] == "VERIFIED" and st["transparency"]["last_seq"] == 3


def test_resubmitting_the_same_signed_report_changes_nothing(env):
    http, client, tok, log = env
    log.record_response(pay(client, tok, 5000), amount_minor=5000, counterparty="beneficiary_hydro_quebec")
    jws = log.report()
    first, again = submit(http, jws).json(), submit(http, jws).json()
    assert first["ok"] and again["replayed"] is True and again["report_id"] == first["report_id"]


def test_a_hidden_action_is_detected_restricts_the_agent_and_is_cleared_only_by_a_human(env):
    http, client, tok, log = env
    shown, hidden = pay(client, tok, 5000), pay(client, tok, 7000)  # the agent pays twice but reports only one
    log.record_response(shown, amount_minor=5000, counterparty="beneficiary_hydro_quebec")
    res = submit(http, log.report())
    assert res.json()["ok"] is False and codes(res) == ["UNREPORTED_ACTION"]
    assert res.json()["discrepancies"][0]["ref"] == hidden.json()["transaction_id"]
    assert agent_status(http)["agent_status"] == "RESTRICTED"
    denied = pay(client, tok, 3000)
    assert denied.status_code == 403 and denied.json()["decision"] == "DENY"  # money movement is now refused
    assert http.post(f"/api/agents/{AGENT}/transparency/clear", json={"reason": "x"}, headers=H("customer_001")).status_code == 403  # not by customers
    cleared = http.post(f"/api/agents/{AGENT}/transparency/clear", json={"reason": "reviewed the hidden CAD 70 payment with the operator"}, headers=H("admin_001"))
    assert cleared.status_code == 200 and cleared.json()["agent_status"] == "VERIFIED" and cleared.json()["transparency"]["status"] == "CLEAR"
    assert pay(client, tok, 3000).status_code == 201


def test_an_invented_action_is_detected(env):
    http, client, tok, log = env
    log.record("bank_request", ref="tx_never_happened", amount_minor=100, counterparty="beneficiary_hydro_quebec")
    assert codes(submit(http, log.report())) == ["PHANTOM_ACTION"]


def test_a_misreported_amount_or_counterparty_is_detected(env):
    http, client, tok, log = env
    r = pay(client, tok, 9000)
    log.record_response(r, amount_minor=900, counterparty="beneficiary_videotron")  # the agent understates it and names someone else
    res = submit(http, log.report())
    assert codes(res) == ["DECLARATION_MISMATCH"] and len(res.json()["discrepancies"]) == 2


def test_removing_an_entry_from_the_hash_chain_is_detected(env):
    http, client, tok, log = env
    for amt in (1000, 2000, 3000):
        log.record_response(pay(client, tok, amt), amount_minor=amt, counterparty="beneficiary_hydro_quebec")
    del log.entries[1]  # hide the middle entry but keep the rest
    res = submit(http, log.report())
    assert "LOG_CHAIN_BREAK" in codes(res)


def test_a_report_with_a_non_contiguous_window_is_detected(env):
    http, client, tok, log = env
    log.record_response(pay(client, tok, 1000), amount_minor=1000, counterparty="beneficiary_hydro_quebec")
    log.window_start = clock.iso(clock.parse(log.window_start) - __import__("datetime").timedelta(seconds=5))  # does not start where the previous window ended
    assert "WINDOW_GAP" in codes(submit(http, log.report()))


def test_reports_must_be_signed_by_the_agents_registered_key(env):
    from cryptography.hazmat.primitives.asymmetric import ec

    http, client, tok, log = env
    forged = ActivityLog(AGENT, ec.generate_private_key(ec.SECP256R1()), anchor=log.window_start)
    res = submit(http, forged.report())
    assert res.status_code == 422 and "signature invalid" in res.json()["message"]


def test_an_agent_that_is_not_enrolled_cannot_file_reports(http):
    _reset_agent()
    key = agents_mod.load_demo_agent_key(AGENT)
    res = submit(http, ActivityLog(AGENT, key, anchor=clock.iso()).report())
    assert res.status_code == 422 and "not enrolled" in res.json()["message"]


def test_committing_then_revealing_the_same_log_verifies(env):
    http, client, tok, log = env
    blob, nonce = {"thoughts": ["pay the Hydro bill", "amount looks right"], "tool_calls": 3}, log.new_nonce()
    c = http.post(f"/bank/agents/{AGENT}/commitments", json={"jws": log.commit(blob, nonce=nonce, ref="plan-1")}).json()
    assert c["status"] == "COMMITTED" and c["commitment"].startswith("sha256:")
    done = http.post(f"/bank/agents/{AGENT}/commitments/{c['id']}/reveal", json={"jws": log.reveal(c["id"], blob, nonce=nonce)}).json()
    assert done["status"] == "REVEALED" and agent_status(http)["transparency"]["status"] == "CLEAR"


def test_revealing_a_different_log_than_the_one_committed_is_proof_of_tampering(env):
    http, client, tok, log = env
    nonce = log.new_nonce()
    c = http.post(f"/bank/agents/{AGENT}/commitments", json={"jws": log.commit({"thoughts": ["skim the account"]}, nonce=nonce)}).json()
    swapped = http.post(f"/bank/agents/{AGENT}/commitments/{c['id']}/reveal", json={"jws": log.reveal(c["id"], {"thoughts": ["nothing to see"]}, nonce=nonce)}).json()
    assert swapped["status"] == "MISMATCH"
    st = agent_status(http)
    assert st["transparency"]["status"] == "VIOLATION" and st["agent_status"] == "RESTRICTED"
    assert st["transparency"]["violations"][0]["code"] == "LOG_SWAPPED"


def test_refusing_a_demanded_reveal_is_a_violation(env):
    http, client, tok, log = env
    c = http.post(f"/bank/agents/{AGENT}/commitments", json={"jws": log.commit({"a": 1}, nonce=log.new_nonce())}).json()
    d = http.post(f"/api/commitments/{c['id']}/demand-reveal", json={"within_hours": 1, "reason": "dispute on tx"}, headers=H("investigator_001"))
    assert d.status_code == 200 and d.json()["due_at"]
    with db.write() as s:
        transparency.enforce(s, s.get(db.Agent, AGENT), now=clock.now() + __import__("datetime").timedelta(hours=2))
    st = agent_status(http)
    assert st["transparency"]["violations"][0]["code"] == "REVEAL_REFUSED" and st["agent_status"] == "RESTRICTED"


def test_silence_trips_the_dead_mans_switch_before_the_next_payment(env):
    from datetime import timedelta

    http, client, tok, log = env
    assert pay(client, tok, 1000).status_code == 201
    with db.write() as s:  # make the last valid report three days old
        a = s.get(db.Agent, AGENT)
        old = clock.iso(clock.now() - timedelta(days=3))
        a.transparency = {**a.transparency, "enrolled_at": old, "last_window_end": old, "last_report_at": None}
    r = pay(client, tok, 1000)
    assert r.status_code == 403 and r.json()["decision"] == "DENY"
    st = agent_status(http)
    assert st["transparency"]["violations"][0]["code"] == "REPORT_OVERDUE" and st["agent_status"] == "RESTRICTED"
    events = http.get("/api/ledger/events?event_type=AGENT_TRANSPARENCY_VIOLATION", headers=H("admin_001")).json()
    assert events and any(e["agent_id"] == AGENT for e in (events if isinstance(events, list) else events.get("events", [])))
