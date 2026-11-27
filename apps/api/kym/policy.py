"""Policy Decision Point: deterministic, side-effect free evaluation of effective financial authority.

effective authority = customer authority ∩ agent capabilities ∩ OAuth authorization ∩ active mandate
                      ∩ every parent mandate ∩ bank policy ∩ risk controls ∩ operational restrictions

* Deny by default. Explicit prohibitions override permissions. Missing information fails closed.
* No ontology reasoner, trust score or LLM participates. A high trust score cannot override a denial.
* `evaluate` is a pure function of a JSON snapshot (`inputs`) so any historical decision can be replayed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import canon, clock, taxonomy

DECISIONS = ["ALLOW", "DENY", "REQUIRE_HUMAN_APPROVAL", "REFER_TO_RISK_REVIEW"]


def _engine_digest() -> str:
    """Fingerprint of the decision logic (this file and the action taxonomy). Recorded in each signed decision event so a later replay can tell
    'the engine changed since this decision' apart from 'the evidence was altered'."""
    import hashlib
    from pathlib import Path

    here = Path(__file__).parent
    return "sha256:" + hashlib.sha256(b"".join((here / n).read_bytes() for n in ("policy.py", "taxonomy.py"))).hexdigest()


ENGINE_DIGEST = _engine_digest()

REASON_CODES = [
    "AGENT_NOT_VERIFIED", "AGENT_SUSPENDED", "INVALID_TOKEN", "INVALID_ACTOR_BINDING", "TOKEN_SCOPE_INSUFFICIENT",
    "MANDATE_NOT_FOUND", "MANDATE_EXPIRED", "MANDATE_REVOKED", "MANDATE_VERSION_MISMATCH", "RESOURCE_NOT_AUTHORIZED",
    "ACTION_NOT_AUTHORIZED", "PURPOSE_NOT_AUTHORIZED", "BENEFICIARY_NOT_AUTHORIZED", "CURRENCY_NOT_AUTHORIZED",
    "TRANSACTION_LIMIT_EXCEEDED", "DAILY_LIMIT_EXCEEDED", "MONTHLY_LIMIT_EXCEEDED", "DELEGATION_NOT_ALLOWED",
    "DELEGATION_EXCEEDS_PARENT", "HUMAN_APPROVAL_REQUIRED", "RISK_THRESHOLD_EXCEEDED",
]
# Additional codes beyond the proposed base list (KYM extensions)
EXTENDED_REASON_CODES = [
    "CUSTOMER_NOT_VERIFIED", "ACCOUNT_RESTRICTED", "MANDATE_NOT_YET_VALID", "MANDATE_SUSPENDED", "MERCHANT_NOT_AUTHORIZED",
    "DELEGATION_CYCLE", "APPROVAL_INVALID", "POLICY_INPUT_UNVERIFIABLE", "RISK_REVIEW_REQUIRED",
]


def _rar_problem(details: list, req: dict) -> str | None:
    """A token may carry a narrower grant than the mandate (RFC 9396). The request must fit inside it as well as inside the mandate."""
    action = req["action"]
    cover = [d for d in details if action in d.get("actions", [])]
    if not cover:
        return f"The token's authorization_details do not include {action}"
    acct = req.get("account_id")
    if acct and not any(acct in d.get("accounts", []) for d in cover):
        return f"Account {acct} is outside the token's authorization_details"
    if action in taxonomy.MONEY_MOVING:
        caps = [d["maximum_amount"]["amount_minor"] for d in cover if d.get("maximum_amount")]
        if caps and (req.get("amount_minor") is None or req["amount_minor"] > max(caps)):
            return f"Amount {req.get('amount_minor')} exceeds the maximum {max(caps)} in the token's authorization_details"
        if req.get("counterparty_kind") == "beneficiary" and all("beneficiaries" in d for d in cover) \
                and not any(req.get("counterparty_id") in d["beneficiaries"] for d in cover):
            return f"Beneficiary {req.get('counterparty_id')} is outside the token's authorization_details"
    return None


# --------------------------------------------------------------------------- compiled runtime policy


@lru_cache(maxsize=2048)
def _runtime_cached(digest: str, content_json: str) -> dict:
    import json

    m = json.loads(content_json)
    by_action: dict[str, list[dict]] = {}
    for p in m["permissions"]:
        c = p["constraints"]
        by_action.setdefault(p["action"], []).append(
            {
                "resources": frozenset(p["resources"]),
                "max_amount": c.get("maximum_amount_minor"),
                "currency": c.get("currency") or m["currency"],
                "beneficiaries": frozenset(c.get("allowed_beneficiaries", [])),
                "merchants": frozenset(c.get("allowed_merchants", [])),
                "categories": frozenset(c.get("allowed_merchant_categories", [])),
                "countries": frozenset(c.get("allowed_countries", [])),
                "destinations": frozenset(c.get("allowed_destination_accounts", [])),
            }
        )
    return {
        "mandate_id": m["mandate_id"], "version": m["version"], "mandate_digest": digest,
        "ontology_version": m["ontology_version"], "policy_version": m["policy_version"], "purpose": m["purpose"],
        "currency": m["currency"], "by_action": by_action, "prohibitions": frozenset(m["prohibitions"]),
        "aggregate": m["aggregate_constraints"], "obligations": m["obligations"], "delegation": m["delegation"],
        "not_before": m["validity"]["not_before"], "expires_at": m["validity"]["expires_at"],
        "tz": m["validity"]["budget_timezone"], "principal_id": m["principal"]["id"], "agent_id": m["mandatary"]["agent_id"],
        "client_id": m["mandatary"]["client_id"], "lineage": m.get("lineage"),
    }


def runtime_policy(content: dict, digest: str | None = None) -> dict:
    return _runtime_cached(digest or canon.digest(content), canon.canonical(content).decode())


# --------------------------------------------------------------------------- calendar windows


def window_bounds(now: datetime, tz_name: str) -> dict[str, tuple[datetime, datetime]]:
    """Calendar day and month in the mandate's budget timezone, returned as UTC instants."""
    tz = ZoneInfo(tz_name)
    local = now.astimezone(tz)
    day0 = local.replace(hour=0, minute=0, second=0, microsecond=0)
    day1 = (day0 + timedelta(days=1)).replace(hour=0, minute=0)  # wall-clock midnight (DST safe)
    month0 = day0.replace(day=1)
    month1 = (month0.replace(day=28) + timedelta(days=4)).replace(day=1)
    utc = ZoneInfo("UTC")
    return {k: (a.astimezone(utc), b.astimezone(utc)) for k, (a, b) in {"day": (day0, day1), "month": (month0, month1)}.items()}


# --------------------------------------------------------------------------- evaluation


class _Trace:
    def __init__(self):
        self.items: list[dict] = []
        self.fail_codes: list[str] = []
        self.refer = False
        self.need_approval = False
        self.approvals_required = 0
        self.rar_problem: str | None = None

    def add(self, cid: str, name: str, outcome: str, detail: str, code: str | None = None, rule: str | None = None):
        self.items.append({"id": cid, "name": name, "outcome": outcome, "detail": detail, "reason_code": code, "rule": rule})
        if outcome == "FAIL" and code and code not in self.fail_codes:
            self.fail_codes.append(code)

    def ok(self, cid, name, detail, rule=None):
        self.add(cid, name, "PASS", detail, None, rule)

    def fail(self, cid, name, code, detail, rule=None):
        self.add(cid, name, "FAIL", detail, code, rule)

    def skip(self, cid, name, detail):
        self.add(cid, name, "SKIP", detail)


def _eval_permissions(t: _Trace, label: str, rt: dict, req: dict, mandate_status: str) -> None:
    action = req["action"]
    cid = f"{label}"
    if action in rt["prohibitions"]:
        t.fail(f"{cid}.prohibition", f"{label}: explicit prohibition", "ACTION_NOT_AUTHORIZED",
               f"{action} is explicitly prohibited; prohibitions override any permission", "explicit_prohibition_overrides_permission")
        return
    t.ok(f"{cid}.prohibition", f"{label}: explicit prohibition", f"{action} is not prohibited", "explicit_prohibition_overrides_permission")
    perms = rt["by_action"].get(action, [])
    if not perms:
        t.fail(f"{cid}.action", f"{label}: action permitted", "ACTION_NOT_AUTHORIZED",
               f"No permission for exact action {action}. Related actions grant nothing (no implicit inheritance).", "deny_by_default")
        return
    t.ok(f"{cid}.action", f"{label}: action permitted", f"Permission exists for exact action {action}", "exact_action_match")
    acct = req.get("account_id")
    cands = [p for p in perms if acct in p["resources"]]
    if not cands:
        t.fail(f"{cid}.resource", f"{label}: resource in scope", "RESOURCE_NOT_AUTHORIZED",
               f"Account {acct} is not listed for {action} (listed: {sorted(set().union(*[p['resources'] for p in perms]))})", "resource_scoping")
        return
    t.ok(f"{cid}.resource", f"{label}: resource in scope", f"Account {acct} is covered", "resource_scoping")

    money_moving = action in taxonomy.MONEY_MOVING
    first_failures: list[tuple] | None = None
    for p in sorted(cands, key=lambda p: sorted(p["resources"])):
        fails: list[tuple] = []
        if money_moving:
            if req.get("currency") != p["currency"] or req.get("currency") != rt["currency"]:
                fails.append(("CURRENCY_NOT_AUTHORIZED", f"{req.get('currency')} is not the mandate currency {rt['currency']}"))
            amount = req.get("amount_minor")
            if p["max_amount"] is None:
                fails.append(("TRANSACTION_LIMIT_EXCEEDED", "Permission carries no maximum amount; money-moving authority must be bounded"))
            elif amount is None or amount > p["max_amount"]:
                fails.append(("TRANSACTION_LIMIT_EXCEEDED", f"Amount {amount} exceeds per-transaction maximum {p['max_amount']}"))
            kind = req.get("counterparty_kind")
            cp = req.get("counterparty_id")
            if action == "transfers.execute" and kind == "account":
                if cp not in p["destinations"]:
                    fails.append(("BENEFICIARY_NOT_AUTHORIZED", f"Destination account {cp} is not authorized"))
            elif kind == "beneficiary":
                if cp not in p["beneficiaries"]:
                    fails.append(("BENEFICIARY_NOT_AUTHORIZED", f"Beneficiary {cp} is not in the mandate's allowed beneficiaries"))
            elif kind == "merchant":
                if cp not in p["merchants"] and req.get("counterparty_category") not in p["categories"]:
                    fails.append(("MERCHANT_NOT_AUTHORIZED", f"Merchant {cp} (category {req.get('counterparty_category')}) is not authorized"))
            else:
                fails.append(("BENEFICIARY_NOT_AUTHORIZED", "No identifiable counterparty"))
            if p["countries"] and req.get("counterparty_country") not in p["countries"]:
                fails.append(("BENEFICIARY_NOT_AUTHORIZED", f"Counterparty country {req.get('counterparty_country')} is outside allowed countries"))
        if not fails:
            t.ok(f"{cid}.constraints", f"{label}: permission constraints",
                 "Currency, amount and counterparty satisfy a matching permission" if money_moving else "No financial constraints apply to this action", "constraint_intersection")
            first_failures = None
            break
        if first_failures is None:
            first_failures = fails
    if first_failures:
        for code, detail in first_failures:
            t.fail(f"{cid}.constraints", f"{label}: permission constraints", code, detail, "constraint_intersection")

    if req.get("purpose") is not None or money_moving:
        if req.get("purpose") != rt["purpose"]:
            t.fail(f"{cid}.purpose", f"{label}: purpose", "PURPOSE_NOT_AUTHORIZED",
                   f"Declared purpose {req.get('purpose')!r} differs from mandate purpose {rt['purpose']!r}. A declared purpose is not proof of intent; binding is enforced through resources, beneficiaries and limits.",
                   "purpose_binding")
        else:
            t.ok(f"{cid}.purpose", f"{label}: purpose", "Declared purpose matches the mandate (observable details are enforced separately)", "purpose_binding")


def _eval_limits(t: _Trace, label: str, rt: dict, req: dict, usage: dict) -> None:
    amount = req.get("amount_minor") or 0
    agg = rt["aggregate"]
    u = usage.get(rt["mandate_id"], {"day_minor": 0, "month_minor": 0, "month_count": 0})
    if agg.get("maximum_daily_amount_minor") is not None:
        lim = agg["maximum_daily_amount_minor"]
        if u["day_minor"] + amount > lim:
            t.fail(f"{label}.daily", f"{label}: daily budget", "DAILY_LIMIT_EXCEEDED",
                   f"Consumed {u['day_minor']} (executed + reserved) + {amount} > daily limit {lim}", "aggregate_budget")
        else:
            t.ok(f"{label}.daily", f"{label}: daily budget", f"{u['day_minor']} + {amount} ≤ {lim}", "aggregate_budget")
    if agg.get("maximum_monthly_amount_minor") is not None:
        lim = agg["maximum_monthly_amount_minor"]
        if u["month_minor"] + amount > lim:
            t.fail(f"{label}.monthly", f"{label}: monthly budget", "MONTHLY_LIMIT_EXCEEDED",
                   f"Consumed {u['month_minor']} (executed + reserved) + {amount} > monthly limit {lim}", "aggregate_budget")
        else:
            t.ok(f"{label}.monthly", f"{label}: monthly budget", f"{u['month_minor']} + {amount} ≤ {lim}", "aggregate_budget")
    if agg.get("maximum_transaction_count_monthly") is not None:
        lim = agg["maximum_transaction_count_monthly"]
        if u["month_count"] + 1 > lim:
            t.fail(f"{label}.count", f"{label}: transaction count", "MONTHLY_LIMIT_EXCEEDED", f"{u['month_count']} + 1 > {lim}", "aggregate_budget")
        else:
            t.ok(f"{label}.count", f"{label}: transaction count", f"{u['month_count']} + 1 ≤ {lim}", "aggregate_budget")


def evaluate(inputs: dict) -> dict:
    t = _Trace()
    req = inputs["request"]
    now = clock.parse(req["now"])
    action = req["action"]
    pol = inputs["bank_policy"]
    money_moving = action in taxonomy.MONEY_MOVING

    if not taxonomy.is_known(action):
        t.fail("request.action", "Known action", "ACTION_NOT_AUTHORIZED", f"Unknown action {action}", "deny_by_default")
        return _finish(t, inputs)
    if money_moving:
        a = req.get("amount_minor")
        if isinstance(a, bool) or not isinstance(a, int) or a <= 0:
            t.fail("request.amount", "Valid amount", "TRANSACTION_LIMIT_EXCEEDED", "Amount must be a positive integer in minor units")
        else:
            t.ok("request.amount", "Valid amount", f"{a} minor units")

    # 1. OAuth token: technical permission only.
    tok = inputs.get("token") or {}
    if not tok.get("present"):
        t.fail("token.present", "OAuth access token", "INVALID_TOKEN", "No verified access token")
    else:
        if tok.get("signature_valid") and not tok.get("expired") and not tok.get("revoked"):
            t.ok("token.valid", "Token signature, expiry and revocation", "Token is cryptographically valid, unexpired and not revoked (technical permission only)")
        else:
            t.fail("token.valid", "Token signature, expiry and revocation", "INVALID_TOKEN",
                   f"signature_valid={tok.get('signature_valid')} expired={tok.get('expired')} revoked={tok.get('revoked')}")
        if tok.get("audience_ok"):
            t.ok("token.audience", "Token audience", "Audience is this bank API")
        else:
            t.fail("token.audience", "Token audience", "INVALID_TOKEN", "Token audience is not this resource server (resource indicator mismatch)")
        if tok.get("dpop_ok"):
            t.ok("token.binding", "Sender constraint (DPoP)", tok.get("dpop_detail", "Proof of possession verified"))
        else:
            t.fail("token.binding", "Sender constraint (DPoP)", "INVALID_TOKEN", tok.get("dpop_detail", "Proof of possession missing or invalid"))
        if tok.get("actor_ok"):
            t.ok("token.actor", "Actor binding", "act.sub and client_id match the registered agent for this client")
        else:
            t.fail("token.actor", "Actor binding", "INVALID_ACTOR_BINDING", tok.get("actor_detail", "Token actor does not match the registered agent"))
        needed = taxonomy.scope_for(action) if taxonomy.is_known(action) else None
        if needed is None:
            t.skip("token.scope", "OAuth scope", "Action has no bank-API scope")
        elif needed in tok.get("scopes", []):
            t.ok("token.scope", "OAuth scope", f"Scope {needed} present (scopes cannot express account, beneficiary, amount or purpose)")
        else:
            t.fail("token.scope", "OAuth scope", "TOKEN_SCOPE_INSUFFICIENT", f"Scope {needed} not granted")
        if needed is not None and "rar" in tok:
            # Judged last (see _finish): it only bites when the token is narrower than the mandate, so a mandate denial stays the primary reason.
            t.rar_problem = _rar_problem(tok["rar"], req)

    # 2. Customer identity and authority over the resource (evaluated independently).
    cust = inputs.get("customer")
    if not cust or cust.get("kyc_status") != "VERIFIED":
        t.fail("customer.verified", "Customer identity verified", "CUSTOMER_NOT_VERIFIED", "Customer identity is not verified")
    else:
        t.ok("customer.verified", "Customer identity verified", "Identity verification is VERIFIED (simulated KYC)")
    acct = inputs.get("account")
    if req.get("account_id"):
        if not acct:
            t.fail("account.exists", "Account exists", "RESOURCE_NOT_AUTHORIZED", "Account not found")
        else:
            if not acct.get("controlled_by_principal"):
                t.fail("account.authority", "Customer authority over resource", "RESOURCE_NOT_AUTHORIZED",
                       "The principal does not own or hold signing authority over this account; authority cannot be delegated")
            else:
                t.ok("account.authority", "Customer authority over resource", "Principal controls the account (identity and authority are evaluated separately)")
            if acct.get("status") != "OPEN" or acct.get("restrictions"):
                t.fail("account.restrictions", "Operational restrictions", "ACCOUNT_RESTRICTED",
                       f"Account status {acct.get('status')}, restrictions {acct.get('restrictions')}")
            else:
                t.ok("account.restrictions", "Operational restrictions", "Account is open without restrictions")
    if cust and cust.get("restrictions"):
        t.fail("customer.restrictions", "Customer restrictions", "ACCOUNT_RESTRICTED", f"Restrictions: {cust['restrictions']}")

    # 3. Agent registry status and declared capabilities.
    ag = inputs.get("agent")
    if not ag:
        t.fail("agent.registered", "Agent registered", "AGENT_NOT_VERIFIED", "Agent is not in the registry")
    else:
        st = ag.get("status")
        restricted_actions = pol["agents"]["restricted_allowed_actions"]
        if st == "VERIFIED":
            t.ok("agent.status", "Agent status", "VERIFIED")
        elif st == "RESTRICTED" and action in restricted_actions:
            t.ok("agent.status", "Agent status", f"RESTRICTED agents may only use {restricted_actions}")
        elif st in ("SUSPENDED", "REVOKED"):
            t.fail("agent.status", "Agent status", "AGENT_SUSPENDED", f"Agent is {st}")
        else:
            t.fail("agent.status", "Agent status", "AGENT_NOT_VERIFIED", f"Agent status {st} is not eligible for {action}")
        if action in ag.get("capabilities", []):
            t.ok("agent.capability", "Agent registered capability", f"{action} is among the agent's registered capabilities")
        else:
            t.fail("agent.capability", "Agent registered capability", "ACTION_NOT_AUTHORIZED", f"Agent never registered the capability {action}")

    # 4. Mandate lifecycle, version binding, and lineage.
    mnd = inputs.get("mandate")
    chain = inputs.get("chain", [])
    rts: list[tuple[str, dict]] = []
    if not mnd or not mnd.get("found"):
        t.fail("mandate.found", "Mandate found", "MANDATE_NOT_FOUND", "No mandate record for the credential's mandate reference")
    else:
        t.ok("mandate.found", "Mandate found", f"{mnd['content']['mandate_id']} v{mnd['version']}")
        rt = runtime_policy(mnd["content"], mnd["digest"])
        rts.append(("mandate", rt))
        _status_checks(t, "mandate", mnd, rt, now)
        if tok.get("present"):
            if tok.get("mandate_id") != rt["mandate_id"] or tok.get("mandate_version") != rt["version"] or tok.get("mandate_hash") != mnd["digest"]:
                t.fail("mandate.binding", "Credential bound to this mandate version/digest", "MANDATE_VERSION_MISMATCH",
                       f"Token references {tok.get('mandate_id')} v{tok.get('mandate_version')}; current record is {rt['mandate_id']} v{rt['version']} or digest differs")
            elif mnd.get("current_version") is not None and mnd["current_version"] != rt["version"]:
                t.fail("mandate.binding", "Credential bound to this mandate version/digest", "MANDATE_VERSION_MISMATCH", "A newer mandate version exists")
            else:
                t.ok("mandate.binding", "Credential bound to this mandate version/digest", "mandate_id, version and digest match")
        if inputs.get("customer") and rt["principal_id"] != inputs["customer"]["id"]:
            t.fail("mandate.principal", "Mandate principal", "INVALID_ACTOR_BINDING", "Mandate principal differs from token subject")
        if ag and rt["agent_id"] != ag["id"]:
            t.fail("mandate.mandatary", "Mandate mandatary", "INVALID_ACTOR_BINDING", "Mandate was granted to a different agent")
        elif ag:
            t.ok("mandate.mandatary", "Mandate mandatary", "Mandate was granted to this agent")
        if rt["policy_version"] != pol["policy_version"]:
            t.add("mandate.policy", "Policy version", "INFO", f"Mandate approved under {rt['policy_version']}; evaluated under {pol['policy_version']}")
        for i, anc in enumerate(chain):
            if anc.get("found") is False:
                t.fail(f"parent{i}.found", f"Parent mandate {i + 1}", "MANDATE_NOT_FOUND", "Parent mandate record missing")
                continue
            art = runtime_policy(anc["content"], anc["digest"])
            rts.append((f"parent{i + 1}", art))
            _status_checks(t, f"parent{i + 1}", anc, art, now, parent=True)
        if mnd["content"].get("lineage") and not chain:
            t.fail("lineage.chain", "Delegation lineage", "MANDATE_NOT_FOUND", "Child mandate without verifiable parent chain")
        agents_in_chain = [r["agent_id"] for _, r in rts]
        if len(set(agents_in_chain)) != len(agents_in_chain):
            t.fail("lineage.cycle", "Delegation cycle", "DELEGATION_CYCLE", "The same agent appears twice in the delegation chain")

    # 5. Action semantics evaluated against every mandate in the chain (intersection).
    if rts:
        for label, rt in rts:
            if action == "mandates.delegate":
                d = rt["delegation"]
                depth_used = 0 if not rt.get("lineage") else rt["lineage"]["depth"]
                if not d["allowed"] or d["maximum_depth"] < 1:
                    t.fail(f"{label}.delegation", f"{label}: delegation permitted", "DELEGATION_NOT_ALLOWED", "Mandate does not allow delegation")
                else:
                    t.ok(f"{label}.delegation", f"{label}: delegation permitted", f"Delegation allowed to depth {d['maximum_depth']} (current depth {depth_used})")
                continue
            _eval_permissions(t, label, rt, req, "ACTIVE")
            if money_moving:
                _eval_limits(t, label, rt, req, inputs.get("usage", {}))
    else:
        t.skip("authority", "Mandate permissions", "No verifiable mandate: nothing can be authorized")

    # 6. Risk (transaction risk is independent of mandate authorization).
    risk = inputs.get("risk")
    if money_moving:
        if not risk:
            t.fail("risk.assessment", "Risk assessment", "POLICY_INPUT_UNVERIFIABLE", "Required risk information unavailable: fail closed")
        else:
            if risk.get("sanctions_hit"):
                t.fail("risk.sanctions", "Synthetic sanctions screening", "RISK_THRESHOLD_EXCEEDED", "Synthetic watch-list match (demo data, not real screening)", "risk_hard_stop")
            if risk["score"] >= pol["risk"]["deny_at"]:
                t.fail("risk.threshold", "Risk threshold", "RISK_THRESHOLD_EXCEEDED", f"Risk score {risk['score']} ≥ deny threshold {pol['risk']['deny_at']}", "risk_threshold")
            elif risk["score"] >= pol["risk"]["review_at"]:
                t.add("risk.threshold", "Risk threshold", "REFER", f"Risk score {risk['score']} ≥ review threshold {pol['risk']['review_at']}", "RISK_REVIEW_REQUIRED", "risk_threshold")
                t.refer = True
            else:
                t.ok("risk.threshold", "Risk threshold", f"Risk score {risk['score']} < review threshold {pol['risk']['review_at']}", "risk_threshold")

    # 7. Human approval obligations (strictest across the lineage and bank policy).
    if money_moving and rts:
        amount = req.get("amount_minor") or 0
        required = 0
        reasons = []
        for label, rt in rts:
            ob = rt["obligations"]
            if ob.get("human_approval_above_minor") is not None and amount > ob["human_approval_above_minor"]:
                required = max(required, ob.get("required_approvals", 1))
                reasons.append(f"{label}: amount {amount} > {ob['human_approval_above_minor']}")
        floor = pol["approval"]["bank_human_approval_above_minor"]
        if amount > floor:
            required = max(required, 1)
            reasons.append(f"bank policy: amount {amount} > {floor}")
        apr = inputs.get("approval") or {}
        if required == 0:
            t.ok("approval.required", "Human approval", "No approval obligation triggered")
        elif apr.get("valid") and apr.get("granted_count", 0) >= required:
            t.ok("approval.required", "Human approval", f"{apr['granted_count']} of {required} required approvals are valid, unexpired, unused and bound to the exact operation hash", "approval_binding")
        else:
            t.need_approval = True
            t.approvals_required = required
            problem = apr.get("problem")
            t.add("approval.required", "Human approval", "REQUIRE_APPROVAL",
                  f"{required} human approval(s) required ({'; '.join(reasons)})" + (f". Supplied approval unusable: {problem}" if problem else ""),
                  "APPROVAL_INVALID" if problem else "HUMAN_APPROVAL_REQUIRED", "approval_binding")

    return _finish(t, inputs)


def _status_checks(t: _Trace, label: str, m: dict, rt: dict, now: datetime, parent: bool = False) -> None:
    st = m.get("status")
    who = "parent mandate" if parent else "mandate"
    if st == "REVOKED":
        t.fail(f"{label}.status", f"{label}: lifecycle status", "MANDATE_REVOKED", f"The {who} is revoked; revocation takes effect immediately even for unexpired tokens", "revocation_checked_every_request")
    elif st == "SUSPENDED":
        t.fail(f"{label}.status", f"{label}: lifecycle status", "MANDATE_SUSPENDED", f"The {who} is suspended")
    elif st == "SUPERSEDED":
        t.fail(f"{label}.status", f"{label}: lifecycle status", "MANDATE_VERSION_MISMATCH", f"The {who} version was superseded by an amendment")
    elif st == "EXPIRED":
        t.fail(f"{label}.status", f"{label}: lifecycle status", "MANDATE_EXPIRED", f"The {who} is expired")
    elif st != "ACTIVE":
        t.fail(f"{label}.status", f"{label}: lifecycle status", "MANDATE_NOT_FOUND", f"The {who} is {st}, not ACTIVE")
    else:
        t.ok(f"{label}.status", f"{label}: lifecycle status", "ACTIVE", "revocation_checked_every_request")
    if clock.parse(rt["expires_at"]) <= now:
        t.fail(f"{label}.validity", f"{label}: validity window", "MANDATE_EXPIRED", f"Expired at {rt['expires_at']}")
    elif clock.parse(rt["not_before"]) > now:
        t.fail(f"{label}.validity", f"{label}: validity window", "MANDATE_NOT_YET_VALID", f"Valid from {rt['not_before']}")
    else:
        t.ok(f"{label}.validity", f"{label}: validity window", f"{rt['not_before']} ≤ now < {rt['expires_at']}")


def _finish(t: _Trace, inputs: dict) -> dict:
    if t.rar_problem and not t.fail_codes:
        t.fail("token.rar", "Token's own authorization_details", "TOKEN_SCOPE_INSUFFICIENT", t.rar_problem)
    elif not t.rar_problem and "rar" in (inputs.get("token") or {}) and not t.fail_codes:
        t.ok("token.rar", "Token's own authorization_details", "The request is within the authority the agent asked for when it obtained this token")
    if t.fail_codes:
        decision = "DENY"
    elif t.refer:
        decision = "REFER_TO_RISK_REVIEW"
    elif t.need_approval:
        decision = "REQUIRE_HUMAN_APPROVAL"
    else:
        decision = "ALLOW"
    codes = list(t.fail_codes)
    if decision == "REFER_TO_RISK_REVIEW":
        codes = ["RISK_REVIEW_REQUIRED"]
    if decision == "REQUIRE_HUMAN_APPROVAL":
        problem = (inputs.get("approval") or {}).get("problem")
        codes = ["APPROVAL_INVALID", "HUMAN_APPROVAL_REQUIRED"] if problem else ["HUMAN_APPROVAL_REQUIRED"]
    return {
        "decision": decision,
        "reason_codes": codes,
        "trace": t.items,
        "approvals_required": t.approvals_required,
        "policy_version": inputs["bank_policy"]["policy_version"],
        "passed": sum(1 for i in t.items if i["outcome"] == "PASS"),
        "failed": sum(1 for i in t.items if i["outcome"] == "FAIL"),
    }


def replay(inputs: dict) -> dict:
    """Re-run a stored decision snapshot through the same engine. Used for historical reconstruction."""
    return evaluate(inputs)


# --------------------------------------------------------------------------- delegation attenuation


def attenuation_violations(parent: dict, child: dict, chain_agent_ids: list[str] | None = None) -> list[dict]:
    """A child mandate must never widen the parent. Returns violations (empty list means attenuated)."""
    v: list[dict] = []

    def bad(code: str, dim: str, detail: str):
        v.append({"code": code, "dimension": dim, "detail": detail})

    pd, cd = parent["delegation"], child["delegation"]
    if not pd["allowed"] or pd["maximum_depth"] < 1:
        bad("DELEGATION_NOT_ALLOWED", "delegation", "Parent mandate does not allow delegation")
    if cd["maximum_depth"] > max(pd["maximum_depth"] - 1, 0):
        bad("DELEGATION_EXCEEDS_PARENT", "delegation_depth", f"child depth {cd['maximum_depth']} > parent remaining depth {max(pd['maximum_depth'] - 1, 0)}")
    if child["principal"] != parent["principal"]:
        bad("DELEGATION_EXCEEDS_PARENT", "principal", "Child must act for the same principal")
    if child["purpose"] != parent["purpose"]:
        bad("DELEGATION_EXCEEDS_PARENT", "purpose", "Child purpose must equal parent purpose")
    if child["currency"] != parent["currency"]:
        bad("DELEGATION_EXCEEDS_PARENT", "currency", "Child currency differs")
    ids = chain_agent_ids if chain_agent_ids is not None else [parent["mandatary"]["agent_id"]]
    if child["mandatary"]["agent_id"] in ids:
        bad("DELEGATION_CYCLE", "cycle", f"Agent {child['mandatary']['agent_id']} already appears in the delegation chain")
    for cp in child["permissions"]:
        pperms = [p for p in parent["permissions"] if p["action"] == cp["action"] and set(cp["resources"]) <= set(p["resources"])]
        if not pperms:
            bad("DELEGATION_EXCEEDS_PARENT", "permitted_actions_or_resources", f"Parent grants no {cp['action']} over {cp['resources']}")
            continue
        if not any(_constraints_within(cp["constraints"], p["constraints"]) for p in pperms):
            bad("DELEGATION_EXCEEDS_PARENT", "constraints", f"{cp['action']}: child constraints exceed every matching parent permission")
    if not set(parent["prohibitions"]) <= set(child["prohibitions"]):
        bad("DELEGATION_EXCEEDS_PARENT", "prohibitions", f"Child drops parent prohibitions {sorted(set(parent['prohibitions']) - set(child['prohibitions']))}")
    for k in ("maximum_daily_amount_minor", "maximum_monthly_amount_minor", "maximum_transaction_count_monthly"):
        pv, cv = parent["aggregate_constraints"].get(k), child["aggregate_constraints"].get(k)
        if pv is not None and (cv is None or cv > pv):
            bad("DELEGATION_EXCEEDS_PARENT", k, f"child {cv} exceeds parent {pv}")
    po, co = parent["obligations"], child["obligations"]
    if po.get("human_approval_above_minor") is not None and (
        co.get("human_approval_above_minor") is None or co["human_approval_above_minor"] > po["human_approval_above_minor"]
    ):
        bad("DELEGATION_EXCEEDS_PARENT", "human_approval", "Child weakens the human-approval threshold")
    if co.get("required_approvals", 1) < po.get("required_approvals", 1):
        bad("DELEGATION_EXCEEDS_PARENT", "required_approvals", "Child reduces required approvers")
    pv, cv = parent["validity"], child["validity"]
    if clock.parse(cv["not_before"]) < clock.parse(pv["not_before"]) or clock.parse(cv["expires_at"]) > clock.parse(pv["expires_at"]):
        bad("DELEGATION_EXCEEDS_PARENT", "temporal_validity", "Child validity must lie within parent validity")
    if cv["budget_timezone"] != pv["budget_timezone"]:
        bad("DELEGATION_EXCEEDS_PARENT", "budget_timezone", "Budget timezone differs")
    if not set(child["jurisdictions"]) <= set(parent["jurisdictions"]):
        bad("DELEGATION_EXCEEDS_PARENT", "geographic_restrictions", "Child adds jurisdictions")
    return v


def _constraints_within(c: dict, p: dict) -> bool:
    if p.get("maximum_amount_minor") is not None and (c.get("maximum_amount_minor") is None or c["maximum_amount_minor"] > p["maximum_amount_minor"]):
        return False
    for k in ("allowed_beneficiaries", "allowed_merchants", "allowed_merchant_categories", "allowed_countries", "allowed_destination_accounts"):
        pv = set(p.get(k) or [])
        cv = set(c.get(k) or [])
        if pv and not cv <= pv:
            return False
        if pv and not cv:
            return False
    if p.get("currency") and c.get("currency") and p["currency"] != c["currency"]:
        return False
    return True


def effective_permissions(mandate: dict, *, controlled_accounts: set[str], agent_capabilities: set[str], agent_status: str, policy: dict) -> list[dict]:
    """Studio view: each mandate permission intersected with customer authority, agent capabilities and bank policy."""
    out = []
    for p in mandate["permissions"]:
        limits = []
        reasons = []
        res_ok = [r for r in p["resources"] if r in controlled_accounts]
        if len(res_ok) != len(p["resources"]):
            reasons.append("Customer does not control: " + ", ".join(sorted(set(p["resources"]) - set(res_ok))))
        if p["action"] not in agent_capabilities:
            reasons.append("Agent has not registered this capability")
        if agent_status not in ("VERIFIED",) and not (agent_status == "RESTRICTED" and p["action"] in policy["agents"]["restricted_allowed_actions"]):
            reasons.append(f"Agent status {agent_status}")
        if p["action"] in taxonomy.MONEY_MOVING:
            cap = policy["limits"]["max_single_payment_minor"]
            mx = p["constraints"].get("maximum_amount_minor")
            eff = min(mx, cap) if mx else cap
            limits.append(f"max per transaction {eff} (bank cap {cap})")
            if mx and mx > cap:
                reasons.append(f"Exceeds bank per-payment cap {cap}")
        out.append({"action": p["action"], "resources": res_ok, "effective": not reasons, "limits": limits, "narrowed_by": reasons})
    return out
