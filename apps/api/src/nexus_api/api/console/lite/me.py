"""``GET /console/lite/me`` — quién entra en la consola lite (spec 030, R2.1).

Lo que la consola necesita para pintar su armazón: la persona, su negocio, sus
módulos, sus canales y a quién pedir más saldo (plan D10). Nada del partner
salvo su nombre, y solo para eso. Ningún id de tenant ni de partner.
"""

from __future__ import annotations

import uuid
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from nexus_api.config import get_settings
from nexus_api.db.models import Channel, ChannelStatus, ClientPhone, ReservationSettings
from nexus_api.services import inbox_view
from nexus_api.services.business_hours import (
    business_hours_label,
    parse_business_hours,
    to_canonical,
)

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


class LiteBusinessOut(BaseModel):
    """Spec 045 (R5.1): el horario del perfil del negocio y su zona. La app lo
    lee para «silenciar fuera de horario»; se edita en la web (Reservas)."""

    timezone: str
    hours: dict[str, list[dict[str, str]]] | None
    hours_label: str | None


class LiteReservasOut(BaseModel):
    """Spec 043: el modo de Reservas (las palabras las pone cada pantalla)."""

    mode: Literal["services", "capacity"]
    capacity_kind: str | None


class LiteMeOut(BaseModel):
    user: LiteUserOut
    client: LiteClientOut
    #: Spec 031 (R3.2): los módulos del cliente en el orden de la barra. Es la
    #: **única** fuente del orden para la consola y para la app; ninguna de las
    #: dos lo reescribe.
    nav: list[str]
    balance_contact: BalanceContactOut
    # Spec 030 (iteration 3): the client's active agents, principal first.
    agents: list[LiteAgentOut]
    channels: list[LiteChannelOut]
    business: LiteBusinessOut
    reservas: LiteReservasOut | None = None


async def _locale(scope: LiteScope, request: Request) -> str:
    """El idioma de la persona: el de su teléfono; en la web, el que pide el
    navegador."""
    phone_id = scope.principal.phone_id
    if phone_id is not None:
        phone = await scope.session.get(ClientPhone, phone_id)
        if phone is not None:
            return phone.locale
    return "en" if request.headers.get("accept-language", "").lower().startswith("en") else "es"


async def business_of(scope: LiteScope, request: Request) -> LiteBusinessOut:
    tenant = scope.tenant
    hours = parse_business_hours(tenant.business_hours)
    return LiteBusinessOut(
        timezone=tenant.timezone or "UTC",
        hours=to_canonical(hours) if hours is not None else None,
        hours_label=business_hours_label(hours, await _locale(scope, request))
        if hours is not None
        else None,
    )


@router.get("/me", response_model=LiteMeOut)
async def read_me(request: Request, scope: LiteScope = Depends(lite_scope())) -> LiteMeOut:
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
        nav=list(principal.modules),
        balance_contact=contact,
        agents=[
            LiteAgentOut(id=aid, name=name)
            for aid, name in await inbox_view.client_agents(scope.session)
        ],
        channels=channels,
        business=await business_of(scope, request),
        reservas=await _reservas(scope),
    )


async def _reservas(scope: LiteScope) -> LiteReservasOut | None:
    if not scope.principal.has("reservas"):
        return None
    settings = await scope.session.get(ReservationSettings, scope.principal.tenant_id)
    if settings is None:
        return None
    return LiteReservasOut(mode=settings.mode, capacity_kind=settings.capacity_kind)  # type: ignore[arg-type]
