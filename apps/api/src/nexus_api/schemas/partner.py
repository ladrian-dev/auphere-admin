"""Pydantic schemas for the partner platform (ADR-028).

Two families:
- ``/v1/partners/*`` (public, secret-key auth) — responses NEVER expose
  internal tenant ids; the partner only ever sees its own
  ``external_client_ref``.
- ``/admin/partners/*`` (operator panel) — full detail, including the
  one-time plaintext key at creation/rotation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ── /v1/partners (public, server-to-server) ─────────────────────────────────


class ClientProvisionIn(BaseModel):
    external_client_ref: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="UTC", max_length=64)


class WhatsAppStatusOut(BaseModel):
    status: Literal["connected", "not_connected"]
    display_phone_number: str | None = None


class ClientProvisionOut(BaseModel):
    external_client_ref: str
    status: Literal["provisioned"]
    whatsapp: WhatsAppStatusOut


class WidgetSessionIn(BaseModel):
    external_client_ref: str = Field(min_length=1, max_length=255)


class WidgetSessionOut(BaseModel):
    session_token: str
    expires_in: int
    whatsapp: WhatsAppStatusOut


# ── /admin/partners ──────────────────────────────────────────────────────────


class PartnerCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    contact_email: EmailStr | None = None


class PartnerUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["active", "suspended"] | None = None
    contact_email: EmailStr | None = None
    broadcast_recipient_cap: int | None = Field(default=None, ge=1, le=10_000)
    rate_limit_mint_per_min: int | None = Field(default=None, ge=1, le=10_000)
    rate_limit_embed_per_min: int | None = Field(default=None, ge=1, le=100_000)


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    contact_email: str | None
    broadcast_recipient_cap: int
    rate_limit_mint_per_min: int
    rate_limit_embed_per_min: int
    created_at: datetime
    updated_at: datetime


class ApiKeyCreateIn(BaseModel):
    type: Literal["live", "test"] = "live"
    scopes: list[str] = Field(default=["provision", "widget_sessions"])
    allowed_origins: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    prefix_snippet: str
    scopes: list[str]
    allowed_origins: list[str]
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    grace_expires_at: datetime | None


class ApiKeyCreatedOut(ApiKeyOut):
    """Returned ONLY at creation/rotation — the single time the plaintext
    exists outside the partner's own storage."""

    plaintext: str


class ApiKeyRotateIn(BaseModel):
    grace_hours: int = Field(default=24, ge=0, le=24 * 14)


class OriginsUpdateIn(BaseModel):
    allowed_origins: list[str] = Field(max_length=20)


class PartnerTenantLinkIn(BaseModel):
    external_client_ref: str = Field(min_length=1, max_length=255)
    tenant_id: uuid.UUID
    client_name: str | None = Field(default=None, max_length=255)


class PartnerTenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    partner_id: uuid.UUID
    external_client_ref: str
    tenant_id: uuid.UUID
    client_name: str | None
    created_at: datetime


class EmbedAuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    partner_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    tenant_id: uuid.UUID | None
    event: str
    payload: dict[str, Any]
    ip: str | None
    origin: str | None
    jti: str | None
    created_at: datetime
