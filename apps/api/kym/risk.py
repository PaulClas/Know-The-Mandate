"""Know Your Transaction: configurable, explainable SYNTHETIC risk engine.

Not a real AML, fraud or sanctions screening system. Risk is independent of mandate authorization:
a transaction can be authorized by the customer yet rejected by bank risk controls, or low risk but
outside the mandate. No score here can override an explicit prohibition (the PDP checks those first).
"""
from __future__ import annotations

from statistics import mean

DISCLAIMER = "Synthetic risk signals for demonstration. Not real AML/KYT, fraud or sanctions screening."


def assess(ctx: dict, policy: dict) -> dict:
    """ctx: amount_minor, payee{id,kind,country,category,watchlist}, customer_country, history_amounts[],
    known_payee_ids[], recent_payments[{at_minutes_ago, amount_minor}], approval_threshold_minor, auth_failures,
    agent_incidents (int)."""
    w = policy["risk"]["weights"]
    prm = policy["risk"]["parameters"]
    signals = []

    def sig(sid: str, triggered: bool, points: int, detail: str):
        signals.append({"id": sid, "triggered": triggered, "points": points if triggered else 0, "detail": detail})

    amt = ctx["amount_minor"]
    hist = [a for a in ctx.get("history_amounts", []) if a > 0]
    if len(hist) >= 3:
        avg = mean(hist)
        trig = amt > avg * prm["amount_anomaly_multiple"]
        sig("amount_anomaly", trig, w["amount_anomaly"], f"Amount {amt} vs historical mean {int(avg)} (threshold ×{prm['amount_anomaly_multiple']})")
    else:
        sig("amount_anomaly", False, 0, "Insufficient history to establish a baseline")

    payee = ctx["payee"]
    known = payee["id"] in ctx.get("known_payee_ids", [])
    if payee["kind"] == "merchant":
        sig("new_merchant", not known, w["new_merchant"], "First payment to this merchant" if not known else "Merchant previously used")
        sig("unusual_beneficiary", False, 0, "Evaluated as merchant")
    else:
        sig("unusual_beneficiary", not known, w["unusual_beneficiary"], "Principal has never paid this beneficiary" if not known else "Beneficiary previously paid")
        sig("new_merchant", False, 0, "Not a merchant")

    window = prm["velocity_window_minutes"]
    recent = [p for p in ctx.get("recent_payments", []) if p["minutes_ago"] <= window]
    sig("velocity", len(recent) >= prm["velocity_max_payments"], w["velocity"], f"{len(recent)} payments in the last {window} minutes (max {prm['velocity_max_payments']})")

    home = ctx.get("customer_country", "CA")
    sig("geographic_mismatch", payee["country"] != home, w["geographic_mismatch"], f"Counterparty country {payee['country']} vs customer country {home}")

    thr = ctx.get("approval_threshold_minor")
    pattern = False
    if thr:
        low = thr * (100 - prm["structuring_band_percent"]) // 100
        in_band = low <= amt <= thr
        similar = [p for p in ctx.get("recent_payments", []) if low <= p["amount_minor"] <= thr and p["minutes_ago"] <= 1440]
        pattern = in_band and len(similar) >= 1
    sig("suspicious_pattern", pattern, w["suspicious_pattern"], "Repeated amounts just under the approval threshold" if pattern else "No threshold-hugging pattern")

    af = ctx.get("auth_failures", 0)
    sig("repeated_auth_failures", af >= prm["auth_failure_threshold"], w["repeated_auth_failures"], f"{af} denied requests by this agent recently (threshold {prm['auth_failure_threshold']})")

    inc = ctx.get("agent_incidents", 0)
    sig("agent_incident_history", inc > 0, min(w["agent_incident_history"], inc * 5), f"{inc} recorded agent incidents")

    sanctions = bool(payee.get("watchlist"))
    sig("synthetic_sanctions_match", sanctions, 100, "Counterparty is on the SYNTHETIC watch list" if sanctions else "No synthetic watch-list match")

    score = min(100, sum(s["points"] for s in signals))
    return {
        "score": score,
        "level": "HIGH" if score >= policy["risk"]["deny_at"] else "ELEVATED" if score >= policy["risk"]["review_at"] else "LOW",
        "signals": signals,
        "sanctions_hit": sanctions,
        "thresholds": {"review_at": policy["risk"]["review_at"], "deny_at": policy["risk"]["deny_at"]},
        "disclaimer": DISCLAIMER,
    }
