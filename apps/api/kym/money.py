"""Exact monetary arithmetic on integer minor units. No binary floating point anywhere."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

MAX_MINOR = 10**15  # well inside BIGINT; rejects overflow before it can reach the database
EXPONENT = {"JPY": 0, "KRW": 0, "BHD": 3, "KWD": 3}


class MoneyError(ValueError):
    pass


def exponent(ccy: str) -> int:
    return EXPONENT.get(ccy, 2)


def parse_major(text: str, ccy: str) -> int:
    try:
        d = Decimal(text)
    except InvalidOperation as e:
        raise MoneyError(f"invalid amount {text!r}") from e
    exp = exponent(ccy)
    scaled = d * (10**exp)
    if scaled != scaled.to_integral_value():
        raise MoneyError(f"{ccy} has {exp} decimal places; {text!r} is more precise")
    if scaled < 0:
        raise MoneyError("amount must not be negative")
    return int(scaled)


def fmt(minor: int, ccy: str) -> str:
    exp = exponent(ccy)
    if exp == 0:
        return f"{minor} {ccy}"
    major, frac = divmod(minor, 10**exp)
    return f"{major} {ccy}" if frac == 0 else f"{major}.{str(frac).zfill(exp)} {ccy}"


def require_minor(value, name: str = "amount") -> int:
    """Validate an API-supplied amount: an exact integer (never float, str or bool)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoneyError(f"{name} must be an integer in minor currency units")
    if value < 0:
        raise MoneyError(f"{name} must not be negative")
    if value > MAX_MINOR:
        raise MoneyError(f"{name} exceeds the supported maximum")
    return value
