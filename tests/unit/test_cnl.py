import pytest
from helpers import ts

from kym import cnl, money

R = cnl.Resolver(
    accounts={"account.chequing-001": {"id": "account_001", "owner_id": "customer_001", "currency": "CAD"}},
    payees={"beneficiary.hydro-quebec": {"id": "beneficiary_hydro_quebec", "kind": "beneficiary", "category": "4900", "country": "CA"}},
    agents={"agent.finance-assistant": {"id": "agent_finance_001", "client_id": "client_finance_001", "operator_id": "organization_001"}},
    customers={"customer_001": {"type": "individual", "jurisdiction": "CA-QC", "name": "Alice"}},
)
EXPIRE = ts(30)
T1 = f"""PERMIT agent.finance-assistant TO READ_BALANCE
ON account.chequing-001.
PERMIT agent.finance-assistant TO PAY_INVOICE FROM account.chequing-001 TO beneficiary.hydro-quebec WITH MAX_AMOUNT 250 CAD PER TRANSACTION.
LIMIT TOTAL_PAYMENTS TO 500 CAD PER CALENDAR_MONTH.
REQUIRE HUMAN_APPROVAL FOR PAYMENTS ABOVE 100 CAD.
PROHIBIT EXTERNAL_TRANSFER.
PROHIBIT DELEGATION.
PURPOSE household_bill_management.
EXPIRE AT {EXPIRE}."""
T2 = f"""PURPOSE household_bill_management. EXPIRE AT {EXPIRE}. FORBID DELEGATION. FORBID EXTERNAL_TRANSFER.
REQUIRE HUMAN_APPROVAL FOR PAYMENTS ABOVE CAD 100.00.
LIMIT TOTAL_PAYMENTS TO CAD 500 PER CALENDAR_MONTH.
ALLOW agent.finance-assistant TO PAY_INVOICE FROM account.chequing-001 WITH MAX_AMOUNT CAD 250.00 PER TRANSACTION TO beneficiary.hydro-quebec.
ALLOW agent.finance-assistant TO READ_BALANCE ON account.chequing-001."""


def compile_(text):
    return cnl.compile_cnl(text, "customer_001", R, default_not_before=ts(-1))


def test_valid_mandate_compilation():
    r = compile_(T1)
    assert r["ok"], r["errors"]
    m = r["mandate"]
    assert m["permissions"][1]["constraints"]["maximum_amount_minor"] == 25000
    assert m["aggregate_constraints"]["maximum_monthly_amount_minor"] == 50000
    assert m["obligations"]["human_approval_above_minor"] == 10000
    assert m["delegation"] == {"allowed": False, "maximum_depth": 0}
    assert "mandates.delegate" in m["prohibitions"] and "transfers.external" in m["prohibitions"]


def test_equivalent_phrasings_compile_to_identical_policy():
    a, b = compile_(T1), compile_(T2)
    assert a["ok"] and b["ok"]
    assert a["canonical_digest"] == b["canonical_digest"]
    assert a["normalized_cnl"] == b["normalized_cnl"]


def test_compilation_is_deterministic():
    assert compile_(T1)["canonical_digest"] == compile_(T1)["canonical_digest"]


@pytest.mark.parametrize("missing,code", [("PURPOSE household_bill_management.", "MISSING_PURPOSE"), (f"EXPIRE AT {EXPIRE}.", "MISSING_EXPIRY"), ("WITH MAX_AMOUNT 250 CAD PER TRANSACTION", "MISSING_CONSTRAINT"), ("TO beneficiary.hydro-quebec ", "MISSING_COUNTERPARTY")])
def test_missing_constraints_are_rejected_not_invented(missing, code):
    r = compile_(T1.replace(missing, ""))
    assert not r["ok"]
    assert code in {e["code"] for e in r["errors"]}


def test_unknown_references_and_actions_rejected():
    assert "UNRESOLVED_REFERENCE" in {e["code"] for e in compile_(T1.replace("account.chequing-001", "account.nope", 1))["errors"]}
    assert "UNKNOWN_ACTION" in {e["code"] for e in compile_(T1.replace("READ_BALANCE", "READ_EVERYTHING"))["errors"]}


def test_syntax_error_has_position():
    r = compile_("PERMIT agent.finance-assistant READ.")
    assert r["errors"][0]["code"] == "SYNTAX_ERROR" and r["errors"][0]["line"] == 1


def test_permission_prohibition_conflict_rejected():
    assert "PERMISSION_PROHIBITION_CONFLICT" in {e["code"] for e in compile_(T1 + "\nPROHIBIT READ_BALANCE.")["errors"]}


def test_ambiguous_instruction_detected_and_nothing_compiled():
    text = "Manage my money, pay my usual bills and move some savings whenever it makes sense. Do not spend too much."
    kinds = {a["kind"] for a in cnl.detect_ambiguities(text)}
    assert {"accounts", "bills", "usual", "amount", "frequency", "excessive"} <= kinds
    with pytest.raises(ValueError):
        cnl.propose_cnl({"agent": "agent.x"}, R)


def test_money_is_exact_integer_minor_units():
    assert money.parse_major("250", "CAD") == 25000
    assert money.parse_major("0.10", "CAD") == 10
    assert money.parse_major("1000", "JPY") == 1000
    with pytest.raises(money.MoneyError):
        money.parse_major("1.005", "CAD")
    for bad in (1.5, "100", True, -1):
        with pytest.raises(money.MoneyError):
            money.require_minor(bad)
