"""Transport-level hardening: rate limiting, failed-auth lockout, security headers, body size caps.

These controls protect the *availability and integrity of the evidence ledger* from unauthenticated abuse
(every rejected request would otherwise write a signed event and hold the global write lock).
In-memory and per-process: a production deployment needs a shared limiter at the edge (gateway/WAF).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from . import config

MAX_BODY_BYTES = 1_000_000
UNAUTH_PREFIXES = ("/bank", "/oauth", "/adapters")
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class RateLimiter:
    """Sliding-window limiter. `allow(key)` records the hit and returns False once the window is full."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def count(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            return len(q)

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


REQUESTS = RateLimiter(config.RATE_LIMIT_PER_MIN)
FAILED_CLIENT_AUTH = RateLimiter(config.FAILED_AUTH_PER_MIN)
# At most N TOKEN_REJECTED evidence events per minute; the rest are counted, not written (ledger-flood defence).
REJECT_EVENTS = RateLimiter(config.REJECT_EVENTS_PER_MIN)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"  # X-Forwarded-For is deliberately NOT trusted


async def security_middleware(request: Request, call_next):
    path = request.url.path
    ip = client_ip(request)
    if path.startswith(UNAUTH_PREFIXES):
        if not REQUESTS.allow(ip):
            return _limited("rate limit exceeded")
        if path.startswith("/oauth") and FAILED_CLIENT_AUTH.count(ip) >= config.FAILED_AUTH_PER_MIN:
            return _limited("too many failed client authentications")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse({"error": "payload_too_large"}, status_code=413)
    response = await call_next(request)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    h["X-KYM-Environment"] = f"{config.ENV}; synthetic-data"
    if not path.startswith(DOC_PATHS):
        h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if path.startswith(("/api", "/bank", "/oauth", "/adapters")):
        h.setdefault("Cache-Control", "no-store")
    return response


def _limited(msg: str) -> JSONResponse:
    return JSONResponse({"error": "too_many_requests", "error_description": msg}, status_code=429, headers={"Retry-After": "60"})
