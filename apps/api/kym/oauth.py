"""Sandbox OAuth 2.0 / OIDC authorization server for KYM.

CLEARLY LABELLED SANDBOX ADAPTER. It is built on maintained libraries (PyJWT, cryptography) for all
signing and verification, but the protocol endpoints are a minimal in-process implementation, not a
certified FAPI 2.0 server. Production deployments should use a maintained authorization server
(e.g. Keycloak, ORY Hydra, Authlib-based, or a commercial FAPI-certified product) and keep KYM as the
mandate/policy layer.

Implemented (sandbox): authorization code + PKCE (S256), PAR (RFC 9126, simplified), confidential client
authentication (client_secret_post/basic), RFC 9396 authorization_details validation against the approved
mandate, DPoP proof validation (RFC 9449), JWT access tokens (RFC 9068-style, ES256), introspection
(RFC 7662), revocation (RFC 7009), token exchange (RFC 8693, simplified `act` chain), OIDC id_token.
Not implemented: mTLS (RFC 8705), refresh tokens, JARM, request objects, dynamic client registration.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import jwt
from sqlalchemy import delete, select

from . import agents as agents_mod
from . import clock, config, db, keys, kyc, ledger, mandates, taxonomy
from .canon import b64u

RAR_TYPE = "kym_financial_mandate"
GRANT_TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
PAR_TTL = 90
CODE_TTL = 60


class OAuthError(Exception):
    def __init__(self, error: str, description: str, status: int = 400):
        super().__init__(description)
        self.error, self.description, self.status = error, description, status

    def body(self) -> dict:
        return {"error": self.error, "error_description": self.description}


class TokenInvalid(Exception):
    """Token cannot be trusted at all (bad signature / malformed). PEP answers 401 without evaluating policy."""


# --------------------------------------------------------------------------- client authentication


def authenticate_client(s, client_id: str | None, client_secret: str | None) -> db.Agent:
    if not client_id or not client_secret:
        raise OAuthError("invalid_client", "confidential client authentication required", 401)
    a = s.execute(select(db.Agent).where(db.Agent.client_id == client_id)).scalar_one_or_none()
    if not a or not agents_mod.check_secret(client_secret, a.client_secret_hash):
        raise OAuthError("invalid_client", "client authentication failed", 401)
    if a.status not in ("VERIFIED", "RESTRICTED"):
        raise OAuthError("unauthorized_client", f"client agent status is {a.status}", 403)
    return a


# --------------------------------------------------------------------------- RFC 9396 authorization_details


def validate_rar(details) -> list[dict]:
    if not isinstance(details, list) or not details:
        raise OAuthError("invalid_authorization_details", "authorization_details must be a non-empty array")
    for d in details:
        if not isinstance(d, dict) or d.get("type") != RAR_TYPE:
            raise OAuthError("invalid_authorization_details", f"unsupported authorization_details type {d.get('type') if isinstance(d, dict) else d!r}")
        for k in ("actions", "mandate_id", "mandate_version", "accounts"):
            if k not in d:
                raise OAuthError("invalid_authorization_details", f"missing {k}")
        if not all(taxonomy.is_known(a) for a in d["actions"]):
            raise OAuthError("invalid_authorization_details", "unknown action")
        if isinstance(d["mandate_version"], bool) or not isinstance(d["mandate_version"], int):
            raise OAuthError("invalid_authorization_details", "mandate_version must be an integer")
    return details


def _rar_within_mandate(details: list[dict], content: dict) -> None:
    """Requested authority must be a subset of the approved mandate; the AS never trusts client-supplied authority."""
    for d in details:
        if d["mandate_id"] != content["mandate_id"] or d["mandate_version"] != content["version"]:
            raise OAuthError("invalid_authorization_details", "mandate reference mismatch")
        for action in d["actions"]:
            perms = [p for p in content["permissions"] if p["action"] == action]
            if not perms:
                raise OAuthError("invalid_authorization_details", f"mandate does not permit {action}")
            allowed_acc = set().union(*[set(p["resources"]) for p in perms])
            if not set(d["accounts"]) <= allowed_acc:
                raise OAuthError("invalid_authorization_details", f"accounts exceed the mandate for {action}")
            if "maximum_amount" in d and perms[0]["constraints"].get("maximum_amount_minor"):
                cap = max(p["constraints"].get("maximum_amount_minor") or 0 for p in perms)
                if d["maximum_amount"]["amount_minor"] > cap:
                    raise OAuthError("invalid_authorization_details", "maximum_amount exceeds the mandate")
            if "beneficiaries" in d:
                allowed_b = set().union(*[set(p["constraints"].get("allowed_beneficiaries", [])) for p in content["permissions"]])
                if not set(d["beneficiaries"]) <= allowed_b:
                    raise OAuthError("invalid_authorization_details", "beneficiaries exceed the mandate")


# --------------------------------------------------------------------------- PAR + authorization


def pushed_authorization_request(s, client: db.Agent, params: dict) -> dict:
    if params.get("response_type") != "code":
        raise OAuthError("unsupported_response_type", "only response_type=code")
    if params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
        raise OAuthError("invalid_request", "PKCE with S256 is required")
    resource = params.get("resource")
    if resource != config.API_AUDIENCE:
        raise OAuthError("invalid_target", f"resource must be {config.API_AUDIENCE} (RFC 8707)")
    details = validate_rar(params.get("authorization_details"))
    mid, mver = details[0]["mandate_id"], details[0]["mandate_version"]
    if any(d["mandate_id"] != mid or d["mandate_version"] != mver for d in details):
        raise OAuthError("invalid_authorization_details", "one mandate per authorization request")
    try:
        row = mandates.get_row(s, mid, mver)
    except mandates.MandateError as e:
        raise OAuthError("invalid_authorization_details", "unknown mandate") from e
    if mandates.get_state(s, mid, mver).status != "ACTIVE":
        raise OAuthError("access_denied", "mandate is not ACTIVE")
    if row.content["mandatary"]["client_id"] != client.client_id:
        raise OAuthError("unauthorized_client", "this client is not the mandatary of the mandate")
    _rar_within_mandate(details, row.content)
    request_uri = f"urn:ietf:params:oauth:request_uri:{uuid.uuid4().hex}"
    s.add(db.OAuthRequest(request_uri=request_uri, client_id=client.client_id, params={**params, "authorization_details": details}, expires_at=_plus(PAR_TTL), status="PENDING"))
    s.flush()
    return {"request_uri": request_uri, "expires_in": PAR_TTL}


def _plus(seconds: int) -> str:
    return clock.iso(clock.now() + timedelta(seconds=seconds))


def authorize_approve(s, request_uri: str, customer_id: str) -> dict:
    """Bank-hosted consent step: the signed-in customer approves the pushed request. Returns the authorization response."""
    req = s.get(db.OAuthRequest, request_uri)
    if not req or req.status != "PENDING" or clock.parse(req.expires_at) < clock.now():
        raise OAuthError("invalid_request", "unknown, used or expired request_uri")
    d = req.params["authorization_details"][0]
    row = mandates.get_row(s, d["mandate_id"], d["mandate_version"])
    if not kyc.can_act_for(s, customer_id, row.principal_id):
        raise OAuthError("access_denied", "customer is not the mandate principal", 403)
    code = secrets.token_urlsafe(32)
    req.code_hash = hashlib.sha256(code.encode()).hexdigest()
    req.status = "APPROVED"
    req.customer_id = row.principal_id
    req.expires_at = _plus(CODE_TTL)
    s.flush()
    return {"code": code, "state": req.params.get("state"), "iss": config.ISSUER}


# --------------------------------------------------------------------------- DPoP (RFC 9449)


def _normalize_htu(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme.lower()}://{u.netloc.lower()}{u.path}"


def verify_dpop(s, proof: str | None, *, method: str, url: str, access_token: str | None = None, expected_jkt: str | None = None) -> tuple[bool, str, str | None]:
    """Returns (ok, detail, jkt). Validates typ, alg, jwk, signature, htm, htu, iat window, ath, jkt binding and jti replay."""
    if not proof:
        return False, "DPoP proof missing", None
    try:
        header = jwt.get_unverified_header(proof)
    except jwt.PyJWTError:
        return False, "malformed DPoP proof", None
    if header.get("typ") != "dpop+jwt" or header.get("alg") != "ES256" or "jwk" not in header:
        return False, "DPoP header must have typ=dpop+jwt, alg=ES256 and a public jwk", None
    jwk = header["jwk"]
    if jwk.get("kty") != "EC" or "d" in jwk:
        return False, "DPoP jwk must be a public EC key", None
    try:
        claims = jwt.decode(proof, jwt.PyJWK(jwk).key, algorithms=["ES256"], options={"verify_aud": False, "verify_exp": False, "verify_iat": False, "require": ["jti", "htm", "htu", "iat"]})
    except jwt.PyJWTError as e:
        return False, f"DPoP signature/claims invalid: {e}", None
    jkt = agents_mod.jwk_thumbprint(jwk)
    if claims["htm"].upper() != method.upper():
        return False, "DPoP htm does not match request method", jkt
    if _normalize_htu(claims["htu"]) != _normalize_htu(url):
        return False, "DPoP htu does not match request URI", jkt
    if abs(clock.now().timestamp() - claims["iat"]) > 60:
        return False, "DPoP proof iat outside the acceptable window", jkt
    if access_token is not None:
        ath = b64u(hashlib.sha256(access_token.encode()).digest())
        if claims.get("ath") != ath:
            return False, "DPoP ath does not match the access token", jkt
    if expected_jkt is not None and jkt != expected_jkt:
        return False, "DPoP key does not match the token's cnf.jkt", jkt
    if s.get(db.DpopSeen, claims["jti"]):
        return False, "DPoP proof replay detected (jti already used)", jkt
    s.execute(delete(db.DpopSeen).where(db.DpopSeen.seen_at < clock.iso(clock.now() - timedelta(seconds=300))))  # bounded replay cache
    s.add(db.DpopSeen(jti=claims["jti"], seen_at=clock.iso()))
    s.flush()
    return True, "DPoP proof valid and bound to the token key", jkt


# --------------------------------------------------------------------------- token issuance


def _sign(claims: dict, typ: str = "at+jwt") -> str:
    return jwt.encode(claims, keys.as_signing_key(), algorithm="ES256", headers={"kid": keys.AS_KID, "typ": typ})


def _scopes_for(details: list[dict]) -> list[str]:
    return sorted({taxonomy.scope_for(a) for d in details for a in d["actions"] if taxonomy.scope_for(a)})


def _issue(s, *, agent: db.Agent, row: db.MandateRow, details: list[dict], jkt: str | None, actor_chain: dict, ttl: int | None = None, aud: str | None = None,
           scope: list[str] | None = None, correlation_id: str | None = None) -> tuple[str, dict]:
    now = clock.now()
    ttl = config.ACCESS_TOKEN_TTL_SECONDS if ttl is None else ttl
    jti = f"tok_{uuid.uuid4().hex[:16]}"
    scopes = scope if scope is not None else _scopes_for(details)
    claims = {
        "iss": config.ISSUER, "sub": row.principal_id, "aud": aud or config.API_AUDIENCE, "client_id": agent.client_id, "act": actor_chain,
        "scope": " ".join(scopes), "jti": jti, "iat": int(now.timestamp()), "exp": int(now.timestamp()) + ttl,
        "authorization_details": details,
        f"{config.CLAIM_NS}mandate_id": row.mandate_id, f"{config.CLAIM_NS}mandate_version": row.version, f"{config.CLAIM_NS}mandate_hash": row.digest,
    }
    if jkt:
        claims["cnf"] = {"jkt": jkt}
    token = _sign(claims)
    s.add(db.Token(jti=jti, token_hash=hashlib.sha256(token.encode()).hexdigest(), mandate_id=row.mandate_id, mandate_version=row.version, client_id=agent.client_id,
                   sub=row.principal_id, actor=agent.id, scope=claims["scope"], aud=claims["aud"], cnf_jkt=jkt, issued_at=clock.iso(now),
                   expires_at=clock.iso(now + timedelta(seconds=ttl)), authorization_details=details))
    s.flush()
    ledger.append(s, "TOKEN_ISSUED", actor_id="meridian-authorization-server", actor_type="bank_system", principal_id=row.principal_id, agent_id=agent.id, mandate_id=row.mandate_id,
                  mandate_version=row.version, correlation_id=correlation_id, payload={"jti": jti, "scope": claims["scope"], "aud": claims["aud"], "cnf_jkt": jkt, "expires_in": ttl, "token_sha256_prefix": hashlib.sha256(token.encode()).hexdigest()[:12]})
    return token, claims


def token_endpoint(s, params: dict, *, dpop: str | None, url: str, client: db.Agent | None = None) -> dict:
    gt = params.get("grant_type")
    client = client or authenticate_client(s, params.get("client_id"), params.get("client_secret"))
    if gt == "authorization_code":
        return _code_grant(s, client, params, dpop, url)
    if gt == GRANT_TOKEN_EXCHANGE:
        return _token_exchange(s, client, params, dpop, url)
    raise OAuthError("unsupported_grant_type", f"unsupported grant_type {gt}")


def _code_grant(s, client, params, dpop, url) -> dict:
    code = params.get("code") or ""
    ch = hashlib.sha256(code.encode()).hexdigest()
    req = s.execute(select(db.OAuthRequest).where(db.OAuthRequest.code_hash == ch)).scalar_one_or_none()
    if not req or req.client_id != client.client_id:
        raise OAuthError("invalid_grant", "unknown code")
    if req.status != "APPROVED" or clock.parse(req.expires_at) < clock.now():
        req.status = "CODE_USED" if req.status == "APPROVED" else req.status
        raise OAuthError("invalid_grant", "code already used or expired")
    req.status = "CODE_USED"
    verifier = params.get("code_verifier") or ""
    expected = b64u(hashlib.sha256(verifier.encode()).digest())
    if not secrets.compare_digest(expected, req.params["code_challenge"]):
        raise OAuthError("invalid_grant", "PKCE verification failed")
    ok, detail, jkt = verify_dpop(s, dpop, method="POST", url=url)
    if not ok:
        raise OAuthError("invalid_dpop_proof", detail)
    if jkt != agents_mod.jwk_thumbprint(client.public_key_jwk):
        raise OAuthError("invalid_dpop_proof", "DPoP key is not the agent's registered key")
    details = req.params["authorization_details"]
    d0 = details[0]
    row = mandates.get_row(s, d0["mandate_id"], d0["mandate_version"])
    if mandates.get_state(s, row.mandate_id, row.version).status != "ACTIVE":
        raise OAuthError("access_denied", "mandate is no longer active")
    _rar_within_mandate(details, row.content)
    token, claims = _issue(s, agent=client, row=row, details=details, jkt=jkt, actor_chain={"sub": client.id})
    resp = {"access_token": token, "token_type": "DPoP", "expires_in": config.ACCESS_TOKEN_TTL_SECONDS, "scope": claims["scope"], "authorization_details": details}
    if "openid" in (req.params.get("scope") or "").split():
        now = int(clock.now().timestamp())
        resp["id_token"] = _sign({"iss": config.ISSUER, "sub": row.principal_id, "aud": client.client_id, "iat": now, "exp": now + 300, "nonce": req.params.get("nonce"), "auth_time": now, "acr": "demo-simulated"}, typ="JWT")
    return resp


def _token_exchange(s, client, params, dpop, url) -> dict:
    """RFC 8693 (simplified): a delegated child agent exchanges the parent's token for a child-mandate token; `act` nests the chain."""
    subject = params.get("subject_token")
    if params.get("subject_token_type") != "urn:ietf:params:oauth:token-type:access_token" or not subject:
        raise OAuthError("invalid_request", "subject_token (access token) required")
    try:
        claims = decode_token(subject)
    except TokenInvalid as e:
        raise OAuthError("invalid_grant", "subject_token invalid") from e
    trow = s.get(db.Token, claims["jti"])
    if not trow or trow.revoked_at or claims["exp"] < clock.now().timestamp():
        raise OAuthError("invalid_grant", "subject_token expired or revoked")
    # Proof of possession of the subject token: the parent must co-sign the exchange with the key the parent token is bound to (RFC 9449 `ath`).
    ok, detail, _ = verify_dpop(s, params.get("subject_dpop"), method="POST", url=url, access_token=subject, expected_jkt=(claims.get("cnf") or {}).get("jkt"))
    if not ok:
        raise OAuthError("invalid_grant", f"subject_dpop: {detail}")
    child_id = params.get("mandate_id")
    child = mandates.get_row(s, child_id) if child_id else None
    if not child or child.content["mandatary"]["client_id"] != client.client_id:
        raise OAuthError("invalid_target", "requested mandate is not held by this client")
    lin = child.content.get("lineage")
    if not lin or lin["parent_mandate_id"] != claims[f"{config.CLAIM_NS}mandate_id"]:
        raise OAuthError("invalid_target", "requested mandate is not a bank-validated delegation of the subject token's mandate")
    if mandates.get_state(s, child.mandate_id, child.version).status != "ACTIVE":
        raise OAuthError("access_denied", "child mandate is not active")
    ok, detail, jkt = verify_dpop(s, dpop, method="POST", url=url)
    if not ok:
        raise OAuthError("invalid_dpop_proof", detail)
    if jkt != agents_mod.jwk_thumbprint(client.public_key_jwk):
        raise OAuthError("invalid_dpop_proof", "DPoP key is not the agent's registered key")
    details = validate_rar(params.get("authorization_details")) if params.get("authorization_details") else mandates_to_details(child.content)
    _rar_within_mandate(details, child.content)
    token, c2 = _issue(s, agent=client, row=child, details=details, jkt=jkt, actor_chain={"sub": client.id, "act": claims["act"]})
    return {"access_token": token, "issued_token_type": "urn:ietf:params:oauth:token-type:access_token", "token_type": "DPoP", "expires_in": config.ACCESS_TOKEN_TTL_SECONDS, "scope": c2["scope"]}


def mandates_to_details(content: dict) -> list[dict]:
    from . import cnl

    return cnl.authorization_details(content)


# --------------------------------------------------------------------------- verification (resource server side)


def decode_token(token: str, *, verify_exp: bool = False) -> dict:
    try:
        pub = keys.as_signing_key().public_key()
        return jwt.decode(token, pub, algorithms=["ES256"], issuer=config.ISSUER, options={"verify_aud": False, "verify_exp": verify_exp, "verify_iat": False})
    except jwt.PyJWTError as e:
        raise TokenInvalid(str(e)) from e


def verify_access_token(s, token: str | None, *, method: str, url: str, dpop: str | None) -> tuple[dict, dict]:
    """Returns (claims, token_facts for the PDP). Raises TokenInvalid when the token cannot be trusted at all."""
    if not token:
        raise TokenInvalid("no token")
    claims = decode_token(token)
    now = clock.now().timestamp()
    row = s.get(db.Token, claims.get("jti", ""))
    agent = s.execute(select(db.Agent).where(db.Agent.client_id == claims.get("client_id"))).scalar_one_or_none()
    actor = (claims.get("act") or {}).get("sub")
    actor_ok = bool(agent and actor == agent.id)
    jkt = (claims.get("cnf") or {}).get("jkt")
    if jkt:
        dpop_ok, dpop_detail, _ = verify_dpop(s, dpop, method=method, url=url, access_token=token, expected_jkt=jkt)
    else:
        dpop_ok, dpop_detail = False, "token is not sender-constrained (no cnf.jkt)"
    facts = {
        "present": True, "signature_valid": True, "expired": claims.get("exp", 0) <= now, "revoked": bool(row is None or row.revoked_at),
        "audience_ok": claims.get("aud") == config.API_AUDIENCE, "dpop_ok": dpop_ok, "dpop_detail": dpop_detail, "actor_ok": actor_ok,
        "actor_detail": "act.sub does not match the registered agent for this client_id" if not actor_ok else "",
        "scopes": (claims.get("scope") or "").split(), "jti": claims.get("jti"), "client_id": claims.get("client_id"), "sub": claims.get("sub"),
        "mandate_id": claims.get(f"{config.CLAIM_NS}mandate_id"), "mandate_version": claims.get(f"{config.CLAIM_NS}mandate_version"),
        "mandate_hash": claims.get(f"{config.CLAIM_NS}mandate_hash"), "actor": actor,
        "rar": (row.authorization_details if row is not None else []) or [],
    }
    return claims, facts


# --------------------------------------------------------------------------- introspection / revocation


def introspect(s, client: db.Agent, token: str) -> dict:
    try:
        claims = decode_token(token)
    except TokenInvalid:
        return {"active": False}
    row = s.get(db.Token, claims.get("jti", ""))
    active = bool(row and not row.revoked_at and claims["exp"] > clock.now().timestamp() and claims.get("client_id") == client.client_id)
    if not active:
        return {"active": False}
    mid, mv = claims[f"{config.CLAIM_NS}mandate_id"], claims[f"{config.CLAIM_NS}mandate_version"]
    mstatus = mandates.get_state(s, mid, mv).status
    return {"active": True, "scope": claims["scope"], "client_id": claims["client_id"], "sub": claims["sub"], "aud": claims["aud"], "exp": claims["exp"], "iat": claims["iat"],
            "jti": claims["jti"], "token_type": "DPoP", "act": claims["act"], f"{config.CLAIM_NS}mandate_id": mid, f"{config.CLAIM_NS}mandate_version": mv,
            f"{config.CLAIM_NS}mandate_status": mstatus, "note": "Token activity is technical state. Authority is decided per request by the KYM PDP."}


def revoke_token(s, client: db.Agent, token: str) -> None:
    try:
        claims = decode_token(token)
    except TokenInvalid:
        return  # RFC 7009: respond 200 regardless
    row = s.get(db.Token, claims.get("jti", ""))
    if row and row.client_id == client.client_id and not row.revoked_at:
        row.revoked_at = clock.iso()
        ledger.append(s, "TOKEN_REVOKED", actor_id=client.id, actor_type="agent", principal_id=row.sub, agent_id=client.id, mandate_id=row.mandate_id, mandate_version=row.mandate_version, payload={"jti": row.jti})


def mint_test_token(s, agent_id: str, mandate_id: str, version: int, *, aud: str | None = None, ttl: int | None = None, drop_scope: str | None = None,
                    actor: str | None = None, jkt: str | None = None) -> str:
    """Playground / test hook: issues a REAL signed token with an intentional defect so the PDP's rejection can be demonstrated."""
    agent = s.get(db.Agent, agent_id)
    row = mandates.get_row(s, mandate_id, version)
    details = mandates_to_details(row.content)
    scopes = [x for x in _scopes_for(details) if x != drop_scope]
    token, _ = _issue(s, agent=agent, row=row, details=details, jkt=jkt or agents_mod.jwk_thumbprint(agent.public_key_jwk), actor_chain={"sub": actor or agent.id}, ttl=ttl, aud=aud, scope=scopes)
    return token


def jwks() -> dict:
    return {"keys": [keys.as_jwk()]}


def metadata() -> dict:
    return {
        "issuer": config.ISSUER, "authorization_endpoint": f"{config.ISSUER}/oauth/authorize", "token_endpoint": f"{config.ISSUER}/oauth/token",
        "pushed_authorization_request_endpoint": f"{config.ISSUER}/oauth/par", "introspection_endpoint": f"{config.ISSUER}/oauth/introspect",
        "revocation_endpoint": f"{config.ISSUER}/oauth/revoke", "jwks_uri": f"{config.ISSUER}/.well-known/jwks.json",
        "grant_types_supported": ["authorization_code", GRANT_TOKEN_EXCHANGE], "response_types_supported": ["code"], "code_challenge_methods_supported": ["S256"],
        "dpop_signing_alg_values_supported": ["ES256"], "authorization_details_types_supported": [RAR_TYPE], "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "scopes_supported": taxonomy.SCOPES + ["openid"], "id_token_signing_alg_values_supported": ["ES256"], "require_pushed_authorization_requests": True,
        "x-kym-sandbox": True, "x-kym-note": "Sandbox authorization server. Not certified. mTLS, refresh tokens and request objects are not implemented.",
    }

