"""Pydantic schemas for the Auphere channel registry (Bloque D Fase 2).

Two resource families:

- ``auphere_owner_channels`` — global registry of Auphere outbound
  numbers (CRUD via the admin endpoints).
- ``owner_phone_index`` — per-tenant registry of owner phones, with
  optional pinning to a specific Auphere channel.

E.164 phone validation is enforced server-side via a strict regex —
the admin UI duplicates it client-side for instant feedback but the
server is the source of truth.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")
_PROVIDERS: ClassVar = ("ycloud", "meta")


def _validate_e164(value: str) -> str:
    if not _E164_RE.match(value):
        raise ValueError(
            "phone must be in E.164 format (e.g. +56912345678) — leading +, "
            "country code, no spaces, max 15 digits"
        )
    return value


# ── auphere_owner_channels ─────────────────────────────────────────


class AuphereOwnerChannelOut(BaseModel):
    """One row of ``auphere_owner_channels`` exposed to the admin panel.

    ``has_webhook_secret`` is a boolean view of
    ``webhook_secret_encrypted IS NOT NULL`` — the secret itself never
    leaves the server. The operator can rotate via PATCH but not read.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_e164: str
    display_name: str
    country_code: str | None
    provider: str
    provider_phone_id: str | None
    active: bool
    is_default: bool
    has_webhook_secret: bool
    created_at: datetime
    updated_at: datetime


class AuphereOwnerChannelCreateIn(BaseModel):
    """Body for POST /admin/auphere/channels."""

    model_config = ConfigDict(extra="forbid")

    phone_e164: str = Field(min_length=2, max_length=20)
    display_name: str = Field(min_length=1, max_length=120)
    country_code: str | None = Field(
        default=None, min_length=2, max_length=2
    )
    provider: str = Field(default="ycloud")
    provider_phone_id: str | None = Field(default=None, max_length=120)
    is_default: bool = Field(default=False)
    webhook_secret: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Optional per-channel webhook HMAC secret. When NULL the "
            "webhook falls back to settings.ycloud_webhook_secret (the "
            "shared provider secret). Stored Fernet-encrypted."
        ),
    )

    @field_validator("phone_e164")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return _validate_e164(v)

    @field_validator("country_code")
    @classmethod
    def _validate_country(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.isalpha():
            raise ValueError("country_code must be 2 letters (ISO 3166)")
        return v.upper()

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        if v not in _PROVIDERS:
            raise ValueError(
                f"provider must be one of {list(_PROVIDERS)}; got {v!r}"
            )
        return v


class AuphereOwnerChannelUpdateIn(BaseModel):
    """Body for PATCH /admin/auphere/channels/{id}. Every field optional
    so the operator can rotate a single property in isolation."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    country_code: str | None = Field(
        default=None, min_length=2, max_length=2
    )
    provider_phone_id: str | None = Field(default=None, max_length=120)
    active: bool | None = Field(default=None)
    is_default: bool | None = Field(default=None)
    webhook_secret: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Rotates the per-channel HMAC secret. Pass an empty string "
            "to clear it (revert to shared provider secret)."
        ),
    )

    @field_validator("country_code")
    @classmethod
    def _validate_country(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.isalpha():
            raise ValueError("country_code must be 2 letters (ISO 3166)")
        return v.upper()


# ── owner_phone_index ──────────────────────────────────────────────


class OwnerPhoneIndexOut(BaseModel):
    """One row of ``owner_phone_index`` for a given tenant."""

    model_config = ConfigDict(from_attributes=True)

    phone_e164: str
    tenant_id: uuid.UUID
    user_label: str | None
    active: bool
    added_at: datetime
    auphere_channel_id: uuid.UUID | None


class OwnerPhoneIndexCreateIn(BaseModel):
    """Body for POST /admin/tenants/{tenant_id}/backchannel/owners."""

    model_config = ConfigDict(extra="forbid")

    phone_e164: str = Field(min_length=2, max_length=20)
    user_label: str | None = Field(default=None, max_length=120)
    auphere_channel_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Optional explicit pin to a specific Auphere channel. NULL "
            "means the resolver picks the provider's default at send "
            "time (recommended unless this owner needs a country-"
            "specific number)."
        ),
    )

    @field_validator("phone_e164")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return _validate_e164(v)


class OwnerPhoneIndexUpdateIn(BaseModel):
    """Body for PATCH /admin/tenants/{tenant_id}/backchannel/owners/{phone}."""

    model_config = ConfigDict(extra="forbid")

    user_label: str | None = Field(default=None, max_length=120)
    active: bool | None = Field(default=None)
    auphere_channel_id: uuid.UUID | None = Field(default=None)
    # Sentinel for "clear the channel pin" — the JSON body sends
    # ``auphere_channel_id: null`` AND ``clear_channel_id: true``. Pure
    # null could mean "don't touch" so we need the explicit signal.
    clear_channel_id: bool = Field(default=False)
