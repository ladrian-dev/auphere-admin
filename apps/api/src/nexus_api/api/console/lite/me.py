"""``GET /console/lite/me`` — quién entra en la consola lite (spec 030, R2.1).

Lo que la consola necesita para pintar su armazón: la persona, su negocio, sus
módulos, sus canales y a quién pedir más saldo (plan D10). Nada del partner
salvo su nombre, y solo para eso. Ningún id de tenant ni de partner.
"""

from __future__ import annotations

import uuid
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus_api.config import get_settings
from nexus_api.db.models import Channel, ChannelStatus
from nexus_api.services import inbox_view

from .deps import LiteScope, lite_scope

router = APIRouter()


class LiteUserOut(BaseModel):
    email: str
    name: str


class LiteClientOut(BaseModel):
    name: str
    modules: list[str]


class BalanceContactOut(BaseModel):
    kind: Literal["partner", "auphere"]
    name: str


class LiteChannelOut(BaseModel):
    kind: str
    connected: bool


class LiteAgentOut(BaseModel):
    id: uuid.UUID
    name: str


class LiteMeOut(BaseModel):
    user: LiteUserOut
    client: LiteClientOut
    balance_contact: BalanceContactOut
    # Spec 030 (iteration 3): the client's active agents, principal first.
    agents: list[LiteAgentOut]
    channels: list[LiteChannelOut]


@router.get("/me", response_model=LiteMeOut)
async def read_me(scope: LiteScope = Depends(lite_scope())) -> LiteMeOut:
    principal = scope.principal
    partner = principal.partner
    if partner.slug in get_settings().auphere_partner_slug_set:
        contact = BalanceContactOut(kind="auphere", name="Auphere")
    else:
        contact = BalanceContactOut(kind="partner", name=partner.name)
    rows = await scope.session.execute(sa.select(Channel.type, Channel.status))
    channels = [
        LiteChannelOut(
            kind=str(getattr(kind, "value", kind)), connected=state == ChannelStatus.ACTIVE
        )
        for kind, state in rows.all()
    ]
    member = principal.membership
    return LiteMeOut(
        user=LiteUserOut(email=member.email, name=member.display_name or member.email),
        client=LiteClientOut(name=principal.client_name, modules=list(principal.modules)),
        balance_contact=contact,
        agents=[
            LiteAgentOut(id=aid, name=name)
            for aid, name in await inbox_view.client_agents(scope.session)
        ],
        channels=channels,
    )
