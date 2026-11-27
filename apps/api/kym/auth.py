"""Demo role-based sessions for the bank/admin/customer UI. DEMO ONLY: no passwords, no passkeys.

Production: OIDC login with passkeys (WebAuthn) and step-up authentication for approvals.
"""
from __future__ import annotations

import time

import jwt
from fastapi import Depends, Header, HTTPException

from . import config, kyc

DEMO_USERS = {
    "admin_001": {"role": "admin", "name": "Meridian Bank Operator"},
    "investigator_001": {"role": "investigator", "name": "Dispute Investigator"},
    "customer_001": {"role": "customer", "name": "Alice Tremblay"},
    "customer_002": {"role": "customer", "name": "Ben Carter"},
    "customer_003": {"role": "customer", "name": "Priya Nair (Northwind signatory)"},
    "customer_004": {"role": "customer", "name": "Jordan Lee (Northwind signatory)"},
    "customer_005": {"role": "customer", "name": "Sam Ortiz (Northwind treasury analyst, no signing authority)"},
    "business_001": {"role": "customer", "name": "Northwind Supply Inc. (business principal)"},
}
ISS = "kym-demo-session"


def login(user_id: str) -> str:
    if not config.is_demo():
        raise PermissionError("demo sessions are disabled when KYM_ENV != demo; integrate OIDC with passkeys")
    if user_id not in DEMO_USERS:
        raise KeyError(user_id)
    now = int(time.time())
    return jwt.encode({"iss": ISS, "sub": user_id, "role": DEMO_USERS[user_id]["role"], "iat": now, "exp": now + 8 * 3600}, config.session_secret(), algorithm="HS256")


class User:
    def __init__(self, id: str, role: str):
        self.id, self.role = id, role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def current_user(authorization: str | None = Header(default=None)) -> User:
    if not config.is_demo():
        raise HTTPException(503, "demo authentication disabled outside KYM_ENV=demo")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "demo session required (POST /api/session)")
    try:
        c = jwt.decode(authorization.split(None, 1)[1], config.session_secret(), algorithms=["HS256"], issuer=ISS)
    except jwt.PyJWTError as e:
        raise HTTPException(401, "invalid demo session") from e
    return User(c["sub"], c["role"])


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"role {user.role} may not perform this operation")
        return user
    return dep


def assert_can_act_for(s, user: User, principal_id: str) -> None:
    """Resource-level authorization: customers may only act for themselves or businesses they are signatories for."""
    if user.role in ("admin", "investigator"):
        return
    if not kyc.can_act_for(s, user.id, principal_id):
        raise HTTPException(403, "cross-customer access denied")

