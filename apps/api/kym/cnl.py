"""KYM-CNL: controlled language parser, ambiguity detection, deterministic compiler and normalizer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from lark import Lark, Token, Transformer, UnexpectedInput
from pydantic import ValidationError

from . import canon, config, money, taxonomy
from .schemas import Mandate

GRAMMAR_PATH = config.PACKAGES / "controlled-language" / "kym-cnl.lark"
_parser: Lark | None = None


def parser() -> Lark:
    global _parser
    if _parser is None:
        _parser = Lark(Path(GRAMMAR_PATH).read_text(), parser="lalr", start="start", propagate_positions=True)
    return _parser


# --------------------------------------------------------------------------- AST


class _ToAst(Transformer):
    def start(self, items):
        return items

    def statement(self, items):
        return items[0]

    def ref_list(self, items):
        return [str(i) for i in items]

    def money(self, items):
        a = [str(i) for i in items]
        num, ccy = (a[0], a[1]) if a[0][0].isdigit() else (a[1], a[0])
        return {"amount": num, "currency": ccy}

    def limit_value(self, items):
        return items[0] if isinstance(items[0], dict) else {"count": str(items[0])}

    def on_clause(self, items):
        return ("ON", items[0])

    def from_clause(self, items):
        return ("FROM", items[0])

    def to_clause(self, items):
        return ("TO", items[0])

    def max_clause(self, items):
        return ("MAX", items[0])

    def permit(self, items):
        _, subject, verb, *clauses = items
        return {"type": "PERMIT", "agent": str(subject), "verb": str(verb), "clauses": [list(c) for c in clauses]}

    def prohibit(self, items):
        return {"type": "PROHIBIT", "verb": str(items[1])}

    def limit(self, items):
        return {"type": "LIMIT", "kind": str(items[0]), "value": items[1], "period": str(items[2])}

    def require(self, items):
        count = None
        rest = items
        if isinstance(items[0], Token) and items[0].type == "NUMBER":
            count, rest = str(items[0]), items[1:]
        return {"type": "REQUIRE", "approvals": count, "above": rest[-1]}

    def allow_delegation(self, items):
        return {"type": "ALLOW_DELEGATION", "depth": str(items[-1])}

    def start_at(self, items):
        return {"type": "START", "at": str(items[0])}

    def expire_at(self, items):
        return {"type": "EXPIRE", "at": str(items[0])}

    def purpose(self, items):
        return {"type": "PURPOSE", "id": str(items[0])}

    def jurisdiction(self, items):
        return {"type": "JURISDICTION", "codes": [str(i) for i in items]}

    def timezone(self, items):
        return {"type": "TIMEZONE", "tz": str(items[0])}


def parse(text: str) -> list[dict]:
    return _ToAst().transform(parser().parse(text))


def _friendly_error(e: UnexpectedInput, text: str) -> dict:
    expected = sorted(getattr(e, "expected", None) or getattr(e, "allowed", None) or [])
    return {
        "code": "SYNTAX_ERROR",
        "message": f"Unexpected input at line {e.line}, column {e.column}.",
        "line": e.line,
        "column": e.column,
        "context": e.get_context(text, span=30).strip(),
        "expected": expected[:12],
    }


# --------------------------------------------------------------------------- resolver


@dataclass
class Resolver:
    accounts: dict[str, dict] = field(default_factory=dict)  # cnl_ref -> {id, owner_id, currency}
    payees: dict[str, dict] = field(default_factory=dict)
    agents: dict[str, dict] = field(default_factory=dict)  # cnl_ref -> {id, client_id, operator_id}
    customers: dict[str, dict] = field(default_factory=dict)  # id -> {type, jurisdiction}

    @classmethod
    def from_session(cls, s) -> Resolver:
        from sqlalchemy import select

        from . import db

        r = cls()
        for a in s.execute(select(db.Account).where(db.Account.owner_id.is_not(None))).scalars():
            r.accounts[a.cnl_ref] = {"id": a.id, "owner_id": a.owner_id, "currency": a.currency}
        for p in s.execute(select(db.Payee)).scalars():
            r.payees[p.cnl_ref] = {"id": p.id, "kind": p.kind, "category": p.category, "country": p.country}
        for ag in s.execute(select(db.Agent)).scalars():
            r.agents[ag.cnl_ref] = {"id": ag.id, "client_id": ag.client_id, "operator_id": ag.declared.get("operator_id", "")}
        for c in s.execute(select(db.Customer)).scalars():
            r.customers[c.id] = {"type": c.type, "jurisdiction": c.jurisdiction, "name": c.name}
        return r

    def ref_of(self, kind: str, ident: str) -> str:
        table = {"account": self.accounts, "payee": self.payees, "agent": self.agents}[kind]
        for ref, v in table.items():
            if v["id"] == ident:
                return ref
        return ident


# --------------------------------------------------------------------------- compile


def _err(errors, code, message, **extra):
    errors.append({"code": code, "message": message, **extra})


def _money(m: dict, errors, ctx: str):
    try:
        return money.parse_major(m["amount"], m["currency"]), m["currency"]
    except money.MoneyError as e:
        _err(errors, "INVALID_AMOUNT", f"{ctx}: {e}")
        return None, m["currency"]


def _ts(v: str, errors, ctx: str):
    try:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v
    except ValueError:
        _err(errors, "INVALID_TIMESTAMP", f"{ctx}: {v!r} is not a valid UTC timestamp")
        return None


def compile_cnl(text: str, principal_id: str, resolver: Resolver, *, default_not_before: str,
                mandate_id: str = "mdt_DRAFT", policy_version: str = config.POLICY_VERSION) -> dict:
    errors: list[dict] = []
    result: dict = {"ok": False, "errors": errors, "ast": None, "mandate": None, "normalized_cnl": None, "canonical_digest": None}
    try:
        ast = parse(text)
    except UnexpectedInput as e:
        errors.append(_friendly_error(e, text))
        return result
    result["ast"] = ast
    cust = resolver.customers.get(principal_id)
    if not cust:
        _err(errors, "UNKNOWN_PRINCIPAL", f"Unknown customer {principal_id}")
        return result

    agent_refs: set[str] = set()
    permissions: dict[str, dict] = {}
    prohibitions: set[str] = set()
    agg: dict = {}
    obligations: dict = {}
    delegation = {"allowed": False, "maximum_depth": 0}
    purpose = start = expire = tz = None
    jurisdictions: list[str] | None = None
    currencies: set[str] = set()
    seen_single: set[str] = set()

    def once(kind: str):
        if kind in seen_single:
            _err(errors, "DUPLICATE_STATEMENT", f"{kind} may appear only once")
        seen_single.add(kind)

    for st in ast:
        t = st["type"]
        if t == "PERMIT":
            action = taxonomy.BY_CNL.get(st["verb"])
            if not action:
                _err(errors, "UNKNOWN_ACTION", f"Unknown action {st['verb']}. Allowed: {', '.join(sorted(taxonomy.BY_CNL))}")
                continue
            ag = resolver.agents.get(st["agent"])
            agent_refs.add(st["agent"])
            if not ag:
                _err(errors, "UNRESOLVED_REFERENCE", f"Agent {st['agent']} is not in the agent registry")
            on: list[str] = []
            frm: list[str] = []
            to: list[str] = []
            maxamt = None
            for kind, val in st["clauses"]:
                if kind == "ON":
                    on += val
                elif kind == "FROM":
                    frm += val
                elif kind == "TO":
                    to += val
                elif kind == "MAX":
                    maxamt = val
            money_moving = action.financial_execution
            if money_moving and on:
                _err(errors, "WRONG_CLAUSE", f"{action.cnl} moves money: use FROM <account>, not ON")
            if not money_moving and (frm or to or maxamt):
                _err(errors, "WRONG_CLAUSE", f"{action.cnl} does not move money: use ON <account> only")
            res_refs = frm if money_moving else on
            if not res_refs:
                _err(errors, "MISSING_RESOURCE", f"{action.cnl} needs an explicit account ({'FROM' if money_moving else 'ON'} account.<name>)")
            ids = []
            for ref in res_refs:
                a = resolver.accounts.get(ref)
                if not a:
                    _err(errors, "UNRESOLVED_REFERENCE", f"{ref} is not a known account")
                    continue
                ids.append(a["id"])
            cons: dict = {}
            if money_moving:
                if maxamt is None:
                    _err(errors, "MISSING_CONSTRAINT", f"{action.cnl} needs WITH MAX_AMOUNT <amount> <currency> PER TRANSACTION")
                else:
                    amt, ccy = _money(maxamt, errors, "MAX_AMOUNT")
                    currencies.add(ccy)
                    if amt is not None:
                        cons["maximum_amount_minor"] = amt
                        cons["currency"] = ccy
                if not to:
                    _err(errors, "MISSING_COUNTERPARTY", f"{action.cnl} needs an explicit TO beneficiary, merchant, category or account")
                for ref in to:
                    kind, _, name = ref.partition(".")
                    if kind in ("beneficiary", "merchant"):
                        p = resolver.payees.get(ref)
                        if not p or p["kind"] != kind:
                            _err(errors, "UNRESOLVED_REFERENCE", f"{ref} is not a known {kind}")
                        else:
                            cons.setdefault("allowed_beneficiaries" if kind == "beneficiary" else "allowed_merchants", []).append(p["id"])
                    elif kind == "category":
                        cons.setdefault("allowed_merchant_categories", []).append(name)
                    elif kind == "country":
                        cons.setdefault("allowed_countries", []).append(name.upper())
                    elif kind == "account":
                        a = resolver.accounts.get(ref)
                        if not a:
                            _err(errors, "UNRESOLVED_REFERENCE", f"{ref} is not a known account")
                        elif action.id != "transfers.execute":
                            _err(errors, "WRONG_CLAUSE", "Destination accounts are only valid for EXECUTE_TRANSFER")
                        else:
                            cons.setdefault("allowed_destination_accounts", []).append(a["id"])
                    else:
                        _err(errors, "UNRESOLVED_REFERENCE", f"{ref} is not a valid counterparty reference")
                if action.id == "transfers.execute" and "allowed_destination_accounts" not in cons and "allowed_beneficiaries" not in cons:
                    _err(errors, "MISSING_COUNTERPARTY", "EXECUTE_TRANSFER needs TO account.<own account>")
                for k in ("allowed_beneficiaries", "allowed_merchants", "allowed_merchant_categories", "allowed_countries", "allowed_destination_accounts"):
                    if k in cons:
                        cons[k] = sorted(set(cons[k]))
            key = canon.digest({"a": action.id, "r": sorted(ids), "c": cons})
            permissions[key] = {"action": action.id, "resources": sorted(set(ids)), "constraints": cons}
        elif t == "PROHIBIT":
            if st["verb"] == "DELEGATION":
                prohibitions.add("mandates.delegate")
                delegation = {"allowed": False, "maximum_depth": 0}
                seen_single.add("DELEGATION")
            else:
                a = taxonomy.BY_CNL.get(st["verb"])
                if not a:
                    _err(errors, "UNKNOWN_ACTION", f"Unknown action {st['verb']}")
                else:
                    prohibitions.add(a.id)
        elif t == "LIMIT":
            if st["kind"] == "TOTAL_PAYMENTS":
                if "count" in st["value"]:
                    _err(errors, "INVALID_AMOUNT", "TOTAL_PAYMENTS needs an amount and currency")
                    continue
                amt, ccy = _money(st["value"], errors, "LIMIT")
                currencies.add(ccy)
                key = "maximum_monthly_amount_minor" if st["period"] == "CALENDAR_MONTH" else "maximum_daily_amount_minor"
                once(key)
                if amt is not None:
                    agg[key] = amt
            else:
                if "count" not in st["value"] or "." in st["value"]["count"]:
                    _err(errors, "INVALID_AMOUNT", "PAYMENT_COUNT needs a whole number")
                    continue
                if st["period"] != "CALENDAR_MONTH":
                    _err(errors, "UNSUPPORTED", "PAYMENT_COUNT is supported per CALENDAR_MONTH only")
                    continue
                once("count")
                agg["maximum_transaction_count_monthly"] = int(st["value"]["count"])
        elif t == "REQUIRE":
            once("REQUIRE")
            amt, ccy = _money(st["above"], errors, "REQUIRE")
            currencies.add(ccy)
            if amt is not None:
                obligations["human_approval_above_minor"] = amt
            n = st["approvals"]
            if n is not None:
                if "." in n or int(n) < 1 or int(n) > 5:
                    _err(errors, "INVALID_AMOUNT", "approval count must be a whole number from 1 to 5")
                else:
                    obligations["required_approvals"] = int(n)
        elif t == "ALLOW_DELEGATION":
            once("DELEGATION")
            if "." in st["depth"] or int(st["depth"]) < 1:
                _err(errors, "INVALID_AMOUNT", "delegation depth must be a whole number of at least 1")
            else:
                delegation = {"allowed": True, "maximum_depth": int(st["depth"])}
        elif t == "START":
            once("START")
            start = _ts(st["at"], errors, "START AT")
        elif t == "EXPIRE":
            once("EXPIRE")
            expire = _ts(st["at"], errors, "EXPIRE AT")
        elif t == "PURPOSE":
            once("PURPOSE")
            purpose = st["id"]
        elif t == "JURISDICTION":
            once("JURISDICTION")
            jurisdictions = sorted(set(st["codes"]))
        elif t == "TIMEZONE":
            once("TIMEZONE")
            tz = st["tz"]

    if len(agent_refs) > 1:
        _err(errors, "MULTIPLE_AGENTS", f"A mandate has exactly one mandatary; found {sorted(agent_refs)}")
    if not agent_refs:
        _err(errors, "MISSING_AGENT", "No PERMIT statement names an agent")
    if purpose is None:
        _err(errors, "MISSING_PURPOSE", "State the purpose: PURPOSE <purpose_id>.")
    if expire is None:
        _err(errors, "MISSING_EXPIRY", "Authority must expire: EXPIRE AT <UTC timestamp>.")
    if not permissions:
        _err(errors, "MISSING_PERMISSION", "No PERMIT statement: missing authority means denial, so nothing can be compiled")
    for p in permissions.values():
        if p["action"] in prohibitions:
            _err(errors, "PERMISSION_PROHIBITION_CONFLICT", f"{p['action']} is both permitted and prohibited")
    if len(currencies) > 1:
        _err(errors, "CURRENCY_MISMATCH", f"Mandate uses one currency; found {sorted(currencies)}")
    ccy = next(iter(currencies), "CAD")
    for p in permissions.values():
        for rid in p["resources"]:
            acct = next((a for a in resolver.accounts.values() if a["id"] == rid), None)
            if acct and p["action"] in taxonomy.MONEY_MOVING and acct["currency"] != ccy:
                _err(errors, "CURRENCY_MISMATCH", f"Account {rid} is held in {acct['currency']} but the mandate limits are in {ccy}")
    if errors:
        return result

    agent = resolver.agents[next(iter(agent_refs))]
    if "mandates.delegate" in prohibitions and delegation["allowed"]:
        _err(errors, "PERMISSION_PROHIBITION_CONFLICT", "ALLOW DELEGATION conflicts with PROHIBIT DELEGATION")
        return result
    jur = jurisdictions if jurisdictions is not None else _default_jurisdictions(cust["jurisdiction"])
    try:
        mandate = Mandate.model_validate(
            {
                "mandate_id": mandate_id,
                "principal": {"id": principal_id, "type": cust["type"]},
                "mandatary": {"agent_id": agent["id"], "operator_id": agent["operator_id"], "client_id": agent["client_id"]},
                "purpose": purpose,
                "currency": ccy,
                "permissions": sorted(permissions.values(), key=lambda p: (p["action"], p["resources"], canon.canonical(p["constraints"]))),
                "prohibitions": sorted(prohibitions),
                "aggregate_constraints": agg,
                "obligations": {"notify_customer": True, **obligations},
                "delegation": delegation,
                "validity": {"not_before": start or default_not_before, "expires_at": expire, **({"budget_timezone": tz} if tz else {})},
                "jurisdictions": jur,
                "policy_version": policy_version,
            }
        )
    except ValidationError as e:
        for item in e.errors():
            _err(errors, "SCHEMA_VIOLATION", str(item.get("msg")), path=".".join(str(x) for x in item.get("loc", ())))
        return result
    mdict = mandate.model_dump()
    result.update(
        ok=True,
        mandate=mdict,
        normalized_cnl=render_cnl(mdict, resolver),
        canonical_digest=canon.digest(mdict),
        defaults_applied=_defaults(start, jurisdictions, tz),
    )
    return result


def _default_jurisdictions(j: str) -> list[str]:
    return sorted({j.split("-")[0], j})


def _defaults(start, jur, tz) -> list[str]:
    d = []
    if start is None:
        d.append("START AT defaulted to the compile reference time; confirm before approval")
    if jur is None:
        d.append("JURISDICTION defaulted from the customer's jurisdiction of record")
    if tz is None:
        d.append(f"BUDGET_TIMEZONE defaulted to {config.BUDGET_TZ_DEFAULT}")
    return d


def render_cnl(m: dict, resolver: Resolver) -> str:
    """Normalized KYM-CNL: fixed statement order, canonical spacing, canonical money format."""
    ccy = m["currency"]
    agent_ref = resolver.ref_of("agent", m["mandatary"]["agent_id"])
    out = [f"PURPOSE {m['purpose']}.", f"JURISDICTION {', '.join(sorted(m['jurisdictions']))}.", f"BUDGET_TIMEZONE {m['validity']['budget_timezone']}."]
    for p in m["permissions"]:
        a = taxonomy.BY_ID[p["action"]]
        res = ", ".join(sorted(resolver.ref_of("account", r) for r in p["resources"]))
        c = p["constraints"]
        if a.financial_execution:
            to = [resolver.ref_of("payee", b) for b in c.get("allowed_beneficiaries", []) + c.get("allowed_merchants", [])]
            to += [f"category.{x}" for x in c.get("allowed_merchant_categories", [])]
            to += [f"country.{x.lower()}" for x in c.get("allowed_countries", [])]
            to += [resolver.ref_of("account", x) for x in c.get("allowed_destination_accounts", [])]
            out.append(f"PERMIT {agent_ref} TO {a.cnl} FROM {res} TO {', '.join(sorted(to))} WITH MAX_AMOUNT {money.fmt(c['maximum_amount_minor'], ccy)} PER TRANSACTION.")
        else:
            out.append(f"PERMIT {agent_ref} TO {a.cnl} ON {res}.")
    agg = m["aggregate_constraints"]
    if agg.get("maximum_daily_amount_minor"):
        out.append(f"LIMIT TOTAL_PAYMENTS TO {money.fmt(agg['maximum_daily_amount_minor'], ccy)} PER CALENDAR_DAY.")
    if agg.get("maximum_monthly_amount_minor"):
        out.append(f"LIMIT TOTAL_PAYMENTS TO {money.fmt(agg['maximum_monthly_amount_minor'], ccy)} PER CALENDAR_MONTH.")
    if agg.get("maximum_transaction_count_monthly"):
        out.append(f"LIMIT PAYMENT_COUNT TO {agg['maximum_transaction_count_monthly']} PER CALENDAR_MONTH.")
    ob = m["obligations"]
    if ob.get("human_approval_above_minor") is not None:
        n = ob["required_approvals"]
        word = "HUMAN_APPROVAL" if n == 1 else "HUMAN_APPROVALS"
        prefix = "" if n == 1 else f"{n} "
        out.append(f"REQUIRE {prefix}{word} FOR PAYMENTS ABOVE {money.fmt(ob['human_approval_above_minor'], ccy)}.")
    for p in m["prohibitions"]:
        if p == "mandates.delegate":
            continue
        out.append(f"PROHIBIT {taxonomy.BY_ID[p].cnl}.")
    if m["delegation"]["allowed"]:
        out.append(f"ALLOW DELEGATION TO DEPTH {m['delegation']['maximum_depth']}.")
    else:
        out.append("PROHIBIT DELEGATION.")
    out.append(f"START AT {m['validity']['not_before']}.")
    out.append(f"EXPIRE AT {m['validity']['expires_at']}.")
    return "\n".join(out)


# --------------------------------------------------------------------------- ambiguity detection

AMBIGUITY_RULES = [
    ("accounts", r"\b(my money|my accounts?|my funds|everything|all my)\b", "Which accounts may the agent use?", "Name each account (e.g. account.chequing-001)."),
    ("manage", r"\bmanage\b", "What does 'manage' include: reading data, preparing payments or executing payments?", "List each permitted action explicitly."),
    ("bills", r"\b(usual|regular|normal|recurring|my) bills?\b|\bbills\b", "Which bills, and which beneficiaries?", "Name each beneficiary (e.g. beneficiary.hydro-quebec)."),
    ("usual", r"\busual\b", "What does 'usual' mean (which payees, which amounts)?", "Replace 'usual' with a closed list of beneficiaries and a maximum amount."),
    ("amount", r"\bsome (savings|money)\b|\ba bit\b|\bsome\b", "What amount is permitted?", "State a maximum amount and currency per transaction."),
    ("frequency", r"\bwhenever\b|\bit makes sense\b|\bas needed\b|\bwhen needed\b|\boften\b", "What is the required frequency or trigger?", "State an explicit limit per calendar month, not a judgement."),
    ("excessive", r"\b(too much|excessive|overspend\w*|reasonable|careful)\b", "What defines excessive spending?", "State a total limit per calendar month or day."),
    ("move", r"\b(move|transfer)\b.*\b(savings|money)\b", "Which source and destination accounts, and is the destination your own account?", "Use EXECUTE_TRANSFER FROM <account> TO <own account>; external transfers need a named beneficiary."),
    ("approval", r"\bapprov\w*\b|\bconfirm\b|\bask me\b", "Above which amount must a human approve?", "State REQUIRE HUMAN_APPROVAL FOR PAYMENTS ABOVE <amount>."),
]

REQUIRED_RESOLUTIONS = [
    ("accounts", "Which accounts?"),
    ("actions", "Which actions are permitted?"),
    ("beneficiaries", "Which beneficiaries?"),
    ("max_amount", "What maximum amount per payment?"),
    ("monthly_budget", "What total limit per calendar month?"),
    ("approval_above", "Which payments need human approval?"),
    ("expires_at", "When does the authority expire?"),
    ("purpose", "What is the purpose?"),
]


def detect_ambiguities(instruction: str) -> list[dict]:
    found: list[dict] = []
    low = instruction.lower()
    for rid, pattern, question, hint in AMBIGUITY_RULES:
        for m in re.finditer(pattern, low):
            found.append({"id": f"{rid}-{len(found) + 1}", "kind": rid, "phrase": instruction[m.start():m.end()], "question": question, "hint": hint, "resolved": False})
            break
    explicit = bool(re.search(r"\b(account\.[a-z0-9_-]+|beneficiary\.[a-z0-9_-]+)\b", low))
    if not explicit and not any(a["kind"] == "accounts" for a in found):
        found.append({"id": f"accounts-{len(found) + 1}", "kind": "accounts", "phrase": "(no account named)", "question": "Which accounts may the agent use?", "hint": "Name each account.", "resolved": False})
    return found


def propose_cnl(res: dict, resolver: Resolver | None = None) -> str:
    """Deterministic template: builds KYM-CNL ONLY from values the customer explicitly resolved. Never invents authority."""
    required = ["agent", "purpose", "expires_at"]
    missing = [k for k in required if not res.get(k)]
    if missing:
        raise ValueError(f"unresolved: {', '.join(missing)}")
    agent = res["agent"]
    ccy = res.get("currency", "CAD")
    lines = [f"PURPOSE {res['purpose']}."]
    for verb in res.get("read_actions", []):
        for acct in res.get("accounts", []):
            lines.append(f"PERMIT {agent} TO {verb} ON {acct}.")
    pay = res.get("payment")
    if pay:
        lines.append(
            f"PERMIT {agent} TO {pay.get('verb', 'PAY_INVOICE')} FROM {', '.join(pay['accounts'])} TO {', '.join(pay['beneficiaries'])} "
            f"WITH MAX_AMOUNT {pay['max_amount']} {ccy} PER TRANSACTION."
        )
    if res.get("monthly_budget"):
        lines.append(f"LIMIT TOTAL_PAYMENTS TO {res['monthly_budget']} {ccy} PER CALENDAR_MONTH.")
    if res.get("approval_above") is not None:
        lines.append(f"REQUIRE HUMAN_APPROVAL FOR PAYMENTS ABOVE {res['approval_above']} {ccy}.")
    for p in res.get("prohibit", []):
        lines.append(f"PROHIBIT {p}.")
    lines.append(f"EXPIRE AT {res['expires_at']}.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- consent summaries

FR_ACTIONS = {
    "accounts.read": "consulter le compte", "balances.read": "consulter le solde", "transactions.read": "consulter les transactions",
    "accounts.owner.read": "consulter le titulaire du compte", "data.transmit_external": "transmettre des données à un tiers",
    "analysis.categorize": "catégoriser les transactions", "analysis.cashflow": "analyser les flux de trésorerie",
    "analysis.budget": "générer un budget", "payments.prepare": "préparer un paiement", "transfers.prepare": "préparer un virement",
    "investments.prepare": "préparer un ordre de placement", "payments.initiate": "initier un paiement", "payments.pay_invoice": "payer une facture",
    "purchases.goods": "acheter des biens", "transfers.execute": "exécuter un virement interne", "transfers.external": "exécuter un virement externe",
    "investments.trade": "exécuter un ordre de placement", "mandates.request": "demander un mandat", "mandates.delegate": "déléguer son autorité",
    "mandates.revoke": "révoquer un mandat",
}


def consent_summary(m: dict, names: dict, lang: str = "en") -> str:
    """Human-readable summary shown in the bank-controlled approval interface. names: id -> display name."""
    ccy = m["currency"]
    agent = names.get(m["mandatary"]["agent_id"], m["mandatary"]["agent_id"])
    op = names.get(m["mandatary"]["operator_id"], m["mandatary"]["operator_id"])
    nm = lambda i: names.get(i, i)  # noqa: E731
    fr = lang == "fr"
    L = []
    if fr:
        L.append(f"Meridian Bank autorisera l'agent « {agent} » (exploité par {op}) à agir pour votre compte, du {m['validity']['not_before']} au {m['validity']['expires_at']}, à la seule fin : {m['purpose']}.")
        L.append("L'agent PEUT :")
    else:
        L.append(f"Meridian Bank will let the agent \"{agent}\" (operated by {op}) act for you from {m['validity']['not_before']} until {m['validity']['expires_at']}, only for: {m['purpose']}.")
        L.append("The agent MAY:")
    for p in m["permissions"]:
        a = taxonomy.BY_ID[p["action"]]
        label = FR_ACTIONS[a.id] if fr else a.label.lower()
        res = ", ".join(nm(r) for r in p["resources"])
        c = p["constraints"]
        extra = ""
        if c.get("maximum_amount_minor"):
            amt = money.fmt(c["maximum_amount_minor"], ccy)
            who = ", ".join(nm(x) for x in c.get("allowed_beneficiaries", []) + c.get("allowed_merchants", []) + c.get("allowed_destination_accounts", []))
            extra = f" ; max {amt} par opération" if fr else f"; at most {amt} each time"
            if who:
                extra += f" ; bénéficiaires : {who}" if fr else f"; only to: {who}"
        L.append(f"  - {label} ({res}){extra}")
    L.append("L'agent NE PEUT PAS :" if fr else "The agent MAY NOT:")
    for p in m["prohibitions"]:
        L.append(f"  - {FR_ACTIONS[p] if fr else taxonomy.BY_ID[p].label.lower()}")
    if not m["delegation"]["allowed"] and "mandates.delegate" not in m["prohibitions"]:
        L.append("  - déléguer son autorité" if fr else "  - delegate its authority")
    L.append("Autre action : refusée par défaut." if fr else "Anything not listed above is denied.")
    agg = m["aggregate_constraints"]
    if agg.get("maximum_monthly_amount_minor"):
        L.append((f"Total mensuel maximal : {money.fmt(agg['maximum_monthly_amount_minor'], ccy)}." if fr else f"Monthly total limit: {money.fmt(agg['maximum_monthly_amount_minor'], ccy)}."))
    if agg.get("maximum_daily_amount_minor"):
        L.append((f"Total quotidien maximal : {money.fmt(agg['maximum_daily_amount_minor'], ccy)}." if fr else f"Daily total limit: {money.fmt(agg['maximum_daily_amount_minor'], ccy)}."))
    ob = m["obligations"]
    if ob.get("human_approval_above_minor") is not None:
        n = ob["required_approvals"]
        L.append(
            f"Une approbation humaine ({n} approbateur(s)) est requise au-delà de {money.fmt(ob['human_approval_above_minor'], ccy)}."
            if fr else f"Human approval ({n} approver(s)) is required for payments above {money.fmt(ob['human_approval_above_minor'], ccy)}."
        )
    L.append("Vous pouvez révoquer ce mandat en tout temps. La révocation n'annule pas les paiements déjà exécutés." if fr
             else "You can revoke this mandate at any time. Revocation does not reverse payments already executed.")
    L.append("Démonstration : données synthétiques, aucune valeur juridique ni conformité réglementaire." if fr
             else "Demonstration: synthetic data; no legal effect and no regulatory compliance is claimed.")
    return "\n".join(L)


# --------------------------------------------------------------------------- OAuth views


LOCATION = {
    "data": f"{config.ISSUER}/api/accounts",
    "payments": f"{config.ISSUER}/api/payments",
    "transfers": f"{config.ISSUER}/api/transfers",
}


def authorization_details(m: dict, digest: str | None = None) -> list[dict]:
    """RFC 9396 authorization_details using the proposed (non-IETF) type kym_financial_mandate."""
    groups: dict[str, dict] = {}
    for p in m["permissions"]:
        a = taxonomy.BY_ID[p["action"]]
        if a.scope is None:
            continue
        loc = "payments" if p["action"] in taxonomy.PAYMENT_ACTIONS or a.scope == "payments.prepare" else ("transfers" if p["action"] in taxonomy.TRANSFER_ACTIONS else "data")
        g = groups.setdefault(loc, {"type": "kym_financial_mandate", "locations": [LOCATION[loc]], "actions": [], "mandate_id": m["mandate_id"], "mandate_version": m["version"], "accounts": [], "beneficiaries": []})
        g["actions"].append(p["action"])
        g["accounts"] += p["resources"]
        g["beneficiaries"] += p["constraints"].get("allowed_beneficiaries", [])
        if p["constraints"].get("maximum_amount_minor"):
            cur = g.get("maximum_amount")
            amt = p["constraints"]["maximum_amount_minor"]
            g["maximum_amount"] = {"amount_minor": max(amt, cur["amount_minor"]) if cur else amt, "currency": m["currency"]}
    out = []
    for g in groups.values():
        g["actions"] = sorted(set(g["actions"]))
        g["accounts"] = sorted(set(g["accounts"]))
        g["beneficiaries"] = sorted(set(g["beneficiaries"]))
        if not g["beneficiaries"]:
            del g["beneficiaries"]
        out.append(g)
    return out


def oauth_scopes(m: dict) -> list[str]:
    return sorted({taxonomy.BY_ID[p["action"]].scope for p in m["permissions"] if taxonomy.BY_ID[p["action"]].scope})
