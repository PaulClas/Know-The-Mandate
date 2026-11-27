"""The complete sequence from the project's definition of done, entirely over the HTTP API."""
import uuid

from kym import demo
from kym.demo import iso_in, session_headers


def H(u):
    return session_headers(u)


def test_end_to_end_agent_mandate_lifecycle(http):
    # 1-2. register and verify an agent
    declared = {"display_name": "Utility Helper", "category": "bill_payment", "operating_organization": "Helper Labs Inc.", "operator_id": "organization_099", "responsible_party": "Helper Labs Inc.",
                "developer": "Helper Labs", "deployment_environment": "sandbox", "model_provider": "SyntheticLM Labs (fictional)", "model_id": "synthetic-lm-1", "software_version": "0.1.0",
                "build_digest": "sha256:" + "ab" * 32, "supported_tools": ["get_balance", "initiate_payment"], "requested_capabilities": ["balances.read", "payments.initiate"], "declared_autonomy_level": "supervised"}
    r = http.post("/api/agents", json={"declared": declared, "agent_id": "agent_helper_e2e"}, headers=H("admin_001"))
    assert r.status_code == 201 and r.json()["agent"]["status"] == "PENDING_VERIFICATION"
    assert http.post("/api/agents/agent_helper_e2e/verify", headers=H("customer_001")).status_code == 403  # an agent/customer can never mark itself verified
    v = http.post("/api/agents/agent_helper_e2e/verify", headers=H("admin_001"))
    assert v.status_code == 200 and v.json()["status"] == "VERIFIED" and v.json()["verified"]["checks"]
    # 3-4. ambiguous natural language -> unresolved, nothing invented
    c = http.post("/api/mandates/compile", json={"principal_id": "customer_001", "instruction": "Manage my money, pay my usual bills and move some savings whenever it makes sense. Do not spend too much."}, headers=H("customer_001")).json()
    assert not c["ok"] and {a["kind"] for a in c["ambiguities"]} >= {"accounts", "bills", "excessive"}
    # 5-7. resolve, compile, validate
    cnl = f"""PURPOSE household_bill_management.
PERMIT agent.helper-e2e TO READ_BALANCE ON account.chequing-001.
PERMIT agent.helper-e2e TO INITIATE_PAYMENT FROM account.chequing-001 TO beneficiary.hydro-quebec WITH MAX_AMOUNT 250 CAD PER TRANSACTION.
LIMIT TOTAL_PAYMENTS TO 500 CAD PER CALENDAR_MONTH.
REQUIRE HUMAN_APPROVAL FOR PAYMENTS ABOVE 100 CAD.
PROHIBIT EXTERNAL_TRANSFER.
PROHIBIT DELEGATION.
EXPIRE AT {iso_in(days=30)}."""
    c = http.post("/api/mandates/compile", json={"principal_id": "customer_001", "cnl": cnl}, headers=H("customer_001")).json()
    assert c["ok"], c["errors"]
    assert c["shacl"]["conforms"] and c["validation"]["ok"]
    assert c["oauth"]["authorization_details"][0]["type"] == "kym_financial_mandate"
    assert c["consent_summary"]["fr"] and c["canonical_digest"].startswith("sha256:")
    m = http.post("/api/mandates", json={"principal_id": "customer_001", "cnl": cnl}, headers=H("customer_001")).json()
    assert m["status"] == "PENDING_CUSTOMER_APPROVAL"
    mid = m["mandate_id"]
    # an unapproved mandate cannot be activated
    assert http.post(f"/api/mandates/{mid}/activate", headers=H("customer_001")).status_code == 422
    # 8. bank-controlled approval bound to the digest
    assert http.post(f"/api/mandates/{mid}/approve", json={"digest": "sha256:" + "0" * 64}, headers=H("customer_001")).status_code == 422
    assert http.post(f"/api/mandates/{mid}/approve", json={"digest": m["digest"]}, headers=H("customer_002")).status_code == 403
    ap = http.post(f"/api/mandates/{mid}/approve", json={"digest": m["digest"]}, headers=H("customer_001"))
    assert ap.status_code == 200 and ap.json()["receipt"]["assurance"]["level"] == "DEMO_SIMULATED_SESSION"
    act = http.post(f"/api/mandates/{mid}/activate", headers=H("customer_001"))
    assert act.status_code == 200 and act.json()["status"] == "ACTIVE"
    # 9. mandate-bound credential
    mandate = http.get(f"/api/mandates/{mid}", headers=H("customer_001")).json()
    client, tok = demo.connect(http, "agent_helper_e2e", mandate, "customer_001")
    assert "payments.initiate" in tok.scope
    # 10-12. authorized operation executes
    pay = lambda amt, ben="beneficiary_hydro_quebec", **kw: client.call(tok, "POST", "/bank/payments", json_body={"account_id": "account_001", "beneficiary_id": ben, "amount_minor": amt, "currency": "CAD", "purpose": "household_bill_management", **kw}, idempotency_key=uuid.uuid4().hex)  # noqa: E731
    ok = pay(8500)
    assert ok.status_code == 201 and ok.json()["status"] == "EXECUTED"
    tx_id = ok.json()["transaction_id"]
    # 13-14. unauthorized operation with valid identity and credentials
    bad = pay(5000, "beneficiary_videotron")
    assert bad.status_code == 403 and "BENEFICIARY_NOT_AUTHORIZED" in bad.json()["reason_codes"]
    # 15-16. revoke, then reject further execution
    rv = http.post(f"/api/mandates/{mid}/revoke", json={"reason": "e2e", "revoke_tokens": False}, headers=H("customer_001"))
    assert rv.status_code == 200
    after = pay(8500)
    assert after.status_code == 403 and "MANDATE_REVOKED" in after.json()["reason_codes"]
    # 17-19. reconstruct, verify, attribute responsibility
    ev = http.get(f"/api/transactions/{tx_id}/evidence", headers=H("customer_001")).json()
    assert ev["verification"]["ok"] and ev["policy"]["replay"]["matches"] and ev["consent"]["signature_valid"]
    assert ev["mandate"]["status_now"] == "REVOKED" and any(e["event_type"] == "MANDATE_REVOKED" for e in ev["subsequent_events"])
    assert len(ev["responsibility"]["attribution"]) == 9 and ev["responsibility"]["cannot_establish"]
    pkg = http.get(f"/api/transactions/{tx_id}/evidence/download", headers=H("customer_001")).json()
    assert http.post("/api/evidence/verify", json=pkg, headers=H("admin_001")).json()["ok"]
    assert http.post("/api/ledger/verify", headers=H("admin_001")).json()["ok"]
