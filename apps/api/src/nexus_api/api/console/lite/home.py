"""``GET /console/lite/home`` — el Panel de un solo cliente (spec 030, R4).

Las cifras salen de :mod:`nexus_api.services.lite_home`, que llama a las
mismas funciones que el Inicio del partner. Solo módulo ``panel``.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus_api.services.lite_home import lite_home

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
    data = await lite_home(
        scope.session,
        partner_id=p.partner.id,
        tenant_id=p.tenant_id,
        client_ref=p.client_ref,
        client_name=p.client_name,
        tenant_status=scope.tenant.status,
        with_inbox=p.has("inbox"),
    )
    return LiteHomeOut.model_validate(data, from_attributes=True)
