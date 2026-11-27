"""Financial action taxonomy.

The hierarchy exists for semantics and explanation. It is NOT an authorization inheritance
mechanism: authority is granted per exact action id (see policy.py). A grant of a parent group
never grants its children, and a child never implies another child.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    id: str  # canonical action identifier used in mandates and RAR
    cnl: str  # KYM-CNL verb
    cls: str  # ontology class local name
    group: str  # parent ontology class
    scope: str | None  # illustrative bank-defined OAuth scope
    label: str
    financial_execution: bool = False


GROUPS = {
    "ReadFinancialData": "FinancialAction",
    "AnalyzeFinancialData": "FinancialAction",
    "PrepareFinancialOperation": "FinancialAction",
    "ExecuteFinancialOperation": "FinancialAction",
    "ManageFinancialAuthority": "FinancialAction",
}

ACTIONS: list[Action] = [
    Action("accounts.read", "READ_ACCOUNT", "ReadAccount", "ReadFinancialData", "accounts.read", "Read account"),
    Action("balances.read", "READ_BALANCE", "ReadBalance", "ReadFinancialData", "balances.read", "Read balance"),
    Action("transactions.read", "READ_TRANSACTIONS", "ReadTransactions", "ReadFinancialData", "transactions.read", "Read transactions"),
    Action("accounts.owner.read", "READ_ACCOUNT_OWNER", "ReadAccountOwner", "ReadFinancialData", "accounts.read", "Read account owner"),
    Action("data.transmit_external", "TRANSMIT_DATA_EXTERNAL", "TransmitFinancialData", "ReadFinancialData", None, "Transmit financial data to another party"),
    Action("analysis.categorize", "CATEGORIZE_TRANSACTIONS", "CategorizeTransactions", "AnalyzeFinancialData", None, "Categorize transactions"),
    Action("analysis.cashflow", "ANALYZE_CASH_FLOW", "AnalyzeCashFlow", "AnalyzeFinancialData", None, "Analyze cash flow"),
    Action("analysis.budget", "GENERATE_BUDGET", "GenerateBudget", "AnalyzeFinancialData", None, "Generate budget"),
    Action("payments.prepare", "PREPARE_PAYMENT", "PreparePayment", "PrepareFinancialOperation", "payments.prepare", "Prepare payment"),
    Action("transfers.prepare", "PREPARE_TRANSFER", "PrepareTransfer", "PrepareFinancialOperation", "payments.prepare", "Prepare transfer"),
    Action("investments.prepare", "PREPARE_INVESTMENT_ORDER", "PrepareInvestmentOrder", "PrepareFinancialOperation", "payments.prepare", "Prepare investment order"),
    Action("payments.initiate", "INITIATE_PAYMENT", "InitiatePayment", "ExecuteFinancialOperation", "payments.initiate", "Initiate payment", True),
    Action("payments.pay_invoice", "PAY_INVOICE", "PayInvoice", "ExecuteFinancialOperation", "payments.initiate", "Pay invoice", True),
    Action("purchases.goods", "PURCHASE_GOODS", "PurchaseGoods", "ExecuteFinancialOperation", "payments.initiate", "Purchase goods", True),
    Action("transfers.execute", "EXECUTE_TRANSFER", "ExecuteTransfer", "ExecuteFinancialOperation", "transfers.initiate", "Execute internal transfer", True),
    Action("transfers.external", "EXTERNAL_TRANSFER", "ExecuteExternalTransfer", "ExecuteFinancialOperation", "transfers.initiate", "Execute external transfer", True),
    Action("investments.trade", "EXECUTE_INVESTMENT_ORDER", "ExecuteInvestmentOrder", "ExecuteFinancialOperation", "investments.trade", "Execute investment order", True),
    Action("mandates.request", "REQUEST_MANDATE", "RequestMandate", "ManageFinancialAuthority", None, "Request mandate"),
    Action("mandates.delegate", "DELEGATE", "RequestDelegation", "ManageFinancialAuthority", None, "Delegate authority"),
    Action("mandates.revoke", "REVOKE_MANDATE", "RevokeMandate", "ManageFinancialAuthority", None, "Revoke mandate"),
]

BY_ID = {a.id: a for a in ACTIONS}
BY_CNL = {a.cnl: a for a in ACTIONS}

PAYMENT_ACTIONS = {"payments.initiate", "payments.pay_invoice", "purchases.goods"}
TRANSFER_ACTIONS = {"transfers.execute", "transfers.external"}
MONEY_MOVING = {a.id for a in ACTIONS if a.financial_execution}
DATA_ACTIONS = {"accounts.read", "balances.read", "transactions.read", "accounts.owner.read"}

# Illustrative, bank-defined OAuth scopes. Scopes cannot express account, beneficiary, amount, purpose, etc.
SCOPES = ["accounts.read", "balances.read", "transactions.read", "payments.prepare", "payments.initiate", "transfers.initiate", "investments.trade"]

SCOPE_GAPS = [
    ("Exact financial account", "RAR: accounts"),
    ("Permitted beneficiary", "RAR: beneficiaries"),
    ("Maximum transaction value", "RAR: maximum_amount"),
    ("Cumulative spending limit", "Mandate aggregate_constraints (server-side state)"),
    ("Authorized purpose", "Mandate purpose"),
    ("Recurring schedule / calendar budget", "Mandate validity.budget_timezone"),
    ("Delegation depth", "Mandate delegation"),
    ("Required human approval", "Mandate obligations"),
    ("Mandate revocation state", "Authoritative mandate state, checked per request"),
]


def scope_for(action_id: str) -> str | None:
    return BY_ID[action_id].scope


def is_known(action_id: str) -> bool:
    return action_id in BY_ID


def explicit_implications() -> dict[str, set[str]]:
    """Inheritance must be explicitly defined by policy. This bank policy defines none."""
    return {}
