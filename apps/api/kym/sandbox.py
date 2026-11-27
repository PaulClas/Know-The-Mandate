"""Interactive agent sandbox: deterministic scripted agents behind a restricted tool interface.

The default agent needs no LLM. An optional LLM could propose typed tool calls (see `ToolCallProposer`), but it can never
decide authorization, hold signing keys or reach the payment engine: every tool call below goes over HTTP to the bank PEP.
Only observable tool requests and structured decisions are recorded; no private model reasoning is collected.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Protocol

from sqlalchemy import select

from . import agents as agents_mod
from . import cnl, config, db, demo, gateway, kyc, ledger, mandates, money, oauth, taxonomy
from .agent_sdk import AgentClient, AuthorizationFailed, TokenSet

_http = None
_tokens: dict[tuple, TokenSet] = {}

SANDBOX_AGENTS = [
    {"id": "agent_finance_001", "name": "Personal Finance Assistant", "description": "Reads accounts and analyzes spending. May ask to delegate.",
     "sample_prompts": ["What is my chequing balance?", "Analyze my spending", "Transfer CAD 500 to my savings", "Pay CAD 85 to Hydro-Québec"]},
    {"id": "agent_billpay_001", "name": "Household Bill Payment Agent", "description": "Pays utilities within a mandate.",
     "sample_prompts": ["Pay CAD 85 to Hydro-Québec", "Pay CAD 180 to Hydro-Québec", "Pay CAD 300 to Hydro-Québec", "Pay CAD 50 to Vidéotron"]},
    {"id": "agent_shopping_001", "name": "Shopping Agent", "description": "Buys goods from approved merchants. Treats merchant documents as instructions (naive demo agent).",
     "sample_prompts": ["Buy CAD 40 of groceries from Marché Local", "Check this merchant document"]},
    {"id": "agent_savings_001", "name": "Savings Optimization Agent", "description": "Moves money between the customer's own accounts.",
     "sample_prompts": ["Move CAD 200 to savings", "Transfer CAD 200 to the new supplier"]},
    {"id": "agent_treasury_001", "name": "Business Treasury Agent", "description": "Prepares supplier payments; execution needs two signatories.",
     "sample_prompts": ["Prepare a payment of CAD 4,200 to Acme Industrial Supplies", "Pay CAD 4,200 to Acme Industrial Supplies"]},
    {"id": "agent_unverified_001", "name": "External Unverified Agent", "description": "Not verified by the bank: it holds no authority.",
     "sample_prompts": ["What is my balance?", "Pay CAD 100 to Hydro-Québec"]},
]


class ToolCallProposer(Protocol):
    """Provider-independent interface for an optional LLM that proposes tool calls. It has no authority; the PEP decides."""

    def propose(self, instruction: str, tools: list[dict]) -> list[dict]: ...


def http():
    global _http
    if _http is None:
        from starlette.testclient import TestClient

        from .app import app

        _http = TestClient(app, base_url="http://testserver")
    return _http


def reset() -> None:
    _tokens.clear()


# --------------------------------------------------------------------------- playground (dry-run through the real PEP)


def playground_evaluate(s, body: dict, mrow: db.MandateRow) -> dict:
    agent = s.get(db.Agent, body["agent_id"])
    if not agent:
        raise mandates.MandateError("unknown agent", "MANDATE_NOT_FOUND")
    key = agents_mod.load_demo_agent_key(agent.id)
    if key is None:
        raise mandates.MandateError("agent has no demo key in the sandbox key store", "NOT_AUTHORIZED")
    profile = body.get("token_profile", "valid")
    action = body["action"]
    kw: dict = {}
    if profile == "wrong_audience":
        kw["aud"] = "https://other-bank.example/api"
    elif profile == "expired":
        kw["ttl"] = -120
    elif profile == "missing_scope":
        kw["drop_scope"] = taxonomy.scope_for(action)
    elif profile == "wrong_actor":
        kw["actor"] = "agent_unverified_001"
    token = oauth.mint_test_token(s, agent.id, mrow.mandate_id, mrow.version, **kw)
    if profile == "revoked":
        jti = oauth.decode_token(token)["jti"]
        s.get(db.Token, jti).revoked_at = "2000-01-01T00:00:00.000Z"
    client = AgentClient(None, agent.id, agent.client_id, "", key, base="http://playground.local")
    url = "http://playground.local/bank/playground"
    caller = gateway.Caller("POST", url, f"DPoP {token}", None if profile == "no_dpop" else client.dpop("POST", url, token))
    kind = "READ" if action in taxonomy.DATA_ACTIONS else "PREPARE" if action == "payments.prepare" else "TRANSFER" if action in taxonomy.TRANSFER_ACTIONS else "PAYMENT"
    spec = {"kind": kind, "action": action, "account_id": body["account_id"], "beneficiary_id": body.get("beneficiary_id"), "merchant_id": body.get("merchant_id"), "to_account_id": body.get("to_account_id"),
            "amount_minor": body.get("amount_minor"), "currency": body.get("currency"), "purpose": body.get("purpose"), "approval_id": body.get("approval_id")}
    status, out = gateway.handle(gateway.Caller("POST", url, caller.authorization, caller.dpop), spec, dry_run=True)
    if status != 200:
        return {"dry_run": True, "http_status": status, **out}
    trace = out["trace"]
    token_checks = [c for c in trace if c["id"].startswith("token.")]
    out["oauth_verification"] = "PASS" if all(c["outcome"] in ("PASS", "SKIP") for c in token_checks) else "FAIL"
    out["mandate_verification"] = "PASS" if not any(c["outcome"] == "FAIL" for c in trace if not c["id"].startswith(("token.", "risk.", "agent.", "customer."))) else "FAIL"
    out["token_profile"] = profile
    out["token_source"] = "real ES256-signed token minted server-side for the playground (not issued through the consent flow)"
    out["http_status"] = 200
    return out


# --------------------------------------------------------------------------- chat


AMOUNT_RE = re.compile(r"(?:cad|usd|\$)\s*([\d][\d,]*(?:\.\d{1,2})?)|([\d][\d,]*(?:\.\d{1,2})?)\s*(?:cad|usd|dollars?)", re.I)
PAYEE_HINTS = {"hydro": "beneficiary_hydro_quebec", "vid": "beneficiary_videotron", "tax": "beneficiary_city_taxes", "overseas": "beneficiary_new_supplier", "new supplier": "beneficiary_new_supplier",
               "watchlist": "beneficiary_watchlisted", "sanction": "beneficiary_watchlisted", "acme": "beneficiary_acme_supplies", "beta": "beneficiary_beta_logistics",
               "grocer": "merchant_grocery_001", "march": "merchant_grocery_001", "electronic": "merchant_electronics_001", "gadget": "merchant_gadget_online"}


def _amount(text: str) -> int | None:
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    raw = (m.group(1) or m.group(2)).replace(",", "")
    return money.parse_major(raw, "CAD")


def _payee(text: str) -> str | None:
    low = text.lower()
    for k, v in PAYEE_HINTS.items():
        if k in low:
            return v
    return None


class Session:
    def __init__(self, agent_id: str, customer_id: str, mandate: dict | None):
        self.steps: list[dict] = []
        self.agent_id, self.customer_id, self.mandate = agent_id, customer_id, mandate
        self.client: AgentClient | None = None
        self.token: TokenSet | None = None
        self.proposals: dict[str, dict] = {}

    def step(self, kind: str, title: str, detail: str = "", **kw):
        self.steps.append({"index": len(self.steps), "kind": kind, "title": title, "detail": detail, **kw})

    def connect(self):
        c = http()
        self.client = demo.agent_client(c, self.agent_id)
        if not self.mandate:
            self.step("oauth", "No mandate: agent holds no financial authority", "Registered agents can only act under a customer-approved mandate. Calls will be rejected.")
            return
        key = (self.agent_id, self.mandate["mandate_id"], self.mandate["version"])
        tok = _tokens.get(key)
        if tok and tok.expires_at > time.time():
            self.token = tok
            self.step("oauth", "Reusing mandate-bound access token", f"scope: {tok.scope} (DPoP-bound, short-lived)")
            return
        details = cnl.authorization_details(self.mandate["content"])
        try:
            self.token = self.client.authorize(details, demo.customer_approver(c, self.customer_id))
            _tokens[key] = self.token
            self.step("oauth", "Authorization code + PKCE + PAR + DPoP: token issued", f"scope: {self.token.scope}; RAR type kym_financial_mandate; mandate {self.mandate['mandate_id']} v{self.mandate['version']}")
        except AuthorizationFailed as e:
            self.step("oauth", "OAuth authorization refused", str(e.body.get("error_description", e.body)), status=e.status)

    # -- restricted tool interface -------------------------------------------------
    def _call(self, tool: str, args: dict, method: str, path: str, body: dict | None = None, idem: str | None = None):
        self.step("tool_call", f"Agent proposes tool call: {tool}", "", tool=tool, arguments=args)
        if not self.client:
            self.connect()
        token = self.token or "no-token"
        r = self.client.call(token, method, path, json_body=body, idempotency_key=idem)
        data = r.json()
        self._explain(data, r.status_code)
        return r.status_code, data

    def _explain(self, data: dict, status: int):
        did = data.get("decision_id")
        with db.read() as s:
            d = s.get(db.Decision, did) if did else None
            if d:
                tr = d.trace
                tok = [c for c in tr if c["id"].startswith("token.")]
                self.step("oauth", "OAuth verification", "; ".join(f"{c['name']}: {c['outcome']}" for c in tok), status=("PASS" if all(c["outcome"] != "FAIL" for c in tok) else "FAIL"))
                man = [c for c in tr if c["id"].startswith(("mandate.", "parent", "account.", "agent.", "customer."))]
                fails = [c for c in tr if c["outcome"] == "FAIL" and not c["id"].startswith("token.")]
                self.step("mandate", "Mandate evaluation", f"{sum(c['outcome'] == 'PASS' for c in man)} checks passed" + (f"; failed: {', '.join(sorted({c['detail'] for c in fails}))[:300]}" if fails else ""),
                          status="FAIL" if fails else "PASS", checks=[{"name": c["name"], "outcome": c["outcome"], "detail": c["detail"]} for c in tr])
                r = d.inputs.get("risk")
                if r:
                    self.step("risk", f"Transaction risk: {r['level']} ({r['score']})", ", ".join(x["id"] for x in r["signals"] if x["triggered"]) or "no signals", status=r["level"])
                self.step("decision", f"Decision: {d.decision}", ", ".join(d.reason_codes) or "all checks passed", decision=d.decision, reason_codes=d.reason_codes)
            elif status == 401:
                self.step("decision", "Request rejected before policy evaluation", f"HTTP 401: {data.get('error_description') or data.get('error')}", decision="DENY", reason_codes=["INVALID_TOKEN"])
        if "status" in data and data.get("transaction_id"):
            self.step("execution", f"Execution status: {data['status']}", data.get("failure_reason") or "", status=data["status"], transaction_id=data["transaction_id"])
            with db.read() as s:
                evs, _ = ledger.list_events(s, transaction_id=data["transaction_id"], ascending=True, limit=20)
            self.step("ledger", f"{len(evs)} signed evidence events", ", ".join(e["event_type"] for e in evs), ledger_event_ids=[e["event_id"] for e in evs])

    def get_accounts(self):
        return self._call("get_accounts", {}, "GET", "/bank/accounts")

    def get_balance(self, account_id: str):
        return self._call("get_balance", {"account_id": account_id}, "GET", f"/bank/accounts/{account_id}/balances")

    def get_transactions(self, account_id: str):
        return self._call("get_transactions", {"account_id": account_id}, "GET", f"/bank/accounts/{account_id}/transactions")

    def propose_payment(self, account_id: str, payee_id: str, amount_minor: int, purpose: str | None):
        key = "beneficiary_id" if payee_id.startswith("beneficiary") else "merchant_id"
        body = {"account_id": account_id, key: payee_id, "amount_minor": amount_minor, "currency": "CAD", "purpose": purpose}
        st, data = self._call("propose_payment", {"account_id": account_id, "beneficiary_id": payee_id, "amount": amount_minor}, "POST", "/bank/payments/proposals", body)
        if st == 200:
            self.proposals[data["payment_proposal_id"]] = body
        return st, data

    def initiate_payment(self, body: dict, action: str = "payments.initiate"):
        return self._call("initiate_payment", {k: v for k, v in body.items()}, "POST", "/bank/payments", {**body, "action": action}, idem=uuid.uuid4().hex)

    def initiate_transfer(self, body: dict):
        return self._call("initiate_transfer", body, "POST", "/bank/transfers", body, idem=uuid.uuid4().hex)

    def request_delegation(self, parent_mandate_id: str, child_agent_id: str, max_amount_minor: int):
        self.step("tool_call", "Agent proposes tool call: request_delegation", "", tool="request_delegation", arguments={"parent_mandate_id": parent_mandate_id, "child_agent_id": child_agent_id, "max_amount_minor": max_amount_minor})
        if not self.client:
            self.connect()
        with db.read() as s:
            child_agent = s.get(db.Agent, child_agent_id)
            parent = mandates.get_row(s, parent_mandate_id)
        child = demo.child_from_parent(parent.content, child_agent, max_amount_minor=max_amount_minor)
        r = self.client.call(self.token or "no-token", "POST", f"/api/mandates/{parent_mandate_id}/delegate", json_body={"child_content": child})
        data = r.json()
        codes = data.get("reason_codes") or [data.get("error")]
        self.step("decision", "Delegation " + ("ACCEPTED" if r.status_code == 201 else "REJECTED"), ", ".join(str(c) for c in codes if c) if r.status_code != 201 else f"child mandate {data.get('mandate_id')} active",
                  decision="ALLOW" if r.status_code == 201 else "DENY", reason_codes=[c for c in codes if c] if r.status_code != 201 else [])
        return r.status_code, data


def _find_mandate(customer_id: str, agent_id: str, mandate_id: str | None) -> dict | None:
    with db.read() as s:
        if mandate_id:
            return mandates.view(s, mandate_id)
        for m in mandates.list_mandates(s, agent_id=agent_id):
            if m["status"] == "ACTIVE" and kyc.can_act_for(s, customer_id, m["principal_id"]):
                return mandates.view(s, m["mandate_id"], m["version"])
    return None


def chat(*, agent_id: str, message: str, customer_id: str, mandate_id: str | None = None, untrusted_document: str | None = None) -> dict:
    with db.read() as s:
        if not s.get(db.Agent, agent_id):
            raise mandates.MandateError("unknown agent", "MANDATE_NOT_FOUND")
    mandate = _find_mandate(customer_id, agent_id, mandate_id)
    sess = Session(agent_id, customer_id, mandate)
    sess.step("instruction", "User instruction", message)
    sess.connect()
    low = message.lower()
    accounts = sorted({r for p in (mandate or {"content": {"permissions": []}})["content"]["permissions"] for r in p["resources"]}) or ["account_001"]
    acct = "account_002" if "saving" in low and "account_002" in accounts else accounts[0]
    purpose = mandate["content"]["purpose"] if mandate else None
    reply = ""
    doc = untrusted_document or ""
    if doc:
        sess.step("tool_call", "Agent reads external merchant document (untrusted content)", doc[:300], tool="read_document", arguments={"length": len(doc)})
        inj = re.search(r"payment of\s+(?:cad\s*)?([\d,]+(?:\.\d{1,2})?)", doc, re.I)
        if inj:
            amt = money.parse_major(inj.group(1).replace(",", ""), "CAD")
            sess.step("instruction", "Naive demo agent treats document text as an instruction", f"'{inj.group(0)}' -> attempts payment of {amt} minor units. External content cannot change the mandate.")
            payee = _payee(doc) or _payee(message) or "merchant_gadget_online"
            st, data = sess.initiate_payment({"account_id": acct, "merchant_id" if payee.startswith("merchant") else "beneficiary_id": payee, "amount_minor": amt, "currency": "CAD", "purpose": purpose}, "purchases.goods" if payee.startswith("merchant") else "payments.initiate")
            reply = f"The document tried to make me pay; the bank answered {data.get('decision') or st}: {', '.join(data.get('reason_codes', []))}."
            return {"reply": reply, "steps": sess.steps, "mandate_id": mandate["mandate_id"] if mandate else None}
    amount = _amount(message)
    payee = _payee(message)
    if re.search(r"\b(delegate|sub-?agent)\b", low) and mandate:
        child = "agent_billpay_001" if agent_id != "agent_billpay_001" else "agent_finance_001"
        st, data = sess.request_delegation(mandate["mandate_id"], child, amount or 20000)
        reply = "Delegation accepted." if st == 201 else f"Delegation refused: {data.get('reason_codes') or data.get('error')}"
    elif re.search(r"\bbalance\b", low):
        st, data = sess.get_balance(acct)
        reply = f"Balance: {money.fmt(data['availableBalanceMinor'], data['currency'])}" if st == 200 else f"I could not read the balance ({data.get('reason_codes') or data.get('error')})."
    elif re.search(r"\b(transactions?|spending|analy[sz]e|budget)\b", low):
        st, data = sess.get_transactions(acct)
        if st == 200:
            tot: dict[str, int] = {}
            for t in data["transactions"]:
                if t["amountMinor"] < 0:
                    tot[t["category"]] = tot.get(t["category"], 0) + -t["amountMinor"]
            top = sorted(tot.items(), key=lambda kv: -kv[1])[:3]
            sess.step("execution", "Local analysis (no bank action)", "; ".join(f"{k}: {money.fmt(v, 'CAD')}" for k, v in top))
            reply = "Top spending categories: " + ", ".join(f"{k} {money.fmt(v, 'CAD')}" for k, v in top)
            if re.search(r"\b(transfer|move|send)\b", low):
                low = "transfer"
        else:
            reply = f"I could not read transactions ({data.get('reason_codes') or data.get('error')})."
    if re.search(r"\b(transfer|move)\b", low) and amount:
        if "saving" in low:
            st, data = sess.initiate_transfer({"account_id": "account_001", "to_account_id": "account_002", "amount_minor": amount, "currency": "CAD", "purpose": purpose})
        else:
            st, data = sess.initiate_transfer({"account_id": acct, "beneficiary_id": payee or "beneficiary_new_supplier", "amount_minor": amount, "currency": "CAD", "purpose": purpose})
        reply = (reply + " " if reply else "") + f"Transfer result: {data.get('decision') or st} {', '.join(data.get('reason_codes', []))}"
    elif re.search(r"\b(prepare|draft)\b", low) and amount and payee:
        st, data = sess.propose_payment(acct, payee, amount, purpose)
        reply = f"Payment prepared ({data.get('payment_proposal_id')}). Preparing does not authorize execution." if st == 200 else f"Preparation refused: {data.get('reason_codes')}"
    elif re.search(r"\b(pay|buy|purchase|settle)\b", low) and amount and payee:
        if agent_id in ("agent_treasury_001",) or "prepare" in low:
            sess.propose_payment(acct, payee, amount, purpose)
        key = "merchant_id" if payee.startswith("merchant") else "beneficiary_id"
        action = "purchases.goods" if payee.startswith("merchant") else "payments.initiate"
        st, data = sess.initiate_payment({"account_id": acct, key: payee, "amount_minor": amount, "currency": "CAD", "purpose": purpose}, action)
        if st == 202 and data.get("approval_id"):
            reply = f"Bank approval required ({data['approval_id']}). The customer must approve in the bank portal; I cannot approve it myself."
        elif st == 201:
            reply = f"Payment executed: {money.fmt(amount, 'CAD')}."
        else:
            reply = f"The bank {data.get('decision', 'refused')}: {', '.join(data.get('reason_codes', []))}"
    if not reply:
        reply = "I can read balances, analyze transactions, prepare/make payments, move money or request delegation. Try one of the sample prompts."
    return {"reply": reply, "steps": sess.steps, "mandate_id": mandate["mandate_id"] if mandate else None}


_ = (config, select)
