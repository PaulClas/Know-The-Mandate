from __future__ import annotations

from datetime import UTC, datetime, timedelta

_offset = timedelta(0)


def now() -> datetime:
    return datetime.now(UTC) + _offset


def advance(seconds: float) -> None:
    """Test and demo hook: move the trusted server clock forward."""
    global _offset
    _offset += timedelta(seconds=seconds)


def reset() -> None:
    global _offset
    _offset = timedelta(0)


def iso(dt: datetime | None = None) -> str:
    dt = dt or now()
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
