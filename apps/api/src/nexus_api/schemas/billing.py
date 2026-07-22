"""Schemas for the billing admin — plans catalogue + per-tenant billing.

The per-tenant billing view resolves the FKs (partner name, plan name/price)
so the panel can render labels without a second round-trip.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class BillingPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    monthly_amount_cents: int
    active: bool


class BillingPlanCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    monthly_amount_cents: int = Field(ge=0)


class TenantBillingOut(BaseModel):
    """Resolved billing config for one tenant."""

    tenant_id: uuid.UUID
    tenant_name: str
    partner_id: uuid.UUID | None
    partner_name: str | None
    billing_plan_id: uuid.UUID | None
    plan_name: str | None
    plan_amount_cents: int | None
    price_override_cents: int | None
    billing_effective_from: date | None
    # Derived: what the tenant is billed monthly in USD cents (override wins).
    effective_monthly_cents: int | None
    # "commission" | "subscription" | "inactive" — how the receipt classifies it.
    model: str


class TenantBillingUpdateIn(BaseModel):
    """PUT payload — PATCH semantics via ``exclude_unset``. A field only
    changes when the client actually sends it; sending it as ``null`` clears
    it (e.g. ``partner_id: null`` → direct Auphere client)."""

    model_config = ConfigDict(extra="forbid")

    partner_id: uuid.UUID | None = None
    billing_plan_id: uuid.UUID | None = None
    price_override_cents: int | None = Field(default=None, ge=0)
    billing_effective_from: date | None = None
