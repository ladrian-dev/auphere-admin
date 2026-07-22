"""Schemas for the partner receipt (recibo) admin panel."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReceiptLineOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    model: str
    description: str
    amount_usd: float
    commission_clp: float | None = None


class ReceiptOut(BaseModel):
    invoice_id: uuid.UUID
    partner_id: uuid.UUID
    partner_slug: str
    partner_name: str
    billing_email: str | None
    period_year: int
    period_month: int
    total_usd: float
    currency: str
    status: str
    clp_per_usd: float | None = None
    issued_at: datetime | None = None
    due_date: date
    created: bool
    lines: list[ReceiptLineOut] = Field(default_factory=list)


class ReceiptSummaryOut(BaseModel):
    """One row in the partner's receipt list (no line detail)."""

    model_config = ConfigDict(from_attributes=True)

    invoice_id: uuid.UUID
    period_year: int
    period_month: int
    total_usd: float
    currency: str
    status: str
    issued_at: datetime | None = None
    due_date: date


class ReceiptGenerateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_year: int = Field(ge=2024, le=2100)
    period_month: int = Field(ge=1, le=12)
    send_email: bool = False


class ReceiptSendOut(BaseModel):
    invoice_id: uuid.UUID
    emailed: bool
    to: str | None = None
