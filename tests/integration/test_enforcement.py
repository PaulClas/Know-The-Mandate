import copy
import uuid

import pytest
from sqlalchemy import select

from kym import bank, clock, db, demo, keys, mandates
from kym.demo import session_headers


def H(u):
    return session_headers(u)


def cnl_text(**kw):
    from kym import scenarios

    return scenarios._bill_cnl(**kw)


@pytest.fixture
def active(http):
    m = demo.new_mandate("customer_001", cnl_text())
    client, tok = demo.connect(http, "agent_billpay_001", m, "customer_001")
    return m, client, tok


def pay(client, tok, amt=5000, ben="beneficiary_hydro_quebec", idem=None, **kw):
    body = {"account_id": "account_001", "beneficiary_id": ben, "amount_minor": amt, "currency": "CAD", "purpose": "household_bill_management", **kw}
    return client.call(tok, "POST", "/bank/payments", json_body=body, idempotency_key=idem or uuid.uuid4().hex)


def test_token_valid_but_mandate_invalid_is_denied(active):
    m, client, tok = active
    r = pay(client, tok, 5000, "beneficiary_videotron")
    assert r.status_code == 403 and r.json()["reason_codes"] == ["BENEFICIARY_NOT_AUTHORIZED"]
    assert not [c for c in r.json()["failed_checks"] if c["id"].startswith("token.")]


@pytest.mark.parametrize("profile,code", [("wrong_audience", "INVALID_TOKEN"), ("expired", "INVALID_TOKEN"), ("wrong_actor", "INVALID_ACTOR_BINDING"), ("missing_scope", "TOKEN_SCOPE_INSUFFICIENT"), ("revoked", "INVALID_TOKEN"), ("no_dpop", "INVALID_TOKEN")])
def test_defective_tokens_rejected_by_same_pdp(http, active, profile, code):
    m, _, _ = active
    body = {"agent_id": "agent_billpay_001", "mandate_id": m["mandate_id"], "action": "payments.initiate", "account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": 5000, "currency": "CAD",
            "purpose": "household_bill_management", "token_profile": profile}
    r = http.post("/api/authorization/evaluate", json=body, headers=H("customer_001")).json()
    assert r["decision"] == "DENY" and code in r["reason_codes"] and r["oauth_verification"] == "FAIL"


def test_playground_valid_profile_allows(http, active):
    m, _, _ = active
    body = {"agent_id": "agent_billpay_001", "mandate_id": m["mandate_id"], "action": "payments.initiate", "account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": 5000, "currency": "CAD", "purpose": "household_bill_management"}
    r = http.post("/api/authorization/evaluate", json=body, headers=H("customer_001")).json()
    assert r["decision"] == "ALLOW" and r["oauth_verification"] == "PASS" and r["dry_run"]


def test_invalid_token_signature_rejected_401(http, active):
    m, client, tok = active
    forged = tok.access_token[:-4] + "AAAA"
    r = client.call(forged, "POST", "/bank/payments", json_body={"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": 100, "currency": "CAD"}, idempotency_key="k1")
    assert r.status_code == 401


def test_unauthorized_account_rejected(http, active):
    m, client, tok = active
    r = pay(client, tok, 5000, account_id="account_002")
    assert r.status_code == 403 and "RESOURCE_NOT_AUTHORIZED" in r.json()["reason_codes"]


def test_customer_cannot_delegate_authority_over_account_they_do_not_control():
    with db.write() as s:
        c = mandates.compile_full(s, principal_id="customer_002", cnl_text=cnl_text())  # Alice's account named in Ben's mandate
        assert c["ok"] and not c["validation"]["ok"]
        res = mandates.propose(s, c["mandate"], created_by="customer_002")
    assert res["status"] == "REJECTED"
    failed = [x["id"] for x in res["validation"]["semantic"]["checks"] if not x["ok"]]
    assert any(f.endswith(".authority") for f in failed)


def test_expired_mandate_rejected(active, monkeypatch):
    m, client, tok = active
    clock.advance(31 * 86400)
    try:
        r = pay(client, tok)
        assert r.status_code == 401 or "MANDATE_EXPIRED" in r.json().get("reason_codes", []) or "INVALID_TOKEN" in r.json().get("reason_codes", [])
    finally:
        clock.reset()


def test_approval_expiry(http, active):
    m, client, tok = active
    r = pay(client, tok, 18000)
    aid = r.json()["approval_id"]
    clock.advance(1000)
    try:
        d = http.post(f"/api/approvals/{aid}/approve", headers=H("customer_001"))
        assert d.status_code == 409
    finally:
        clock.reset()


def test_approval_replay_and_substitution_prevented(http, active):
    m, client, tok = active
    k = uuid.uuid4().hex
    r = pay(client, tok, 18000, idem=k)
    aid = r.json()["approval_id"]
    assert http.post(f"/api/approvals/{aid}/approve", headers=H("customer_001")).json()["status"] == "APPROVED"
    sub = pay(client, tok, 19000, approval_id=aid)
    assert sub.status_code == 202 and "APPROVAL_INVALID" in sub.json()["reason_codes"]
    ok = pay(client, tok, 18000, approval_id=aid, idem=k)
    assert ok.status_code == 201
    replay = pay(client, tok, 18000, approval_id=aid)
    assert replay.status_code == 202 and "APPROVAL_INVALID" in replay.json()["reason_codes"]


def test_one_time_approval_does_not_expand_mandate(http, active):
    m, client, tok = active
    r = pay(client, tok, 18000)
    http.post(f"/api/approvals/{r.json()['approval_id']}/approve", headers=H("customer_001"))
    view = http.get(f"/api/mandates/{m['mandate_id']}", headers=H("customer_001")).json()
    assert view["digest"] == m["digest"] and view["versions"] == [{"version": 1, "status": "ACTIVE"}]


def test_idempotent_execution(active):
    m, client, tok = active
    k = uuid.uuid4().hex
    a, b = pay(client, tok, 5000, idem=k), pay(client, tok, 5000, idem=k)
    assert a.json()["transaction_id"] == b.json()["transaction_id"] and b.json().get("idempotent_replay")
    c = pay(client, tok, 6000, idem=k)
    assert c.status_code == 409


@pytest.mark.parametrize("amount", [1.5, "5000", True, -5, None])
def test_monetary_units_validated(active, amount):
    m, client, tok = active
    r = client.call(tok, "POST", "/bank/payments", json_body={"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": amount, "currency": "CAD"}, idempotency_key=uuid.uuid4().hex)
    assert r.status_code == 400


def test_concurrent_requests_cannot_exceed_budget(http):
    from concurrent.futures import ThreadPoolExecutor

    m = demo.new_mandate("customer_001", cnl_text(maximum=250, monthly=300, approval=250))
    client, tok = demo.connect(http, "agent_billpay_001", m, "customer_001")
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda _: pay(client, tok, 10000), range(8)))
    executed = [r for r in res if r.json().get("status") == "EXECUTED"]
    assert len(executed) == 3 and all("MONTHLY_LIMIT_EXCEEDED" in r.json()["reason_codes"] for r in res if r.status_code == 403)
    with db.read() as s:
        spent = sum(t.amount_minor for t in s.execute(select(db.Transaction).where(db.Transaction.mandate_id == m["mandate_id"], db.Transaction.status == "EXECUTED")).scalars())
        assert spent == 30000 and bank.trial_balance(s)["balanced"]


def test_mandate_signature_tampering_blocks_activation():
    m = demo.new_mandate("customer_001", cnl_text(), activate=False)
    with db.write() as s:
        mandates.approve(s, m["mandate_id"], 1, approver_id="customer_001", presented_digest=m["digest"])
        consent = s.execute(select(db.Consent).where(db.Consent.mandate_id == m["mandate_id"])).scalar_one()
        consent.receipt = {**consent.receipt, "approver_id": "customer_002"}
        s.flush()
        with pytest.raises(mandates.MandateError) as e:
            mandates.activate(s, m["mandate_id"], 1, actor_id="admin_001")
        assert e.value.code == "APPROVAL_INVALID"


def test_policy_version_preserved_on_decision_and_replayable(http, active):
    m, client, tok = active
    r = pay(client, tok, 5000)
    ev = http.get(f"/api/transactions/{r.json()['transaction_id']}/evidence", headers=H("admin_001")).json()
    assert ev["policy"]["version"] == "bank-policy-1.0.0" and ev["policy"]["replay"]["matches"] and ev["policy"]["replay"]["inputs_digest_ok"]


def test_historical_reconstruction_after_revocation(http, active):
    m, client, tok = active
    r = pay(client, tok, 5000)
    http.post(f"/api/mandates/{m['mandate_id']}/revoke", json={"reason": "x"}, headers=H("customer_001"))
    ev = http.get(f"/api/transactions/{r.json()['transaction_id']}/evidence", headers=H("admin_001")).json()
    assert ev["policy"]["decision"] == "ALLOW" and ev["policy"]["replay"]["matches"]  # decision reconstructed as it was at the time
    assert ev["mandate"]["status_now"] == "REVOKED" and ev["subsequent_events"]


def test_cascading_revocation_and_delegation_checks(http):
    from kym import scenarios

    r = scenarios.run("G")
    assert r["passed"], [s for s in r["steps"] if not s["ok"]]


def test_cross_customer_access_prevented(http, active):
    m, client, tok = active
    assert http.get(f"/api/mandates/{m['mandate_id']}", headers=H("customer_002")).status_code == 403
    lst = http.get("/api/mandates", headers=H("customer_002")).json()
    assert all(x["principal_id"] == "customer_002" for x in lst)
    tx = pay(client, tok).json()["transaction_id"]
    assert http.get(f"/api/transactions/{tx}", headers=H("customer_002")).status_code == 403
    assert http.get(f"/api/transactions/{tx}/evidence", headers=H("customer_002")).status_code == 403
    assert http.post(f"/api/mandates/{m['mandate_id']}/revoke", json={}, headers=H("customer_002")).status_code == 403
    evs = http.get("/api/ledger/events?limit=500", headers=H("customer_002")).json()["events"]
    assert all(e["principal_id"] == "customer_002" for e in evs)


def test_suspended_agent_is_denied_immediately(http, active):
    m, client, tok = active
    assert pay(client, tok).status_code == 201
    assert http.post("/api/agents/agent_billpay_001/suspend", json={"reason": "test"}, headers=H("admin_001")).status_code == 200
    try:
        r = pay(client, tok)
        assert r.status_code == 403 and "AGENT_SUSPENDED" in r.json()["reason_codes"]
    finally:
        with db.write() as s:
            from kym import agents

            agents.verify(s, "agent_billpay_001", actor_id="admin_001")


def test_ledger_signature_and_tamper_detection_on_authoritative_data(http, active):
    from kym import ledger

    m, client, tok = active
    pay(client, tok)
    with db.read() as s:
        assert ledger.verify_authoritative(s)["ok"]
        ev = ledger.all_events(s)
        pl = ledger.payload_map(s)
        cps = ledger.checkpoints(s)
    bad = copy.deepcopy(ev)
    bad[-1]["actor_id"] = "mallory"
    assert not ledger.verify(bad, pl, cps)["ok"]
    assert keys.verify_ed25519(keys.ledger_key().public_b64u, b"x", "AAAA") is False
