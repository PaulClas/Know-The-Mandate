"""Executable proof. Fails if KYM stops blocking an attack, if the honest gap disappears, or if a baseline is made weaker to flatter KYM."""
import pytest

from kym import redteam


@pytest.fixture(scope="module")
def report(client):
    return redteam.run_all()


def tier(report, aid, t):
    return next(a for a in report["attacks"] if a["id"] == aid)["results"][t]["blocked"]


def test_no_harness_errors(report):
    assert report["summary"]["errors"] == []


def test_kym_blocks_every_attack_except_the_documented_honest_case(report):
    assert report["summary"]["kym_not_blocked"] == ["in_mandate_malicious"]
    assert report["summary"]["kym"]["blocked"] == report["summary"]["kym"]["applicable"]


@pytest.mark.parametrize("aid,scope_only,rar_static", [
    ("beneficiary_swap", False, True), ("over_limit", False, True), ("budget_drain", False, False), ("budget_race", False, False), ("revoked_mandate", False, False),
    ("stolen_token", False, False), ("approval_threshold_bypass", False, False), ("approval_substitution", False, False), ("approval_replay", False, False),
    ("prompt_injection", False, True), ("in_mandate_malicious", False, False),
])
def test_baselines_fail_where_expected(report, aid, scope_only, rar_static):
    """Pins the comparison: static RAR genuinely stops swaps and over-limit payments; it cannot stop stateful or possession-based attacks."""
    assert tier(report, aid, "scope_only") is scope_only
    assert tier(report, aid, "rar_static") is rar_static


def test_oauth_plus_static_rar_is_a_real_steelman(report):
    s = report["summary"]
    assert s["rar_static"]["blocked"] > s["scope_only"]["blocked"] >= 0  # RAR is meaningfully better than scopes alone
    assert s["rar_static"]["blocked"] < s["kym"]["blocked"]


def test_honest_gap_is_reported_not_hidden(report):
    row = next(a for a in report["attacks"] if a["id"] == "in_mandate_malicious")
    assert row["expected_gap"] and row["results"]["kym"]["blocked"] is False and "NOT detectable" in row["results"]["kym"]["detail"]


def test_security_headers_and_body_limit(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY" and "default-src 'none'" in r.headers["content-security-policy"]
    big = client.post("/oauth/par", content=b"x" * 1_100_000, headers={"content-type": "application/json"})
    assert big.status_code == 413


def test_rate_limit_applies_to_unauthenticated_surface(client, monkeypatch):
    from kym import security

    monkeypatch.setattr(security, "REQUESTS", security.RateLimiter(5))
    codes = [client.post("/bank/payments", json={}).status_code for _ in range(8)]
    assert 429 in codes and codes[0] != 429


def test_session_secret_is_not_the_old_public_constant():
    from kym import config

    assert config.session_secret() != "demo-only-session-secret-do-not-use-in-production" and len(config.session_secret()) >= 32


def test_evidence_verification_endpoint_pins_server_keys(client):
    from kym.demo import session_headers

    tx = client.get("/api/transactions", headers=session_headers("admin_001")).json()
    if not tx:
        from kym import scenarios

        scenarios.run("B")
        tx = client.get("/api/transactions", headers=session_headers("admin_001")).json()
    pkg = client.get(f"/api/transactions/{tx[0]['id']}/evidence/download", headers=session_headers("admin_001")).json()
    assert client.post("/api/evidence/verify", json=pkg, headers=session_headers("admin_001")).json()["key_trust"] == "PINNED_BY_VERIFIER"
    pkg["public_keys"]["ledger"]["x"] = "AAAA"
    assert client.post("/api/evidence/verify", json=pkg, headers=session_headers("admin_001")).json()["ok"] is False
