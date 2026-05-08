from __future__ import annotations

import uuid
from datetime import date as Date  # noqa: N812

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class CalculateCommissionInput(InputModel):
    barber_id: uuid.UUID
    service_amount_cents: int = Field(ge=0)
    tip_amount_cents: int = Field(default=0, ge=0)
    currency: str = Field(default="CLP", min_length=3, max_length=3)


class CalculateCommissionOutput(OutputModel):
    barber_id: uuid.UUID
    model: str
    commission_cents: int
    tip_cents: int
    total_cents: int
    currency: str


class GetBarberEarningsInput(InputModel):
    barber_id: uuid.UUID
    from_date: Date
    to_date: Date


class GetBarberEarningsOutput(OutputModel):
    barber_id: uuid.UUID
    appointments_count: int
    gross_revenue_cents: int
    commission_cents: int
    currency: str


class GetDailyReportInput(InputModel):
    on_date: Date


class BarberDailyTotal(OutputModel):
    barber_id: uuid.UUID | None
    appointments_count: int
    gross_revenue_cents: int
    commission_cents: int


class GetDailyReportOutput(OutputModel):
    on_date: Date
    appointments_count: int
    gross_revenue_cents: int
    total_commission_cents: int
    currency: str
    by_barber: list[BarberDailyTotal]
