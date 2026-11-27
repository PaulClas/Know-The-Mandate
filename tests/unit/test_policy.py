import copy

import pytest
from helpers import make_inputs, make_mandate, mutate, ts

from kym import policy


def ev(**kw):
    return policy.evaluate(make_inputs(**kw))


def codes(r):
    return set(r["reason_codes"])


def test_allows_within_mandate():
    r = ev(mandate=make_mandate())
    assert r["decision"] == "ALLOW" and r["reason_codes"] == []


@pytest.mark.parametrize("path,value,code", [
    ("token.signature_valid", False, "INVALID_TOKEN"), ("token.expired", True, "INVALID_TOKEN"), ("token.revoked", True, "INVALID_TOKEN"),
    ("token.audience_ok", False, "INVALID_TOKEN"), ("token.dpop_ok", False, "INVALID_TOKEN"), ("token.actor_ok", False, "INVALID_ACTOR_BINDING"),
    ("token.scopes", ["balances.read"], "TOKEN_SCOPE_INSUFFICIENT"), ("token.mandate_version", 2, "MANDATE_VERSION_MISMATCH"), ("token.mandate_hash", "sha256:bad", "MANDATE_VERSION_MISMATCH"),
    ("agent.status", "SUSPENDED", "AGENT_SUSPENDED"), ("agent.status", "PENDING_VERIFICATION", "AGENT_NOT_VERIFIED"), ("customer.kyc_status", "PENDING", "CUSTOMER_NOT_VERIFIED"),
    ("account.controlled_by_principal", False, "RESOURCE_NOT_AUTHORIZED"), ("account.status", "FROZEN", "ACCOUNT_RESTRICTED"),
])
def test_input_failures_deny_with_specific_code(path, value, code):
    r = policy.evaluate(mutate(make_inputs(make_mandate()), path, value))
    assert r["decision"] == "DENY" and code in codes(r)


def test_missing_token_and_missing_mandate_fail_closed():
    i = make_inputs(make_mandate())
    i["token"] = {"present": False}
    assert policy.evaluate(i)["decision"] == "DENY"
    i = make_inputs(make_mandate())
    i["mandate"] = {"found": False}
    assert "MANDATE_NOT_FOUND" in codes(policy.evaluate(i))


@pytest.mark.parametrize("status,code", [("REVOKED", "MANDATE_REVOKED"), ("EXPIRED", "MANDATE_EXPIRED"), ("SUSPENDED", "MANDATE_SUSPENDED"), ("SUPERSEDED", "MANDATE_VERSION_MISMATCH")])
def test_lifecycle_states_deny(status, code):
    assert code in codes(ev(mandate=make_mandate(), status=status))


def test_expired_validity_window_denies_even_if_status_active():
    m = make_mandate()
    m["validity"] = {"not_before": ts(-10), "expires_at": ts(-1), "budget_timezone": "America/Toronto"}
    assert "MANDATE_EXPIRED" in codes(ev(mandate=m))


def test_unauthorized_beneficiary_account_currency_amount_purpose():
    assert "BENEFICIARY_NOT_AUTHORIZED" in codes(ev(mandate=make_mandate(), beneficiary="beneficiary_other"))
    assert "RESOURCE_NOT_AUTHORIZED" in codes(ev(mandate=make_mandate(), account_id="account_002"))
    assert "CURRENCY_NOT_AUTHORIZED" in codes(ev(mandate=make_mandate(), currency="USD"))
    assert "TRANSACTION_LIMIT_EXCEEDED" in codes(ev(mandate=make_mandate(), amount=25001))
    assert "PURPOSE_NOT_AUTHORIZED" in codes(ev(mandate=make_mandate(), purpose="gambling"))


def test_unlisted_actions_denied_no_implicit_inheritance():
    m = make_mandate()
    assert "ACTION_NOT_AUTHORIZED" in codes(ev(mandate=m, action="transactions.read", amount=0))  # balance != transactions
    assert "ACTION_NOT_AUTHORIZED" in codes(ev(mandate=m, action="payments.prepare", amount=0))  # preparing != executing, and neither implies the other
    r = ev(mandate=m, action="transfers.execute")
    assert r["decision"] == "DENY" and "ACTION_NOT_AUTHORIZED" in codes(r)


def test_prohibition_overrides_permission_in_parent_chain():
    parent = make_mandate(prohibitions=["payments.initiate"], permissions=[{"action": "balances.read", "resources": ["account_001"]}])
    child = make_mandate(mandate_id="mdt_c")
    r = ev(mandate=child, chain=(parent,))
    assert r["decision"] == "DENY" and "ACTION_NOT_AUTHORIZED" in codes(r)


def test_daily_and_monthly_limits_count_executed_and_reserved():
    m = make_mandate()
    assert "DAILY_LIMIT_EXCEEDED" in codes(ev(mandate=m, amount=6000, usage={"mdt_t1": {"day_minor": 20000, "month_minor": 20000, "month_count": 2}}))
    assert "MONTHLY_LIMIT_EXCEEDED" in codes(ev(mandate=m, amount=6000, usage={"mdt_t1": {"day_minor": 0, "month_minor": 45000, "month_count": 2}}))
    assert ev(mandate=m, amount=5000, usage={"mdt_t1": {"day_minor": 0, "month_minor": 45000, "month_count": 2}})["decision"] == "ALLOW"


def test_human_approval_required_then_satisfied_only_by_valid_bound_approval():
    m = make_mandate()
    r = ev(mandate=m, amount=11000)
    assert r["decision"] == "REQUIRE_HUMAN_APPROVAL" and codes(r) == {"HUMAN_APPROVAL_REQUIRED"}
    ok = ev(mandate=m, amount=11000, approval={"supplied": True, "valid": True, "granted_count": 1, "problem": None})
    assert ok["decision"] == "ALLOW"
    bad = ev(mandate=m, amount=11000, approval={"supplied": True, "valid": False, "granted_count": 0, "problem": "approval was granted for a different operation payload"})
    assert bad["decision"] == "REQUIRE_HUMAN_APPROVAL" and "APPROVAL_INVALID" in codes(bad)


def test_two_approver_obligation_needs_two_grants():
    m = make_mandate(obligations={"human_approval_above_minor": 0, "required_approvals": 2, "notify_customer": True})
    assert ev(mandate=m, approval={"supplied": True, "valid": True, "granted_count": 1, "problem": None})["decision"] == "REQUIRE_HUMAN_APPROVAL"
    assert ev(mandate=m, approval={"supplied": True, "valid": True, "granted_count": 2, "problem": None})["decision"] == "ALLOW"


def test_risk_review_and_hard_stop_and_precedence():
    m = make_mandate()
    assert ev(mandate=m, risk_score=70)["decision"] == "REFER_TO_RISK_REVIEW"
    assert ev(mandate=m, risk_score=95)["decision"] == "DENY"
    assert "RISK_THRESHOLD_EXCEEDED" in codes(ev(mandate=m, risk_score=0, sanctions=True))
    r = ev(mandate=m, amount=11000, risk_score=70)
    assert r["decision"] == "REFER_TO_RISK_REVIEW"  # more restrictive than plain approval
    assert ev(mandate=m, beneficiary="x", risk_score=70)["decision"] == "DENY"  # denial beats referral


def test_missing_risk_information_fails_closed():
    i = make_inputs(make_mandate())
    i["risk"] = None
    r = policy.evaluate(i)
    assert r["decision"] == "DENY" and "POLICY_INPUT_UNVERIFIABLE" in codes(r)


def test_policy_version_and_inputs_are_preserved_and_replayable():
    i = make_inputs(make_mandate(), amount=30000)
    first = policy.evaluate(i)
    assert first["policy_version"] == i["bank_policy"]["policy_version"]
    snapshot = copy.deepcopy(i)
    assert policy.replay(snapshot) == first


def test_trace_is_explainable():
    r = ev(mandate=make_mandate(), beneficiary="b2")
    assert {"id", "name", "outcome", "detail"} <= set(r["trace"][0])
    assert any(c["outcome"] == "FAIL" and c["reason_code"] == "BENEFICIARY_NOT_AUTHORIZED" for c in r["trace"])


def test_delegation_action_requires_permission_in_mandate():
    assert ev(mandate=make_mandate(), action="mandates.delegate", account_id=None)["decision"] == "DENY"
    m = make_mandate(delegation={"allowed": True, "maximum_depth": 1}, prohibitions=[])
    assert ev(mandate=m, action="mandates.delegate", account_id=None)["decision"] == "ALLOW"


# ---- delegation attenuation


def child_of(parent, **over):
    c = copy.deepcopy(parent)
    c.update(mandate_id="mdt_c", mandatary={"agent_id": "agent_billpay_001", "operator_id": "organization_002", "client_id": "client_billpay_001"},
             lineage={"parent_mandate_id": parent["mandate_id"], "parent_mandate_version": 1, "depth": 1}, delegation={"allowed": False, "maximum_depth": 0})
    c.update(over)
    return c


def delegating_parent(**over):
    return make_mandate(delegation={"allowed": True, "maximum_depth": 1}, prohibitions=["transfers.external"], **over)


def test_child_equal_or_narrower_is_valid():
    p = delegating_parent()
    assert policy.attenuation_violations(p, child_of(p)) == []
    c = child_of(p)
    c["permissions"][1]["constraints"]["maximum_amount_minor"] = 20000
    assert policy.attenuation_violations(p, c) == []


@pytest.mark.parametrize("mutator,dimension", [
    (lambda c: c["permissions"][1]["constraints"].update(maximum_amount_minor=500000), "constraints"),
    (lambda c: c["permissions"][1]["constraints"].update(allowed_beneficiaries=["beneficiary_x"]), "constraints"),
    (lambda c: c["permissions"].append({"action": "transactions.read", "resources": ["account_001"], "constraints": {}}), "permitted_actions_or_resources"),
    (lambda c: c["permissions"][0].update(resources=["account_001", "account_002"]), "permitted_actions_or_resources"),
    (lambda c: c.update(prohibitions=[]), "prohibitions"),
    (lambda c: c["aggregate_constraints"].update(maximum_monthly_amount_minor=999999), "maximum_monthly_amount_minor"),
    (lambda c: c["validity"].update(expires_at="2999-01-01T00:00:00Z"), "temporal_validity"),
    (lambda c: c["obligations"].update(human_approval_above_minor=99999), "human_approval"),
    (lambda c: c.update(jurisdictions=["CA", "US"]), "geographic_restrictions"),
    (lambda c: c.update(delegation={"allowed": True, "maximum_depth": 1}), "delegation_depth"),
])
def test_child_cannot_expand_any_dimension(mutator, dimension):
    p = delegating_parent()
    c = child_of(p)
    mutator(c)
    v = policy.attenuation_violations(p, c)
    assert dimension in {x["dimension"] for x in v}


def test_delegation_not_allowed_and_cycle():
    p = make_mandate()
    assert "DELEGATION_NOT_ALLOWED" in {v["code"] for v in policy.attenuation_violations(p, child_of(p))}
    p = delegating_parent()
    cyc = child_of(p, mandatary=p["mandatary"])
    assert "DELEGATION_CYCLE" in {v["code"] for v in policy.attenuation_violations(p, cyc)}


def test_child_authority_is_intersection_with_parent_budget():
    p = delegating_parent()
    c = child_of(p)
    usage = {"mdt_t1": {"day_minor": 0, "month_minor": 49000, "month_count": 1}, "mdt_c": {"day_minor": 0, "month_minor": 0, "month_count": 0}}
    r = policy.evaluate(make_inputs(c, chain=(p,), amount=5000, usage=usage))
    assert "MONTHLY_LIMIT_EXCEEDED" in codes(r)  # parent budget consumed by child operations


def test_parent_revocation_makes_child_unusable():
    p = delegating_parent()
    c = child_of(p)
    i = make_inputs(c, chain=(p,))
    i["chain"][0]["status"] = "REVOKED"
    r = policy.evaluate(i)
    assert r["decision"] == "DENY" and "MANDATE_REVOKED" in codes(r)
