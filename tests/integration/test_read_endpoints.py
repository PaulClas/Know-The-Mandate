import pytest

from kym import scenarios
from kym.demo import session_headers

ROUTES = ["/api/overview", "/api/agents", "/api/customers", "/api/accounts", "/api/payees", "/api/mandates", "/api/delegation/graph", "/api/approvals", "/api/ledger/events", "/api/ledger/checkpoints",
          "/api/transactions", "/api/scenarios", "/api/sandbox/agents", "/api/ontology", "/api/ontology/classes", "/api/ontology/graph?mode=schema", "/api/ontology/graph?mode=instances",
          "/api/ontology/examples", "/api/ontology/turtle", "/api/responsibility/matrix", "/api/responsibility/faults", "/api/compliance/controls", "/api/compliance/controls?jurisdiction=CA-QC",
          "/api/compliance/profiles", "/api/standards", "/api/adapters", "/api/metrics", "/health", "/.well-known/jwks.json", "/.well-known/oauth-authorization-server"]


@pytest.mark.parametrize("path", ROUTES)
def test_read_endpoint_returns_200_with_populated_data(client, path):
    scenarios.run("G")  # guarantees delegation edges, approvals-free decisions and transactions exist
    r = client.get(path, headers=session_headers("admin_001"))
    assert r.status_code == 200, r.text[:300]


def test_example_sparql_queries_all_execute(client):
    scenarios.run("B")
    scenarios.run("J")  # produces an approved transaction
    ex = client.get("/api/ontology/examples", headers=session_headers("admin_001")).json()
    assert len(ex) == 6
    for e in ex:
        r = client.post("/api/ontology/query", json={"query": e["query"]}, headers=session_headers("admin_001"))
        assert r.status_code == 200, (e["id"], r.text[:200])
        if e["id"] in ("agents-can-initiate-payments", "mandates-for-beneficiary", "who-approved"):
            assert r.json()["rows"], e["id"]


def test_downstream_of_revoked_query_finds_cascaded_child(client):
    scenarios.run("G")
    q = next(e for e in client.get("/api/ontology/examples", headers=session_headers("admin_001")).json() if e["id"] == "downstream-of-revoked")
    rows = client.post("/api/ontology/query", json={"query": q["query"]}, headers=session_headers("admin_001")).json()["rows"]
    assert rows and rows[0]["childStatus"] == "REVOKED"


def test_mcp_adapter_lists_tools_and_enforces_policy(client):
    r = client.post("/adapters/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    assert {t["name"] for t in r["result"]["tools"]} >= {"get_balance", "initiate_payment"}
    call = client.post("/adapters/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "initiate_payment", "arguments": {"account_id": "account_001", "beneficiary_id": "x", "amount_minor": 1, "currency": "CAD", "idempotency_key": "k"}}}).json()
    assert call["result"]["isError"] is True  # discovery is not permission: no token => rejected
