"""Property-based tests of authorization invariants (Hypothesis)."""
import copy

from helpers import make_inputs, make_mandate, mutate
from hypothesis import given, settings
from hypothesis import strategies as st

from kym import policy

BENS = ["beneficiary_hydro_quebec", "beneficiary_videotron", "beneficiary_acme"]
ACTIONS = ["balances.read", "payments.initiate"]


@st.composite
def mandates(draw):
    mx = draw(st.integers(1000, 100000))
    bens = draw(st.lists(st.sampled_from(BENS), min_size=1, max_size=3, unique=True))
    monthly = draw(st.integers(mx, 500000))
    daily = draw(st.integers(mx, monthly))
    thr = draw(st.integers(0, mx))
    return make_mandate(
        permissions=[{"action": "balances.read", "resources": ["account_001"]}, {"action": "payments.initiate", "resources": ["account_001"], "constraints": {"currency": "CAD", "maximum_amount_minor": mx, "allowed_beneficiaries": bens}}],
        aggregate_constraints={"maximum_daily_amount_minor": daily, "maximum_monthly_amount_minor": monthly}, obligations={"human_approval_above_minor": thr, "required_approvals": 1, "notify_customer": True})


@st.composite
def requests(draw):
    return {"amount": draw(st.integers(1, 150000)), "beneficiary": draw(st.sampled_from(BENS + ["beneficiary_zzz"])), "action": draw(st.sampled_from(ACTIONS)),
            "used": draw(st.integers(0, 400000))}


def decide(m, r, chain=(), approved=False):
    usage = {m["mandate_id"]: {"day_minor": 0, "month_minor": r["used"], "month_count": 0}}
    for c in chain:
        usage[c["mandate_id"]] = {"day_minor": 0, "month_minor": r["used"], "month_count": 0}
    appr = {"supplied": True, "valid": True, "granted_count": 1, "problem": None} if approved else None
    return policy.evaluate(make_inputs(m, chain=chain, action=r["action"], amount=r["amount"], beneficiary=r["beneficiary"], usage=usage, approval=appr))["decision"]


@given(mandates(), requests(), st.data())
@settings(max_examples=150, deadline=None)
def test_narrowing_an_authority_cannot_create_a_new_permission(m, r, data):
    narrowed = copy.deepcopy(m)
    kind = data.draw(st.sampled_from(["lower_max", "drop_beneficiary", "drop_permission", "lower_monthly"]))
    pay = narrowed["permissions"][1]["constraints"]
    if kind == "lower_max":
        pay["maximum_amount_minor"] = max(1, pay["maximum_amount_minor"] // 2)
    elif kind == "drop_beneficiary" and len(pay["allowed_beneficiaries"]) > 1:
        pay["allowed_beneficiaries"] = pay["allowed_beneficiaries"][:-1]
    elif kind == "drop_permission":
        narrowed["permissions"] = narrowed["permissions"][:1]
    elif kind == "lower_monthly":
        narrowed["aggregate_constraints"]["maximum_monthly_amount_minor"] = max(narrowed["aggregate_constraints"]["maximum_daily_amount_minor"], narrowed["aggregate_constraints"]["maximum_monthly_amount_minor"] // 2)
    if decide(narrowed, r, approved=True) == "ALLOW":
        assert decide(m, r, approved=True) == "ALLOW"


@given(mandates(), mandates(), requests())
@settings(max_examples=200, deadline=None)
def test_child_that_passes_attenuation_never_exceeds_its_parent(p, c, r):
    p["delegation"] = {"allowed": True, "maximum_depth": 1}
    p["prohibitions"] = []
    c = copy.deepcopy(c)
    c.update(mandate_id="mdt_c", mandatary={"agent_id": "agent_billpay_001", "operator_id": "organization_002", "client_id": "client_billpay_001"},
             lineage={"parent_mandate_id": p["mandate_id"], "parent_mandate_version": 1, "depth": 1}, delegation={"allowed": False, "maximum_depth": 0}, prohibitions=[])
    c["validity"], c["currency"], c["purpose"], c["jurisdictions"] = p["validity"], p["currency"], p["purpose"], p["jurisdictions"]
    if policy.attenuation_violations(p, c):
        return
    child_decision = decide(c, r, chain=(p,), approved=True)
    if child_decision == "ALLOW":
        assert decide(p, r, approved=True) == "ALLOW"


@given(mandates(), requests(), st.sampled_from(["REVOKED", "EXPIRED", "SUSPENDED", "SUPERSEDED"]))
@settings(max_examples=100, deadline=None)
def test_revoked_or_inactive_mandate_never_allows(m, r, status):
    i = make_inputs(m, action=r["action"], amount=r["amount"], beneficiary=r["beneficiary"], status=status, approval={"supplied": True, "valid": True, "granted_count": 1, "problem": None})
    assert policy.evaluate(i)["decision"] == "DENY"


@given(mandates(), st.lists(st.integers(100, 60000), min_size=1, max_size=25))
@settings(max_examples=100, deadline=None)
def test_cumulative_allowed_spend_never_exceeds_limits(m, amounts):
    used = 0
    for a in amounts:
        usage = {m["mandate_id"]: {"day_minor": used, "month_minor": used, "month_count": 0}}
        d = policy.evaluate(make_inputs(m, amount=a, usage=usage, approval={"supplied": True, "valid": True, "granted_count": 1, "problem": None}))["decision"]
        if d == "ALLOW":
            used += a
    limit = min(m["aggregate_constraints"]["maximum_daily_amount_minor"], m["aggregate_constraints"]["maximum_monthly_amount_minor"])
    assert used <= limit


@given(mandates(), requests(), st.integers(0, 100), st.integers(0, 100))
@settings(max_examples=100, deadline=None)
def test_explicit_prohibition_cannot_be_overridden_by_trust_or_low_risk(m, r, trust, risk):
    m = copy.deepcopy(m)
    m["permissions"] = [p for p in m["permissions"] if p["action"] != "payments.initiate"] or m["permissions"]
    m["prohibitions"] = ["payments.initiate"]
    i = make_inputs(m, amount=r["amount"], beneficiary=r["beneficiary"], risk_score=min(risk, 59))
    i = mutate(i, "agent.trust_score", trust)  # extra field is ignored by the PDP by design
    assert policy.evaluate(i)["decision"] == "DENY"
