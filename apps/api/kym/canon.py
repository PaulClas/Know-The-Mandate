"""Canonical JSON (RFC 8785 via the maintained `rfc8785` library) and domain-separated hashing."""
from __future__ import annotations

import base64
import hashlib
from typing import Any

import rfc8785


def canonical(obj: Any) -> bytes:
    return rfc8785.dumps(obj)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(obj: Any) -> str:
    """sha256 digest of the JCS form, prefixed for self-description."""
    return "sha256:" + sha256_hex(canonical(obj))


def domain_hash(domain: str, obj: Any) -> str:
    """H(len(domain) || domain || JCS(obj)); length prefix makes the encoding unambiguous."""
    d = domain.encode()
    return sha256_hex(len(d).to_bytes(2, "big") + d + canonical(obj))


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
