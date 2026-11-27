"""Minimal agent-side SDK: OAuth authorization code + PKCE + PAR + DPoP, and bank API calls over HTTP.

The agent only ever talks to the bank over HTTP (here in-process via an ASGI test client). It has no database
or payment-engine access. Private keys held here are DEMO keys for sandbox agents.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from . import agents as agents_mod
from . import config
from .canon import b64u


@dataclass
class TokenSet:
    access_token: str
    expires_at: float
    mandate_id: str
    mandate_version: int
    scope: str
    raw: dict = field(default_factory=dict)


class AgentClient:
    def __init__(self, http, agent_id: str, client_id: str, client_secret: str, key: ec.EllipticCurvePrivateKey, base: str = "http://testserver"):
        self.http, self.agent_id, self.client_id, self.client_secret, self.key, self.base = http, agent_id, client_id, client_secret, key, base
        self.jwk = agents_mod.public_jwk(key)

    @classmethod
    def for_demo_agent(cls, http, agent_id: str, client_id: str, base: str = "http://testserver") -> AgentClient:
        key = agents_mod.load_demo_agent_key(agent_id)
        secret = agents_mod.demo_client_secret(client_id)
        if key is None or secret is None:
            raise RuntimeError(f"no demo credentials for {agent_id}")
        return cls(http, agent_id, client_id, secret, key, base)

    def dpop(self, method: str, url: str, access_token: str | None = None, *, iat: int | None = None, jti: str | None = None) -> str:
        claims = {"jti": jti or uuid.uuid4().hex, "htm": method.upper(), "htu": url.split("?")[0], "iat": iat if iat is not None else int(time.time())}
        if access_token:
            claims["ath"] = b64u(hashlib.sha256(access_token.encode()).digest())
        return jwt.encode(claims, self.key, algorithm="ES256", headers={"typ": "dpop+jwt", "jwk": self.jwk})

    def authorize(self, authorization_details: list[dict], approve: Callable[[str], dict], *, scope: str = "openid") -> TokenSet:
        """PAR -> (bank-hosted customer approval via `approve`) -> token request with PKCE and DPoP."""
        verifier = secrets.token_urlsafe(48)
        challenge = b64u(hashlib.sha256(verifier.encode()).digest())
        par = self.http.post(f"{self.base}/oauth/par", json={
            "client_id": self.client_id, "client_secret": self.client_secret, "response_type": "code", "code_challenge": challenge, "code_challenge_method": "S256",
            "resource": config.API_AUDIENCE, "authorization_details": authorization_details, "scope": scope, "state": secrets.token_hex(4), "nonce": secrets.token_hex(4)})
        if par.status_code != 201:
            raise AuthorizationFailed(par.status_code, par.json())
        auth = approve(par.json()["request_uri"])
        url = f"{self.base}/oauth/token"
        tok = self.http.post(url, json={"grant_type": "authorization_code", "client_id": self.client_id, "client_secret": self.client_secret, "code": auth["code"], "code_verifier": verifier},
                             headers={"DPoP": self.dpop("POST", url)})
        if tok.status_code != 200:
            raise AuthorizationFailed(tok.status_code, tok.json())
        b = tok.json()
        d = authorization_details[0]
        return TokenSet(b["access_token"], time.time() + b["expires_in"], d["mandate_id"], d["mandate_version"], b["scope"], b)

    def exchange(self, subject_token: str, mandate_id: str) -> TokenSet:
        url = f"{self.base}/oauth/token"
        r = self.http.post(url, json={"grant_type": "urn:ietf:params:oauth:grant-type:token-exchange", "client_id": self.client_id, "client_secret": self.client_secret,
                                      "subject_token": subject_token, "subject_token_type": "urn:ietf:params:oauth:token-type:access_token", "mandate_id": mandate_id}, headers={"DPoP": self.dpop("POST", url)})
        if r.status_code != 200:
            raise AuthorizationFailed(r.status_code, r.json())
        b = r.json()
        return TokenSet(b["access_token"], time.time() + b["expires_in"], mandate_id, 1, b["scope"], b)

    def call(self, token: TokenSet | str, method: str, path: str, *, json_body: dict | None = None, idempotency_key: str | None = None, params: dict | None = None):
        url = f"{self.base}{path}"
        at = token.access_token if isinstance(token, TokenSet) else token
        headers = {"Authorization": f"DPoP {at}", "DPoP": self.dpop(method, url, at)}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self.http.request(method, url, headers=headers, json=json_body, params=params)


class AuthorizationFailed(Exception):
    def __init__(self, status: int, body: dict):
        super().__init__(f"authorization failed ({status}): {json.dumps(body)[:200]}")
        self.status, self.body = status, body
