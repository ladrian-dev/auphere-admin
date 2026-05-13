from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Slug: lowercase alphanumeric with single hyphens between segments. Mirrors
# the DNS-safe convention we use across the platform (Cloudflare DNS, Vercel
# preview deploys). The DB column is UNIQUE so duplicates 409.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# E.164: leading +, then 1-15 digits with no leading zero in the country code.
_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")
# ISO 3166-1 alpha-2 country code.
_MARKET_RE = re.compile(r"^[A-Z]{2}$")


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    plan: str
    status: str
    market: str | None
    timezone: str
    business_hours: dict[str, Any] | None
    owner_phone: str | None
    owner_email: str | None
    cost_alert_threshold_usd_per_day: Decimal
    agendapro_public_url: str | None = None
    created_at: datetime
    updated_at: datetime


class TenantCreateIn(BaseModel):
    """POST /admin/tenants payload — the wizard sends this."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    plan: str = Field(default="pro")
    market: str | None = Field(default=None)
    timezone: str = Field(default="UTC", max_length=64)
    owner_email: EmailStr | None = Field(default=None)
    owner_phone: str | None = Field(default=None, max_length=32)
    business_hours: dict[str, Any] | None = Field(default=None)
    cost_alert_threshold_usd_per_day: Decimal = Field(default=Decimal("40.00"))

    @field_validator("slug")
    @classmethod
    def _slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase alphanumeric with hyphens (e.g. cultor-barber)"
            )
        return v

    @field_validator("plan")
    @classmethod
    def _plan_known(cls, v: str) -> str:
        if v not in ("essential", "pro", "business", "internal"):
            raise ValueError("plan must be one of: essential, pro, business, internal")
        return v

    @field_validator("market")
    @classmethod
    def _market_iso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        upper = v.upper()
        if not _MARKET_RE.match(upper):
            raise ValueError("market must be a 2-letter ISO 3166-1 country code (e.g. CL)")
        return upper

    @field_validator("timezone")
    @classmethod
    def _timezone_valid(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {v}") from exc
        return v

    @field_validator("owner_phone")
    @classmethod
    def _phone_e164(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _E164_RE.match(v):
            raise ValueError("owner_phone must be E.164 (starts with + then 1-15 digits)")
        return v

    @field_validator("cost_alert_threshold_usd_per_day")
    @classmethod
    def _threshold_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("cost_alert_threshold_usd_per_day must be positive")
        if v > Decimal("10000"):
            raise ValueError("cost_alert_threshold_usd_per_day looks unreasonable; cap is 10000")
        return v


class TenantUpdateIn(BaseModel):
    """PUT /admin/tenants/:id payload — every field optional (PATCH semantics)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: str | None = Field(default=None)
    status: str | None = Field(default=None)
    market: str | None = Field(default=None)
    timezone: str | None = Field(default=None, max_length=64)
    owner_email: EmailStr | None = Field(default=None)
    owner_phone: str | None = Field(default=None, max_length=32)
    business_hours: dict[str, Any] | None = Field(default=None)
    cost_alert_threshold_usd_per_day: Decimal | None = Field(default=None)

    @field_validator("plan")
    @classmethod
    def _plan_known(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in ("essential", "pro", "business", "internal"):
            raise ValueError("plan must be one of: essential, pro, business, internal")
        return v

    @field_validator("status")
    @classmethod
    def _status_known(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in ("active", "paused", "archived"):
            raise ValueError("status must be one of: active, paused, archived")
        return v

    @field_validator("market")
    @classmethod
    def _market_iso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        upper = v.upper()
        if not _MARKET_RE.match(upper):
            raise ValueError("market must be a 2-letter ISO 3166-1 country code (e.g. CL)")
        return upper

    @field_validator("timezone")
    @classmethod
    def _timezone_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {v}") from exc
        return v

    @field_validator("owner_phone")
    @classmethod
    def _phone_e164(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _E164_RE.match(v):
            raise ValueError("owner_phone must be E.164 (starts with + then 1-15 digits)")
        return v

    @field_validator("cost_alert_threshold_usd_per_day")
    @classmethod
    def _threshold_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("cost_alert_threshold_usd_per_day must be positive")
        if v > Decimal("10000"):
            raise ValueError("cost_alert_threshold_usd_per_day looks unreasonable; cap is 10000")
        return v


class SlugAvailabilityOut(BaseModel):
    slug: str
    available: bool


class ChannelOut(BaseModel):
    """Public shape of a Channel row — used by the integrations page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    provider: str
    provider_identifier: str
    config: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
