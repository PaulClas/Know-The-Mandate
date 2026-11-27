"""Regulatory control mappings and standards matrix (data lives in policies/ and standards/). A mapping is NOT a compliance claim."""
from __future__ import annotations

import json
from functools import lru_cache

from . import config

DIRS = {"CA": "canada", "CA-QC": "quebec", "US": "united-states"}
DISCLAIMER = "Control mapping for demonstration. Not legal advice. The KYM demo is not compliant with, certified against or approved under any listed law, regulation, guidance or standard."


@lru_cache
def controls() -> list[dict]:
    out = []
    for d in DIRS.values():
        out += json.loads((config.POLICIES / d / "controls.json").read_text())
    return out


def controls_for(jurisdiction: str | None = None) -> list[dict]:
    return [c for c in controls() if not jurisdiction or c["jurisdiction"] == jurisdiction]


@lru_cache
def profiles() -> list[dict]:
    return json.loads((config.POLICIES / "jurisdiction-profiles.json").read_text())


@lru_cache
def standards() -> list[dict]:
    return json.loads((config.STANDARDS / "standards.json").read_text())


@lru_cache
def ap2_mapping() -> dict:
    return json.loads((config.STANDARDS / "ap2" / "mapping.json").read_text())
