"""Know Your Agent: agent registry, attestation (simulated), trust profile.

Agent-declared metadata is stored separately from facts verified by the bank.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from . import clock, config, db, keys, ledger, taxonomy
from .canon import b64u, canonical

STATUSES = ["UNREGISTERED", "PENDING_VERIFICATION", "VERIFIED", "RESTRICTED", "SUSPENDED", "REVOKED"]
TRANSITIONS = {
    "PENDING_VERIFICATION": {"VERIFIED", "REVOKED"},
    "VERIFIED": {"RESTRICTED", "SUSPENDED", "REVOKED"},
    "RESTRICTED": {"VERIFIED", "SUSPENDED", "REVOKED"},
    "SUSPENDED": {"VERIFIED", "RESTRICTED", "REVOKED"},
    "REVOKED": set(),
}
DECLARED_REQUIRED = ["display_name", "category", "operating_organization", "operator_id", "responsible_party", "developer",
                     "deployment_environment", "model_provider", "model_id", "software_version", "build_digest",
                     "supported_tools", "requested_capabilities", "declared_autonomy_level"]


class AgentError(ValueError):
    pass


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 JWK thumbprint (EC P-256 and OKP)."""
    members = {"EC": ("crv", "kty", "x", "y"), "OKP": ("crv", "kty", "x")}[jwk["kty"]]
    return b64u(hashlib.sha256(json.dumps({k: jwk[k] for k in members}, separators=(",", ":"), sort_keys=True).encode()).digest())


AGENT_ID_RE = re.compile(r"^agent_[a-z0-9_]{2,60}$")


def _ec_pem_path(agent_id: str):
    if not AGENT_ID_RE.match(agent_id):  # the id becomes part of a file name: block path traversal
        raise AgentError("invalid agent id")
    config.ensure_dirs()
    return config.DATA_DIR / "keys" / f"agent-{agent_id}.pem"


def generate_demo_agent_key(agent_id: str) -> tuple[ec.EllipticCurvePrivateKey, dict]:
    """DEMO ONLY: the server holds sandbox agent private keys. Real agents keep their own (workload identity / hardware-backed)."""
    key = ec.generate_private_key(ec.SECP256R1())
    _ec_pem_path(agent_id).write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    _ec_pem_path(agent_id).chmod(0o600)
    return key, public_jwk(key)


def public_jwk(key: ec.EllipticCurvePrivateKey) -> dict:
    n = key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256", "x": b64u(n.x.to_bytes(32, "big")), "y": b64u(n.y.to_bytes(32, "big"))}


def load_demo_agent_key(agent_id: str) -> ec.EllipticCurvePrivateKey | None:
    p = _ec_pem_path(agent_id)
    return serialization.load_pem_private_key(p.read_bytes(), password=None) if p.exists() else None  # type: ignore[return-value]


def _secrets_path():
    config.ensure_dirs()
    return config.DATA_DIR / "keys" / "agent-client-secrets.json"


def store_demo_client_secret(client_id: str, secret: str) -> None:
    p = _secrets_path()
    data = json.loads(p.read_text()) if p.exists() else {}
    data[client_id] = secret
    p.write_text(json.dumps(data))
    p.chmod(0o600)


def demo_client_secret(client_id: str) -> str | None:
    p = _secrets_path()
    return json.loads(p.read_text()).get(client_id) if p.exists() else None


def hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(secret.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_secret(secret: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        calc = hashlib.scrypt(secret.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return secrets.compare_digest(calc.hex(), h)
    except ValueError:
        return False


def make_attestation(agent_id: str, build_digest: str, jwk: dict) -> dict:
    """Simulated attestation authority statement. Production: SLSA/in-toto provenance, SPIFFE/SPIRE workload attestation."""
    stmt = {"agent_id": agent_id, "build_digest": build_digest, "key_thumbprint": jwk_thumbprint(jwk), "issued_at": clock.iso(), "issuer": "demo-attestation-authority"}
    k = keys.attestor_key()
    return {"statement": stmt, "signature": k.sign(canonical(stmt)), "key_id": k.kid, "assurance": "SIMULATED"}


def make_pop(key: ec.EllipticCurvePrivateKey, agent_id: str, nonce: str) -> str:
    return jwt.encode({"agent_id": agent_id, "nonce": nonce, "aud": "meridian-kya"}, key, algorithm="ES256")


def register(s, declared: dict, *, actor_id: str, agent_id: str | None = None, cnl_ref: str | None = None, generate_demo_keys: bool = True,
             public_key_jwk: dict | None = None, status: str = "PENDING_VERIFICATION") -> dict:
    missing = [k for k in DECLARED_REQUIRED if k not in declared or declared[k] in (None, "")]
    if missing:
        raise AgentError(f"missing declared fields: {', '.join(missing)}")
    bad = [c for c in declared["requested_capabilities"] if not taxonomy.is_known(c)]
    if bad:
        raise AgentError(f"unknown capabilities: {bad}")
    agent_id = agent_id or f"agent_{uuid.uuid4().hex[:10]}"
    if not AGENT_ID_RE.match(agent_id):
        raise AgentError("agent_id must match ^agent_[a-z0-9_]{2,60}$")
    if s.get(db.Agent, agent_id):
        raise AgentError("agent id already registered")
    client_id = f"client_{agent_id.removeprefix('agent_')}"
    secret = secrets.token_urlsafe(24)
    if generate_demo_keys:
        key, jwk = generate_demo_agent_key(agent_id)
        pop = make_pop(key, agent_id, "registration")
    else:
        if not public_key_jwk:
            raise AgentError("public_key_jwk is required when generate_demo_keys is false")
        jwk, pop = public_key_jwk, None
    attestation = make_attestation(agent_id, declared["build_digest"], jwk) if generate_demo_keys else {}
    row = db.Agent(
        id=agent_id, cnl_ref=cnl_ref or f"agent.{agent_id.removeprefix('agent_').replace('_', '-')}", display_name=declared["display_name"],
        declared={**declared, "proof_of_possession": pop}, verified={}, client_id=client_id, client_secret_hash=hash_secret(secret),
        public_key_jwk=jwk, status="PENDING_VERIFICATION", registered_at=clock.iso(), attestation=attestation,
        security_posture=declared.get("security_posture", {"mfa_on_operator_console": False, "secrets_in_kms": False, "prompt_injection_testing": False}),
        incidents=[], stats={"mandates_executed": 0, "payments_executed": 0, "payments_denied": 0},
    )
    s.add(row)
    s.flush()
    if generate_demo_keys:
        store_demo_client_secret(client_id, secret)
    ledger.append(s, "AGENT_REGISTERED", actor_id=actor_id, actor_type="bank_operator", agent_id=agent_id, payload={"client_id": client_id, "operator_id": declared["operator_id"], "build_digest": declared["build_digest"], "key_thumbprint": jwk_thumbprint(jwk)})
    if status != "PENDING_VERIFICATION":
        verify(s, agent_id, actor_id=actor_id, force_status=status)
    return {"agent": to_dict(row), "client_secret": secret}


def verify(s, agent_id: str, *, actor_id: str, force_status: str | None = None) -> dict:
    """Bank-operated verification. A caller can never mark itself verified; only facts that check out are recorded."""
    a = s.get(db.Agent, agent_id)
    if not a:
        raise AgentError("unknown agent")
    if a.status not in ("PENDING_VERIFICATION", "SUSPENDED", "RESTRICTED"):
        raise AgentError(f"agent in status {a.status} cannot be verified")
    checks = []
    att = a.attestation or {}
    stmt = att.get("statement")
    sig_ok = bool(stmt) and keys.verify_ed25519(keys.attestor_key().public_b64u, canonical(stmt), att.get("signature", ""))
    checks.append({"check": "attestation_signature", "ok": sig_ok})
    checks.append({"check": "build_digest_matches_attestation", "ok": bool(stmt) and stmt["build_digest"] == a.declared["build_digest"]})
    checks.append({"check": "key_bound_to_attestation", "ok": bool(stmt) and stmt["key_thumbprint"] == jwk_thumbprint(a.public_key_jwk)})
    pop = a.declared.get("proof_of_possession")
    pop_ok = False
    if pop:
        try:
            claims = jwt.decode(pop, jwt.PyJWK(a.public_key_jwk).key, algorithms=["ES256"], audience="meridian-kya")
            pop_ok = claims["agent_id"] == agent_id
        except jwt.PyJWTError:
            pop_ok = False
    checks.append({"check": "proof_of_possession_of_agent_key", "ok": pop_ok})
    ok = all(c["ok"] for c in checks)
    if not ok:
        raise AgentError("verification failed: " + ", ".join(c["check"] for c in checks if not c["ok"]))
    target = force_status or "VERIFIED"
    a.verified = {"checks": checks, "verified_at": clock.iso(), "verified_by": "meridian-kya-service", "key_thumbprint": jwk_thumbprint(a.public_key_jwk), "build_digest": stmt["build_digest"], "assurance": "SIMULATED_ATTESTATION"}
    a.status = target
    s.flush()
    ledger.append(s, "AGENT_VERIFIED", actor_id=actor_id, actor_type="bank_operator", agent_id=agent_id, payload={"status": target, "checks": checks})
    return to_dict(a)


def set_status(s, agent_id: str, new: str, *, actor_id: str, reason: str) -> dict:
    a = s.get(db.Agent, agent_id)
    if not a:
        raise AgentError("unknown agent")
    if new not in TRANSITIONS.get(a.status, set()):
        raise AgentError(f"transition {a.status} -> {new} is not allowed")
    if new == "VERIFIED":
        raise AgentError("use the verify action to (re)verify an agent")
    a.status = new
    s.flush()
    ledger.append(s, "AGENT_SUSPENDED", actor_id=actor_id, actor_type="bank_operator", agent_id=agent_id, payload={"status": new, "reason": reason})
    return to_dict(a)


def add_incident(s, agent_id: str, description: str, severity: str = "MEDIUM") -> None:
    a = s.get(db.Agent, agent_id)
    a.incidents = [*a.incidents, {"at": clock.iso(), "description": description, "severity": severity}]


def trust_profile(a: db.Agent, policy: dict) -> dict:
    """Transparent, configurable trust score. Informational: it feeds risk signals but NEVER overrides a denial."""
    w = policy["trust"]["weights"]
    posture = a.security_posture or {}
    controls = [bool(v) for v in posture.values()]
    security = (sum(controls) / len(controls) * 100) if controls else 0
    provenance = 90 if a.verified.get("checks") else 30
    identity = 85 if a.status in ("VERIFIED", "RESTRICTED") else 20
    stats = a.stats or {}
    total = stats.get("payments_executed", 0) + stats.get("payments_denied", 0)
    success = (stats.get("payments_executed", 0) / total * 100) if total else 50
    penalty = w["incident_penalty_per_incident"] * len(a.incidents)
    raw = provenance * w["provenance_confidence"] + identity * w["identity_assurance"] + security * w["security_controls"] + success * w["success_rate"] - penalty
    score = max(0, min(100, round(raw)))
    return {
        "score": score,
        "components": {"provenance_confidence": provenance, "identity_assurance": identity, "security_controls": round(security), "execution_success_rate": round(success), "incident_penalty": penalty},
        "weights": w,
        "formula": "provenance*w1 + identity*w2 + security*w3 + success*w4 - incident_penalty",
        "note": policy["trust"]["note"],
    }


def capabilities(a: db.Agent) -> list[str]:
    return list(a.declared.get("requested_capabilities", []))


def to_dict(a: db.Agent, policy: dict | None = None) -> dict:
    declared = {k: v for k, v in a.declared.items() if k != "proof_of_possession"}
    d = {
        "id": a.id, "cnl_ref": a.cnl_ref, "display_name": a.display_name, "status": a.status, "client_id": a.client_id,
        "registered_at": a.registered_at, "declared": declared, "verified": a.verified,
        "public_key": {**a.public_key_jwk, "thumbprint": jwk_thumbprint(a.public_key_jwk) if a.public_key_jwk else None},
        "attestation": {"statement": a.attestation.get("statement"), "key_id": a.attestation.get("key_id"), "assurance": a.attestation.get("assurance")} if a.attestation else {},
        "security_posture": a.security_posture, "incidents": a.incidents, "stats": a.stats,
    }
    d["trust"] = trust_profile(a, policy or config.policy_config())
    return d


def list_agents(s) -> list[dict]:
    return [to_dict(a) for a in s.execute(select(db.Agent).order_by(db.Agent.id)).scalars()]
