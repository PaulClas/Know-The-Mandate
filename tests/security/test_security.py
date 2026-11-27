"""Security invariants: sender-constrained tokens, engine isolation, RBAC, fail-closed behavior."""
import time
import uuid

import pytest

from kym import bank, canon, clock, db, demo, keys
from kym.demo import session_headers


def H(u):
    return session_headers(u)


@pytest.fixture
def active():
    from kym import scenarios

    m = demo.new_mandate("customer_001", scenarios._bill_cnl())
    return m


@pytest.fixture
def conn(http, active):
    client, tok = demo.connect(http, "agent_billpay_001", active, "customer_001")
    return client, tok


BODY = {"account_id": "account_001", "beneficiary_id": "beneficiary_hydro_quebec", "amount_minor": 5000, "currency": "CAD", "purpose": "household_bill_management"}


def raw(http, client, tok, proof, body=BODY, url="http://testserver/bank/payments"):
    return http.post(url, json=body, headers={"Authorization": f"DPoP {tok.access_token}", "DPoP": proof, "Idempotency-Key": uuid.uuid4().hex})


def test_dpop_proof_replay_rejected(http, conn):
    client, tok = conn
    proof = client.dpop("POST", "http://testserver/bank/payments", tok.access_token)
    assert raw(http, client, tok, proof).status_code == 201
    r = raw(http, client, tok, proof)
    assert r.status_code == 403 and "INVALID_TOKEN" in r.json()["reason_codes"]


@pytest.mark.parametrize("kind", ["wrong_method", "wrong_uri", "wrong_token_hash", "stale_iat", "missing"])
def test_dpop_binding_checks(http, conn, kind):
    client, tok = conn
    url = "http://testserver/bank/payments"
    proofs = {
        "wrong_method": client.dpop("GET", url, tok.access_token), "wrong_uri": client.dpop("POST", "http://testserver/bank/transfers", tok.access_token),
        "wrong_token_hash": client.dpop("POST", url, "some-other-token"), "stale_iat": client.dpop("POST", url, tok.access_token, iat=int(time.time()) - 3600), "missing": "",
    }
    r = http.post(url, json=BODY, headers={"Authorization": f"DPoP {tok.access_token}", **({"DPoP": proofs[kind]} if proofs[kind] else {}), "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 403 and "INVALID_TOKEN" in r.json()["reason_codes"]


def test_stolen_token_with_attackers_key_is_rejected(http, conn):
    from cryptography.hazmat.primitives.asymmetric import ec

    from kym.agent_sdk import AgentClient

    client, tok = conn
    thief = AgentClient(http, "agent_billpay_001", client.client_id, "x", ec.generate_private_key(ec.SECP256R1()))
    r = thief.call(tok, "POST", "/bank/payments", json_body=BODY, idempotency_key=uuid.uuid4().hex)
    assert r.status_code == 403 and "INVALID_TOKEN" in r.json()["reason_codes"]


def test_authorization_code_single_use_and_pkce(http, active):
    import hashlib
    import secrets

    from kym import cnl, config
    from kym.canon import b64u

    client = demo.agent_client(http, "agent_billpay_001")
    details = cnl.authorization_details(active["content"])
    ver = secrets.token_urlsafe(40)
    par = http.post("/oauth/par", json={"client_id": client.client_id, "client_secret": client.client_secret, "response_type": "code", "code_challenge": b64u(hashlib.sha256(ver.encode()).digest()),
                                        "code_challenge_method": "S256", "resource": config.API_AUDIENCE, "authorization_details": details})
    code = demo.customer_approver(http, "customer_001")(par.json()["request_uri"])["code"]
    url = "http://testserver/oauth/token"
    def tok(verifier):
        return http.post(url, json={"grant_type": "authorization_code", "client_id": client.client_id, "client_secret": client.client_secret, "code": code, "code_verifier": verifier}, headers={"DPoP": client.dpop("POST", url)})
    assert tok("wrong-verifier").status_code == 400  # PKCE failure burns the code
    assert tok(ver).status_code == 400  # and a code can never be reused


def test_par_rejects_authority_beyond_mandate_and_wrong_client(http, active):
    import hashlib

    from kym import cnl, config
    from kym.canon import b64u

    d = cnl.authorization_details(active["content"])
    d[0]["accounts"] = ["account_001", "account_002"]
    client = demo.agent_client(http, "agent_billpay_001")
    base = {"client_id": client.client_id, "client_secret": client.client_secret, "response_type": "code", "code_challenge": b64u(hashlib.sha256(b"v").digest()), "code_challenge_method": "S256", "resource": config.API_AUDIENCE}
    assert http.post("/oauth/par", json={**base, "authorization_details": d}).status_code == 400
    other = demo.agent_client(http, "agent_shopping_001")
    r = http.post("/oauth/par", json={**base, "client_id": other.client_id, "client_secret": other.client_secret, "authorization_details": cnl.authorization_details(active["content"])})
    assert r.status_code == 400 and r.json()["error"] == "unauthorized_client"
    assert http.post("/oauth/par", json={**base, "client_secret": "wrong", "authorization_details": cnl.authorization_details(active["content"])}).status_code == 401
    assert http.post("/oauth/par", json={**base, "resource": "https://evil.example", "authorization_details": cnl.authorization_details(active["content"])}).json()["error"] == "invalid_target"


def test_unverified_agent_cannot_obtain_credentials(http, active):
    c = demo.agent_client(http, "agent_unverified_001")
    r = http.post("/oauth/par", json={"client_id": c.client_id, "client_secret": c.client_secret, "response_type": "code"})
    assert r.status_code == 403


def test_payment_engine_refuses_without_valid_bound_certificate(conn):
    client, tok = conn
    ok = client.call(tok, "POST", "/bank/payments", json_body=BODY, idempotency_key=uuid.uuid4().hex).json()
    with db.write() as s:
        tx = s.get(db.Transaction, ok["transaction_id"])
        dec = s.get(db.Decision, tx.decision_id)
        cert = {"decision_id": dec.id, "decision": dec.decision, "op_hash": dec.op_hash, "policy_version": dec.policy_version, "inputs_digest": dec.inputs_digest, "issued_at": dec.created_at,
                "expires_at": dec.expires_at, "signature": dec.signature, "key_id": dec.key_id}
        bank.verify_certificate(cert, tx.op_hash)  # genuine certificate verifies
        for bad, exc in [({**cert, "op_hash": "sha256:other"}, "CERT_INVALID"), ({**cert, "signature": "AAAA"}, "CERT_INVALID"), ({**cert, "decision": "DENY"}, "CERT_INVALID")]:
            with pytest.raises(bank.EngineError) as e:
                bank.verify_certificate(bad, tx.op_hash)
            assert e.value.code == exc
        with pytest.raises(bank.EngineError) as e:
            bank.verify_certificate(cert, "sha256:different-operation")
        assert e.value.code == "CERT_OP_MISMATCH"
        with pytest.raises(bank.EngineError) as e:  # single use: already consumed by the real execution
            bank.execute_authorized(s, tx, cert)
        assert e.value.code in ("CERT_CONSUMED", "CERT_EXPIRED")


def test_expired_decision_certificate_refused():
    cert = bank.issue_certificate(None, None, {"decision": "ALLOW", "policy_version": "p"}, op_h="h", inputs_digest="d", ttl=-5)
    with pytest.raises(bank.EngineError) as e:
        bank.verify_certificate(cert, "h")
    assert e.value.code == "CERT_EXPIRED"


def test_sessions_and_roles_enforced(http):
    assert http.get("/api/agents").status_code == 401
    assert http.get("/api/agents", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    assert http.post("/api/agents/agent_unverified_001/verify", headers=H("customer_001")).status_code == 403
    assert http.post("/api/agents/agent_unverified_001/suspend", json={"reason": "x"}, headers=H("customer_001")).status_code == 403
    assert http.post("/api/demo/reset", headers=H("customer_001")).status_code == 403
    assert http.post("/api/scenarios/A/run", headers=H("customer_001")).status_code == 403
    assert http.post("/api/ontology/query", json={"query": "SELECT * WHERE {?s ?p ?o}"}, headers=H("customer_001")).status_code == 403
    assert http.post("/api/ledger/checkpoints", headers=H("customer_001")).status_code == 403


def test_admin_cannot_approve_mandates_or_transactions(http, active):
    assert http.post(f"/api/mandates/{active['mandate_id']}/approve", json={"digest": active["digest"]}, headers=H("admin_001")).status_code == 403


def test_agent_registration_cannot_self_verify(http):
    declared = {"display_name": "Sneaky", "category": "x", "operating_organization": "X", "operator_id": "organization_666", "responsible_party": "X", "developer": "X", "deployment_environment": "x",
                "model_provider": "x", "model_id": "x", "software_version": "1", "build_digest": "sha256:" + "cd" * 32, "supported_tools": [], "requested_capabilities": ["payments.initiate"], "declared_autonomy_level": "autonomous",
                "status": "VERIFIED"}
    r = http.post("/api/agents", json={"declared": declared, "agent_id": "agent_sneaky"}, headers=H("admin_001"))
    assert r.json()["agent"]["status"] == "PENDING_VERIFICATION" and r.json()["agent"]["verified"] == {}


def test_ledger_never_stores_reusable_tokens(http, conn):
    client, tok = conn
    http.get("/api/ledger/events?limit=500", headers=H("admin_001"))
    blob = str(http.get("/api/ledger/events?limit=500&q=tok_", headers=H("admin_001")).json())
    assert tok.access_token not in blob
    with db.read() as s:
        from sqlalchemy import select

        assert all(tok.access_token != t.token_hash for t in s.execute(select(db.Token)).scalars())


def test_demo_keys_are_not_exposed_by_api(http):
    blob = str(http.get("/api/ledger/checkpoints", headers=H("admin_001")).json())
    assert "PRIVATE" not in blob and "\"d\"" not in blob
    assert keys.ledger_key().public_b64u in blob


def test_policy_engine_has_no_clock_or_io_dependency_for_replay():
    from helpers import make_inputs, make_mandate

    from kym import policy

    i = make_inputs(make_mandate())
    a = policy.evaluate(i)
    time.sleep(0.01)
    assert policy.evaluate(i) == a and canon.digest(i) == canon.digest(i) and clock.now()
