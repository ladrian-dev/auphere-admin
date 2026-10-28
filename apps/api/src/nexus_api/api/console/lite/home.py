"""``GET /console/lite/home`` — el Panel de un solo cliente (spec 030, R4).

Las cifras salen de :mod:`nexus_api.services.lite_home`, que llama a las
mismas funciones que el Inicio del partner. Solo módulo ``panel``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus_api.services.lite_home import LiteBalance, balance_horizon, lite_home

from .deps import LiteScope, lite_scope

router = APIRouter()


class DayCountOut(BaseModel):
    day: date
    count: int


class LiteConversationsOut(BaseModel):
    last_7d: int
    prev_7d: int | None
    daily: list[DayCountOut]


class AgentSpendOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    cents: int


class LiteSpendMonthOut(BaseModel):
    total_cents: int
    by_agent: list[AgentSpendOut] | None = None


class LiteWaitingOut(BaseModel):
    count: int
    first_conversation_id: uuid.UUID | None


class LiteBalanceOut(BaseModel):
    assigned: bool
    remaining_cents: int | None
    cap_cents: int | None
    days_left: float | None
    # Spec 045 (R4): «cubre N de M días del mes» y «te alcanza hasta…».
    month_days_left: int = 0
    runs_out_on: date | None = None
    #: Spec 047: la moneda de la bolsa del cliente.
    currency: str = "USD"


def balance_out(balance: LiteBalance, *, tz_name: str | None, now: datetime) -> LiteBalanceOut:
    month_days_left, runs_out_on = balance_horizon(balance, tz_name=tz_name, now=now)
    return LiteBalanceOut(
        assigned=balance.assigned,
        remaining_cents=balance.remaining_cents,
        cap_cents=balance.cap_cents,
        days_left=balance.days_left,
        month_days_left=month_days_left,
        runs_out_on=runs_out_on,
        currency=balance.currency,
    )


class LiteAttentionOut(BaseModel):
    kind: Literal["waiting", "balance_out", "balance_low"]
    count: int | None = None
    days_left: float | None = None


class LiteHomeOut(BaseModel):
    spend_month: LiteSpendMonthOut | None
    conversations: LiteConversationsOut | None
    waiting: LiteWaitingOut | None
    balance: LiteBalanceOut | None
    attention: list[LiteAttentionOut]
    errors: list[str]


@router.get("/home", response_model=LiteHomeOut)
async def read_home(scope: LiteScope = Depends(lite_scope("panel"))) -> LiteHomeOut:
    p = scope.principal
    now = datetime.now(UTC)
    data = await lite_home(
        scope.session,
        partner_id=p.partner.id,
        tenant_id=p.tenant_id,
        client_ref=p.client_ref,
        client_name=p.client_name,
        tenant_status=scope.tenant.status,
        with_inbox=p.has("inbox"),
        now=now,
    )
    out = LiteHomeOut.model_validate(data, from_attributes=True)
    if data.balance is not None:
        out.balance = balance_out(data.balance, tz_name=scope.tenant.timezone, now=now)
    return out
