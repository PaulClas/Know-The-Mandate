"""Regression tests for findings from the independent pre-publication review (F-16 to F-21)."""
import copy
import uuid

import pytest

from kym import canon, clock, db, demo, gateway, keys, ledger, mandates, scenarios
from kym.agent_sdk import AgentClient
from kym.demo import session_headers


def H(u):
    return session_headers(u)


@pytest.fixture
def paid(http):
    """A real executed payment plus its evidence package."""
    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    client, tok = demo.connect(http, "agent_billpay_001", m, "customer_001")
    r = client.call(tok, "POST", "/bank/payments", json_body={"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": 5000,
                                                                "currency": "CAD", "purpose": "household_bill_management"}, idempotency_key=uuid.uuid4().hex)
    assert r.status_code == 201
    return http.get(f"/api/transactions/{r.json()['transaction_id']}/evidence/download", headers=H("admin_001")).json()


def verify(http, pkg):
    return http.post("/api/evidence/verify", json=pkg, headers=H("admin_001")).json()


# F-16: deleting the whole ledger must not pass checkpoint verification
def test_empty_chain_with_a_signed_checkpoint_is_reported_as_truncation(http):
    with db.write() as s:
        if not ledger.all_events(s):
            demo.new_mandate("customer_001", scenarios._bill_cnl())
        ledger.create_checkpoint(s)
    with db.read() as s:
        cps = ledger.checkpoints(s)
    res = ledger.verify([], {}, cps)
    assert not res["ok"] and any(p["check"] == "checkpoint" for p in res["problems"])


# F-17: the counterparty type comes from the payee registry, not from the request
def test_beneficiary_cannot_be_addressed_as_a_merchant(http):
    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    client, tok = demo.connect(http, "agent_billpay_001", m, "customer_001")
    body = {"account_id": "account_001", "merchant_id": "beneficiary_hydro_quebec", "amount_minor": 5000, "currency": "CAD", "purpose": "household_bill_management"}
    r = client.call(tok, "POST", "/bank/payments", json_body=body, idempotency_key=uuid.uuid4().hex)
    assert r.status_code == 400 and "registered as a beneficiary" in r.text


# F-18: budgets are counted when money moves (executed_at), not when the request was created
def test_budget_usage_is_counted_by_execution_time():
    from datetime import timedelta

    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    now = clock.now()
    with db.write() as s:
        base = gateway._usage(s, "customer_001", {m["mandate_id"]: "America/Toronto"}, now)[m["mandate_id"]]["day_minor"]
        mk = lambda executed: db.Transaction(id=f"tx_{uuid.uuid4().hex[:10]}", seq=10**9, kind="PAYMENT", action="payments.initiate", status="EXECUTED", principal_id="customer_001",  # noqa: E731
                                              agent_id="agent_billpay_001", mandate_id=m["mandate_id"], mandate_version=1, mandate_chain=[m["mandate_id"]], amount_minor=7777, currency="CAD",
                                              created_at=clock.iso(now - timedelta(days=3)), updated_at=clock.iso(now), executed_at=clock.iso(executed))
        s.add(mk(now))  # requested days ago, executed today: counts today
        s.add(mk(now - timedelta(days=3)))  # executed days ago: does not count today
        s.flush()
        usage = gateway._usage(s, "customer_001", {m["mandate_id"]: "America/Toronto"}, now)[m["mandate_id"]]["day_minor"]
        s.rollback()
    assert usage - base == 7777


# F-19: a token narrower than the mandate is enforced, not ignored
def test_token_authorization_details_narrower_than_the_mandate_are_enforced(http):
    from kym import cnl as cnl_mod

    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    details = copy.deepcopy(cnl_mod.authorization_details(m["content"]))
    for d in details:
        if "maximum_amount" in d:
            d["maximum_amount"]["amount_minor"] = 10000
    client = demo.agent_client(http, "agent_billpay_001")
    tok = client.authorize(details, demo.customer_approver(http, "customer_001"))
    pay = lambda amt: client.call(tok, "POST", "/bank/payments", json_body={"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": amt,  # noqa: E731
                                                                          "currency": "CAD", "purpose": "household_bill_management"}, idempotency_key=uuid.uuid4().hex)
    assert pay(8000).status_code == 201
    over = pay(20000)  # inside the mandate (CAD 250) but outside what this token asked for (CAD 100)
    assert over.status_code == 403 and over.json()["reason_codes"] == ["TOKEN_SCOPE_INSUFFICIENT"]


# F-20: token exchange binds the new token only to the agent's registered DPoP key
def test_token_exchange_rejects_an_unregistered_dpop_key(http):
    from cryptography.hazmat.primitives.asymmetric import ec

    from kym import agents as agents_mod

    parent = demo.new_mandate("customer_001", scenarios._bill_cnl(agent="agent.finance-assistant", verb="PAY_INVOICE", extra="ALLOW DELEGATION TO DEPTH 1."))
    client, tok = demo.connect(http, "agent_finance_001", parent, "customer_001")
    with db.read() as s:
        child_agent = s.get(db.Agent, "agent_billpay_001")
        content = mandates.get_row(s, parent["mandate_id"]).content
    child = http.post(f"/api/mandates/{parent['mandate_id']}/delegate", headers=H("customer_001"), json={"child_content": None}) if False else None
    draft = demo.child_from_parent(content, child_agent, max_amount_minor=20000, monthly_minor=50000)
    x = client.call(tok, "POST", f"/api/mandates/{parent['mandate_id']}/delegate", json_body={"child_content": draft})
    assert x.status_code == 201, x.text
    child = x.json()
    c_client = demo.agent_client(http, "agent_billpay_001")
    assert c_client.exchange(tok.access_token, child["mandate_id"], client.subject_proof(tok.access_token)).access_token  # registered key + parent co-signature: works
    attacker = AgentClient(http, c_client.agent_id, c_client.client_id, c_client.client_secret, ec.generate_private_key(ec.SECP256R1()))
    assert agents_mod.public_jwk(attacker.key) != c_client.jwk
    with pytest.raises(Exception, match="registered key"):
        attacker.exchange(tok.access_token, child["mandate_id"], client.subject_proof(tok.access_token))
    _ = child


# F-21: an evidence package cannot show a story that its signed events do not support
def test_package_with_altered_amount_fails_even_with_pinned_keys(http, paid):
    assert verify(http, paid)["ok"] is True
    forged = copy.deepcopy(paid)
    forged["transaction"]["amount_minor"] = 1
    res = verify(http, forged)
    assert res["ok"] is False and any(p["check"] == "evidence_binding" for p in res["problems"])


def test_package_without_transaction_evidence_fails(http, paid):
    forged = copy.deepcopy(paid)
    forged["ledger_events"] = [e for e in forged["ledger_events"] if e.get("transaction_id") != forged["transaction"]["id"]]
    assert verify(http, forged)["ok"] is False


def test_package_replay_flag_is_not_trusted(http, paid):
    forged = copy.deepcopy(paid)
    forged["policy"]["inputs"]["request"]["amount_minor"] = 1  # change the evidence, keep the (stale) replay flag
    res = verify(http, forged)
    assert res["ok"] is False and any(p["check"] in ("decision_inputs", "decision_replay") for p in res["problems"])


_ = (canon, keys)


# O-25 (partly closed): the payment engine refuses to execute a transaction whose fields no longer match the authorized hash
def test_payment_engine_refuses_mutated_transaction_fields(http):
    from kym import bank

    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    client, tok = demo.connect(http, "agent_billpay_001", m, "customer_001")
    body = {"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": 5000, "currency": "CAD", "purpose": "household_bill_management", "action": "payments.initiate"}
    r = client.call(tok, "POST", "/bank/payments", json_body=body, idempotency_key=uuid.uuid4().hex)
    assert r.status_code == 201
    with db.write() as s:
        tx = s.get(db.Transaction, r.json()["transaction_id"])
        dec = s.get(db.Decision, tx.decision_id)
        cert = {"decision_id": dec.id, "decision": dec.decision, "op_hash": dec.op_hash, "tx_id": tx.id, "issued_at": dec.created_at, "expires_at": dec.expires_at, "inputs_digest": dec.inputs_digest,
                "policy_version": dec.policy_version, "signature": dec.signature, "key_id": dec.key_id}
        tx.amount_minor = 999999
        with pytest.raises(bank.EngineError) as e:
            bank.execute_authorized(s, tx, cert)
        assert e.value.code == "OP_TAMPERED"
        s.rollback()


# F-22: the parent must co-sign a token exchange; a leaked parent token plus the child's credentials is not enough
def test_token_exchange_requires_the_parents_proof_of_possession(http):
    parent = demo.new_mandate("customer_001", scenarios._bill_cnl(agent="agent.finance-assistant", verb="PAY_INVOICE", extra="ALLOW DELEGATION TO DEPTH 1."))
    client, tok = demo.connect(http, "agent_finance_001", parent, "customer_001")
    with db.read() as s:
        child_agent = s.get(db.Agent, "agent_billpay_001")
        content = mandates.get_row(s, parent["mandate_id"]).content
    x = client.call(tok, "POST", f"/api/mandates/{parent['mandate_id']}/delegate", json_body={"child_content": demo.child_from_parent(content, child_agent, max_amount_minor=20000, monthly_minor=50000)})
    child_id = x.json()["mandate_id"]
    c_client = demo.agent_client(http, "agent_billpay_001")
    for bad in (None, "", c_client.subject_proof(tok.access_token)):  # missing, empty, signed by the child's key instead of the parent's
        with pytest.raises(Exception, match="subject_dpop"):
            c_client.exchange(tok.access_token, child_id, bad)
    proof = client.subject_proof(tok.access_token)
    assert c_client.exchange(tok.access_token, child_id, proof).access_token
    with pytest.raises(Exception, match="replay"):
        c_client.exchange(tok.access_token, child_id, proof)  # the same proof cannot be reused


# F-24: a decision certificate is bound to its transaction
def test_certificate_for_one_transaction_cannot_execute_another(http):
    from kym import bank

    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    client, tok = demo.connect(http, "agent_billpay_001", m, "customer_001")
    body = {"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": 5000, "currency": "CAD", "purpose": "household_bill_management", "action": "payments.initiate"}
    ids = [client.call(tok, "POST", "/bank/payments", json_body=body, idempotency_key=uuid.uuid4().hex).json()["transaction_id"] for _ in range(2)]
    with db.write() as s:
        a, b = (s.get(db.Transaction, i) for i in ids)
        dec = s.get(db.Decision, a.decision_id)
        cert = {"decision_id": dec.id, "decision": dec.decision, "op_hash": dec.op_hash, "tx_id": a.id, "policy_version": dec.policy_version, "inputs_digest": dec.inputs_digest,
                "issued_at": dec.created_at, "expires_at": dec.expires_at, "signature": dec.signature, "key_id": dec.key_id}
        with pytest.raises(bank.EngineError) as e:
            bank.execute_authorized(s, b, cert)  # identical operation, different transaction
        assert e.value.code == "CERT_TX_MISMATCH"
        s.rollback()


# O-22 (partial): a changed engine is reported as such, not as tampering; an unchanged engine that disagrees is a problem
def test_replay_distinguishes_engine_change_from_tampering(http, paid, monkeypatch):
    from kym import policy

    assert verify(http, paid)["warnings"] == []
    monkeypatch.setattr(policy, "ENGINE_DIGEST", "sha256:a-later-engine")
    monkeypatch.setattr(policy, "replay", lambda inputs: {"decision": "DENY", "reason_codes": ["SOMETHING_NEW"]})
    res = verify(http, paid)
    assert res["ok"] is True and [w["check"] for w in res["warnings"]] == ["engine_changed"]
    monkeypatch.setattr(policy, "ENGINE_DIGEST", paid_digest(paid))  # same engine, different answer: that is tampering or a bug
    res = verify(http, paid)
    assert res["ok"] is False and any(p["check"] == "decision_replay" for p in res["problems"])


def paid_digest(pkg):
    return next(e["payload"]["engine_digest"] for e in pkg["ledger_events"] if e["event_type"] == "POLICY_EVALUATED" and e.get("payload"))
