"""Schemas for the billing admin — plans catalogue + per-tenant billing.

The per-tenant billing view resolves the FKs (partner name, plan name/price)
so the panel can render labels without a second round-trip.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

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


PaymentMethod = Literal["transfer", "cash", "zelle", "paypal", "crypto", "other"]


class TenantPaymentIn(BaseModel):
    """A monthly fee received outside the provider. A record, nothing else."""

    model_config = ConfigDict(extra="forbid")

    period_year: int = Field(ge=2024, le=2100)
    period_month: int = Field(ge=1, le=12)
    amount_cents: int = Field(gt=0)
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=120)
    paid_on: date
    note: str | None = Field(default=None, max_length=500)


class TenantPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    period_year: int
    period_month: int
    amount_cents: int
    currency: str
    method: str
    reference: str | None
    paid_on: date
    note: str | None
    recorded_by: str
    created_at: datetime
    voided_at: datetime | None
    voided_by: str | None
