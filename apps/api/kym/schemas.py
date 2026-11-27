"""Canonical mandate data model (Pydantic). The JSON Schema in packages/mandate-schema is generated from this."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from . import config, taxonomy

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CCY_RE = re.compile(r"^[A-Z]{3}$")
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Principal(Strict):
    id: str
    type: Literal["individual", "business"]


class Mandatary(Strict):
    agent_id: str
    operator_id: str
    client_id: str


class Constraints(Strict):
    currency: str | None = None
    maximum_amount_minor: StrictInt | None = Field(default=None, gt=0)
    allowed_beneficiaries: list[str] = []
    allowed_merchants: list[str] = []
    allowed_destination_accounts: list[str] = []
    allowed_merchant_categories: list[str] = []
    allowed_countries: list[str] = []

    @field_validator("currency")
    @classmethod
    def _ccy(cls, v):
        if v is not None and not CCY_RE.match(v):
            raise ValueError("currency must be an ISO 4217 alphabetic code")
        return v


class Permission(Strict):
    action: str
    resources: list[str] = Field(min_length=1)
    constraints: Constraints = Constraints()

    @field_validator("action")
    @classmethod
    def _action(cls, v):
        if not taxonomy.is_known(v):
            raise ValueError(f"unknown action {v}")
        return v


class AggregateConstraints(Strict):
    maximum_daily_amount_minor: StrictInt | None = Field(default=None, gt=0)
    maximum_monthly_amount_minor: StrictInt | None = Field(default=None, gt=0)
    maximum_transaction_count_monthly: StrictInt | None = Field(default=None, gt=0)


class Obligations(Strict):
    human_approval_above_minor: StrictInt | None = Field(default=None, ge=0)
    required_approvals: StrictInt = Field(default=1, ge=1, le=5)
    notify_customer: StrictBool = True


class Delegation(Strict):
    allowed: StrictBool = False
    maximum_depth: StrictInt = Field(default=0, ge=0, le=5)


class Lineage(Strict):
    parent_mandate_id: str
    parent_mandate_version: StrictInt
    depth: StrictInt = Field(ge=1)


class Validity(Strict):
    not_before: str
    expires_at: str
    budget_timezone: str = config.BUDGET_TZ_DEFAULT

    @field_validator("not_before", "expires_at")
    @classmethod
    def _ts(cls, v):
        if not TS_RE.match(v):
            raise ValueError("timestamps must be UTC RFC 3339 with 'Z' and whole seconds")
        return v

    @field_validator("budget_timezone")
    @classmethod
    def _tz(cls, v):
        from zoneinfo import ZoneInfo

        ZoneInfo(v)
        return v

    @model_validator(mode="after")
    def _order(self):
        if self.expires_at <= self.not_before:
            raise ValueError("expires_at must be after not_before")
        return self


class Mandate(Strict):
    mandate_id: str
    schema_version: str = config.SCHEMA_VERSION
    ontology_version: str = config.ONTOLOGY_VERSION
    version: StrictInt = Field(default=1, ge=1)
    principal: Principal
    mandatary: Mandatary
    purpose: str
    currency: str = "CAD"
    permissions: list[Permission] = Field(min_length=1)
    prohibitions: list[str] = []
    aggregate_constraints: AggregateConstraints = AggregateConstraints()
    obligations: Obligations = Obligations()
    delegation: Delegation = Delegation()
    validity: Validity
    jurisdictions: list[str] = []
    policy_version: str = config.POLICY_VERSION
    lineage: Lineage | None = None

    @field_validator("mandate_id")
    @classmethod
    def _id(cls, v):
        if not ID_RE.match(v):
            raise ValueError("invalid mandate_id")
        return v

    @field_validator("currency")
    @classmethod
    def _ccy(cls, v):
        if not CCY_RE.match(v):
            raise ValueError("currency must be an ISO 4217 alphabetic code")
        return v

    @field_validator("prohibitions")
    @classmethod
    def _prohib(cls, v):
        for p in v:
            if not taxonomy.is_known(p):
                raise ValueError(f"unknown prohibited action {p}")
        return sorted(set(v))

    @model_validator(mode="after")
    def _consistency(self):
        prohibited = set(self.prohibitions)
        for perm in self.permissions:
            if perm.action in prohibited:
                raise ValueError(f"action {perm.action} is both permitted and prohibited")
            if perm.constraints.currency and perm.constraints.currency != self.currency:
                raise ValueError("permission currency must equal mandate currency")
        if not self.delegation.allowed and self.delegation.maximum_depth:
            raise ValueError("delegation.maximum_depth must be 0 when delegation is not allowed")
        return self

    def permission_for(self, action: str) -> list[Permission]:
        return [p for p in self.permissions if p.action == action]


def mandate_json_schema() -> dict:
    schema = Mandate.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://example.org/kym/v1/mandate.schema.json"
    schema["title"] = "KYM Mandate (experimental)"
    return schema
