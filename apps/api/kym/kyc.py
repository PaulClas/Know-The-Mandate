"""Simulated Know Your Customer. Synthetic data only; NOT a real AML / customer-due-diligence process.

Identity verification and authority over a financial resource are evaluated independently.
"""
from __future__ import annotations

from sqlalchemy import select

from . import db


def identity_verified(s, customer_id: str) -> bool:
    c = s.get(db.Customer, customer_id)
    return bool(c and c.kyc_status == "VERIFIED" and not c.restrictions)


def controls_account(s, customer_id: str, account_id: str) -> bool:
    """True when the customer owns the account, or is the business itself (accounts owned by the business)."""
    a = s.get(db.Account, account_id)
    return bool(a and a.owner_id == customer_id)


def signatories(s, business_id: str, account_id: str | None = None) -> list[str]:
    rows = s.execute(select(db.Representative).where(db.Representative.business_id == business_id, db.Representative.can_sign.is_(True))).scalars()
    return [r.person_id for r in rows if account_id is None or account_id in r.account_ids]


def can_act_for(s, user_id: str, principal_id: str) -> bool:
    """User is the principal, or an authorized representative with signing authority for the business principal."""
    if user_id == principal_id:
        return True
    return user_id in signatories(s, principal_id)


def controlled_accounts(s, customer_id: str) -> set[str]:
    return {a.id for a in s.execute(select(db.Account).where(db.Account.owner_id == customer_id)).scalars()}
