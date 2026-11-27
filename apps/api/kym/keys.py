"""Demo key management. Keys live in local files: DEMO ONLY. Production: HSM/KMS-backed keys."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from . import config
from .canon import b64u

_lock = threading.Lock()
_cache: dict[str, object] = {}


@dataclass
class Ed25519Key:
    kid: str
    private: ed25519.Ed25519PrivateKey

    @property
    def public_b64u(self) -> str:
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return b64u(raw)

    def sign(self, data: bytes) -> str:
        return b64u(self.private.sign(data))


def _path(name: str):
    config.ensure_dirs()
    return config.DATA_DIR / "keys" / f"{name}.pem"


def _load_or_create(name: str, kind: str):
    with _lock:
        cache_key = f"{config.DATA_DIR}:{name}"
        if cache_key in _cache:
            return _cache[cache_key]
        p = _path(name)
        if p.exists():
            key = serialization.load_pem_private_key(p.read_bytes(), password=None)
        else:
            key = ed25519.Ed25519PrivateKey.generate() if kind == "ed25519" else ec.generate_private_key(ec.SECP256R1())
            p.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            p.chmod(0o600)
        _cache[cache_key] = key
        return key


def reset_cache() -> None:
    _cache.clear()


def ed25519_key(name: str, kid: str | None = None) -> Ed25519Key:
    return Ed25519Key(kid or f"{name}-1", _load_or_create(name, "ed25519"))


def ledger_key() -> Ed25519Key:
    return ed25519_key("ledger", "kym-ledger-key-2026-01")


def decision_key() -> Ed25519Key:
    return ed25519_key("decision", "kym-decision-key-2026-01")


def witness_key() -> Ed25519Key:
    return ed25519_key("witness", "kym-witness-key-2026-01")


def attestor_key() -> Ed25519Key:
    return ed25519_key("attestor", "demo-attestor-key-2026-01")


def customer_consent_key(customer_id: str) -> Ed25519Key:
    """Simulated bank-authenticated customer signing key (stand-in for passkey/WebAuthn)."""
    return ed25519_key(f"customer-{customer_id}", f"consent-{customer_id}-1")


def as_signing_key() -> ec.EllipticCurvePrivateKey:
    return _load_or_create("authz-server", "ec")  # type: ignore[return-value]


AS_KID = "kym-as-es256-2026-01"


def as_jwk() -> dict:
    pub = as_signing_key().public_key()
    n = pub.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64u(n.x.to_bytes(32, "big")),
        "y": b64u(n.y.to_bytes(32, "big")),
        "kid": AS_KID,
        "alg": "ES256",
        "use": "sig",
    }


def public_key_registry() -> dict:
    """Public verification keys exported alongside evidence packages."""
    return {
        "ledger": {"kid": ledger_key().kid, "alg": "Ed25519", "x": ledger_key().public_b64u},
        "witness": {"kid": witness_key().kid, "alg": "Ed25519", "x": witness_key().public_b64u},
        "decision": {"kid": decision_key().kid, "alg": "Ed25519", "x": decision_key().public_b64u},
        "authorization_server": as_jwk(),
    }


def verify_ed25519(public_b64u: str, data: bytes, sig_b64u: str) -> bool:
    from cryptography.exceptions import InvalidSignature

    from .canon import b64u_decode

    try:
        ed25519.Ed25519PublicKey.from_public_bytes(b64u_decode(public_b64u)).verify(b64u_decode(sig_b64u), data)
        return True
    except (InvalidSignature, ValueError):
        return False


def dumps(o) -> str:
    return json.dumps(o, sort_keys=True)
