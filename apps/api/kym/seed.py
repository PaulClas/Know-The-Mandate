"""Synthetic demo data: customers, accounts, beneficiaries, transaction history and agents. ALL DATA IS FICTIONAL."""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select

from . import agents as ag
from . import clock, config, db, ledger

BUILD = lambda n: "sha256:" + (f"{n:02x}" * 32)  # noqa: E731

CUSTOMERS = [
    ("customer_001", "individual", "Alice Tremblay", "CA-QC", "customer.alice", "fr"),
    ("customer_002", "individual", "Ben Carter", "US", "customer.ben", "en"),
    ("customer_003", "individual", "Priya Nair", "CA", "customer.priya", "en"),
    ("customer_004", "individual", "Jordan Lee", "CA", "customer.jordan", "en"),
    ("customer_005", "individual", "Sam Ortiz", "CA", "customer.sam", "en"),
    ("business_001", "business", "Northwind Supply Inc.", "CA", "customer.northwind", "en"),
]

ACCOUNTS = [
    ("account_001", "customer_001", "Alice Chequing", "chequing", "CAD", 425000, "account.chequing-001"),
    ("account_002", "customer_001", "Alice Savings", "savings", "CAD", 1280000, "account.savings-001"),
    ("account_003", "customer_002", "Ben Chequing", "chequing", "USD", 300000, "account.chequing-ben"),
    ("account_101", "business_001", "Northwind Operating", "business_operating", "CAD", 8500000, "account.northwind-operating"),
    ("gl_settlement_CAD", None, "Payee settlement (CAD)", "gl", "CAD", 0, ""),
    ("gl_settlement_USD", None, "Payee settlement (USD)", "gl", "USD", 0, ""),
]

PAYEES = [
    ("beneficiary_hydro_quebec", "beneficiary", "Hydro-Québec (synthetic)", "CA", "4900", "beneficiary.hydro-quebec", False),
    ("beneficiary_videotron", "beneficiary", "Vidéotron (synthetic)", "CA", "4814", "beneficiary.videotron", False),
    ("beneficiary_city_taxes", "beneficiary", "City Property Tax Office (synthetic)", "CA", "9311", "beneficiary.city-taxes", False),
    ("beneficiary_new_supplier", "beneficiary", "Meridian Overseas Supplies Pte (synthetic)", "SG", "5085", "beneficiary.new-supplier", False),
    ("beneficiary_watchlisted", "beneficiary", "Synthetic Watchlisted Trading Co (synthetic)", "ZZ", "5999", "beneficiary.watchlisted", True),
    ("beneficiary_acme_supplies", "beneficiary", "Acme Industrial Supplies (synthetic)", "CA", "5085", "beneficiary.acme-supplies", False),
    ("beneficiary_beta_logistics", "beneficiary", "Beta Logistics Ltd (synthetic)", "CA", "4214", "beneficiary.beta-logistics", False),
    ("merchant_grocery_001", "merchant", "Marché Local Grocery (synthetic)", "CA", "5411", "merchant.grocery-001", False),
    ("merchant_electronics_001", "merchant", "Northern Electronics (synthetic)", "CA", "5732", "merchant.electronics-001", False),
    ("merchant_gadget_online", "merchant", "Gadget Online Store (synthetic)", "CA", "5999", "merchant.gadget-online", False),
]

OPERATORS = {
    "organization_001": "Aster Labs Inc.",
    "organization_002": "BillBot Technologies Ltd.",
    "organization_003": "ShopMate Inc.",
    "organization_004": "LedgerLoop Corp.",
    "organization_005": "Unknown Operator Collective",
}

ALL_READ = ["accounts.read", "balances.read", "transactions.read"]


def _agent(aid, name, category, org, caps, level, tools, posture, status="VERIFIED", n=1, env="cloud-sandbox"):
    return {
        "id": aid, "status": status,
        "declared": {
            "display_name": name, "category": category, "operating_organization": OPERATORS[org], "operator_id": org,
            "responsible_party": f"{OPERATORS[org]} (legal entity, synthetic)", "developer": f"{OPERATORS[org]} Engineering",
            "deployment_environment": env, "model_provider": "SyntheticLM Labs (fictional)", "model_id": "synthetic-lm-1",
            "software_version": f"1.{n}.0", "build_digest": BUILD(n), "supported_tools": tools, "requested_capabilities": caps,
            "declared_autonomy_level": level,
        },
        "posture": posture,
    }


GOOD = {"mfa_on_operator_console": True, "secrets_in_kms": True, "prompt_injection_testing": True, "sbom_published": True}
MIXED = {"mfa_on_operator_console": True, "secrets_in_kms": False, "prompt_injection_testing": True, "sbom_published": False}
POOR = {"mfa_on_operator_console": False, "secrets_in_kms": False, "prompt_injection_testing": False, "sbom_published": False}

AGENTS = [
    (_agent("agent_finance_001", "Personal Finance Assistant", "personal_finance", "organization_001",
            [*ALL_READ, "analysis.categorize", "analysis.cashflow", "analysis.budget", "payments.prepare", "payments.initiate", "payments.pay_invoice", "transfers.execute", "transfers.external", "mandates.delegate"],
            "supervised", ["get_accounts", "get_balance", "get_transactions", "propose_payment", "initiate_payment", "request_delegation"], GOOD, n=1), "agent.finance-assistant", {"payments_executed": 240, "payments_denied": 3, "mandates_executed": 31}),
    (_agent("agent_billpay_001", "Household Bill Payment Agent", "bill_payment", "organization_002",
            ["balances.read", "payments.prepare", "payments.initiate", "payments.pay_invoice", "mandates.request"],
            "conditional", ["get_balance", "propose_payment", "initiate_payment", "request_human_approval"], GOOD, n=2), "agent.billpay", {"payments_executed": 410, "payments_denied": 5, "mandates_executed": 52}),
    (_agent("agent_shopping_001", "Shopping Agent", "commerce", "organization_003",
            ["balances.read", "purchases.goods", "payments.prepare", "payments.initiate"], "conditional",
            ["get_balance", "propose_payment", "initiate_payment"], MIXED, n=3), "agent.shopping", {"payments_executed": 95, "payments_denied": 14, "mandates_executed": 12}),
    (_agent("agent_savings_001", "Savings Optimization Agent", "savings", "organization_001",
            [*ALL_READ, "analysis.cashflow", "transfers.prepare", "transfers.execute", "transfers.external"], "supervised",
            ["get_accounts", "get_balance", "get_transactions", "propose_payment", "initiate_payment"], GOOD, n=4), "agent.savings", {"payments_executed": 60, "payments_denied": 1, "mandates_executed": 9}),
    (_agent("agent_treasury_001", "Business Treasury Agent", "treasury", "organization_004",
            [*ALL_READ, "payments.prepare", "payments.initiate", "payments.pay_invoice"], "supervised",
            ["get_accounts", "get_balance", "get_transactions", "propose_payment", "initiate_payment", "request_human_approval"], GOOD, n=5), "agent.treasury", {"payments_executed": 120, "payments_denied": 2, "mandates_executed": 14}),
    (_agent("agent_unverified_001", "External Unverified Agent", "external", "organization_005",
            ["balances.read", "payments.initiate", "payments.pay_invoice", "transfers.external"], "autonomous",
            ["get_balance", "initiate_payment"], POOR, status="PENDING_VERIFICATION", n=6, env="unknown"), "agent.unverified", {"payments_executed": 0, "payments_denied": 0, "mandates_executed": 0}),
]


def is_seeded(s) -> bool:
    return s.execute(select(db.Customer).limit(1)).first() is not None


def seed(s) -> None:
    if is_seeded(s):
        return
    now = clock.now()
    for cid, typ, name, jur, ref, lang in CUSTOMERS:
        s.add(db.Customer(id=cid, type=typ, name=name, jurisdiction=jur, kyc_status="VERIFIED", kyc_date=clock.iso(now - timedelta(days=200)),
                          kyc_evidence_ref=f"kyc-evidence/{cid}.synthetic", risk_class="LOW", restrictions=[], cnl_ref=ref, preferred_language=lang))
    s.add_all([
        db.Representative(business_id="business_001", person_id="customer_003", role="Finance Director", can_sign=True, account_ids=["account_101"]),
        db.Representative(business_id="business_001", person_id="customer_004", role="Chief Executive Officer", can_sign=True, account_ids=["account_101"]),
        db.Representative(business_id="business_001", person_id="customer_005", role="Treasury Analyst (no signing authority)", can_sign=False, account_ids=["account_101"]),
    ])
    for aid, owner, name, typ, ccy, bal, ref in ACCOUNTS:
        s.add(db.Account(id=aid, owner_id=owner, name=name, type=typ, currency=ccy, balance_minor=bal, reserved_minor=0, status="OPEN", restrictions=[], cnl_ref=ref))
    for pid, kind, name, country, cat, ref, wl in PAYEES:
        s.add(db.Payee(id=pid, kind=kind, name=name, country=country, category=cat, cnl_ref=ref, watchlist=wl))
    rng = random.Random(42)
    n = 0

    def hist(account, days_ago, desc, amt, cat, payee=None):
        nonlocal n
        n += 1
        s.add(db.HistoryEntry(id=f"h_{n:04d}", account_id=account, posted_at=clock.iso(now - timedelta(days=days_ago)), description=desc, amount_minor=amt,
                              currency="CAD", category=cat, payee_id=payee))

    for m in range(3):
        hist("account_001", 5 + 30 * m, "Hydro-Québec", -rng.randint(7800, 9800), "utilities", "beneficiary_hydro_quebec")
        hist("account_001", 12 + 30 * m, "Vidéotron", -7499, "telecom", "beneficiary_videotron")
    for d in range(2, 90, 6):
        hist("account_001", d, "Marché Local Grocery", -rng.randint(4200, 14500), "groceries", "merchant_grocery_001")
    for d in range(0, 90, 14):
        hist("account_001", d + 1, "Payroll deposit", 320000, "income")
    for d in range(3, 80, 17):
        hist("account_002", d, "Interest", rng.randint(900, 1300), "interest")
    for d in range(1, 90, 9):
        hist("account_101", d, "Acme Industrial Supplies", -rng.randint(180000, 520000), "suppliers", "beneficiary_acme_supplies")
    for d in range(4, 90, 30):
        hist("account_101", d, "Customer receipts", rng.randint(1500000, 2500000), "income")
    s.flush()
    for cid, *_ in CUSTOMERS:
        ledger.append(s, "CUSTOMER_VERIFIED", actor_id="meridian-kyc-sim", actor_type="bank_system", principal_id=cid,
                      payload={"kyc_evidence_ref": f"kyc-evidence/{cid}.synthetic", "note": "simulated KYC; not real customer due diligence"})
    for spec, ref, stats in AGENTS:
        a = spec
        ag.register(s, a["declared"], actor_id="admin_001", agent_id=a["id"], cnl_ref=ref)
        row = s.get(db.Agent, a["id"])
        row.security_posture = a["posture"]
        row.stats = stats
        if a["status"] == "VERIFIED":
            ag.verify(s, a["id"], actor_id="admin_001")
    s.get(db.Agent, "agent_savings_001").incidents = [{"at": clock.iso(now - timedelta(days=40)), "description": "Retry storm against payments API (synthetic)", "severity": "LOW"}]
    s.get(db.Agent, "agent_shopping_001").incidents = [{"at": clock.iso(now - timedelta(days=12)), "description": "Operator credential rotated after exposure (synthetic)", "severity": "MEDIUM"}]
    ledger.create_checkpoint(s)


def reset_files() -> None:
    db.dispose()
    for p in config.DATA_DIR.glob("kym.db*"):
        p.unlink()
    cp = config.DATA_DIR / "checkpoints"
    if cp.exists():
        for f in cp.glob("*.json"):
            f.unlink()
    exp = config.DATA_DIR / "exports"
    if exp.exists():
        for f in exp.glob("*"):
            f.unlink()
