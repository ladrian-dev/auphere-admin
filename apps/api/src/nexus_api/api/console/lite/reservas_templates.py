"""``GET /console/lite/reservas/templates`` — cómo van las seis plantillas de
WhatsApp de Reservas (spec 043, requisito 15.7).

Mismo alcance que el resto de Reservas (``lite_scope("reservas")``): solo la
persona de un cliente con el módulo, bajo la RLS de su cliente. Lee el espejo de
la WABA del cliente (``services/reservations/templates.templates_view``), que
mantienen el webhook de Meta y ``reservation-templates-cron``; **no llama a
Meta**. El motivo de un rechazo viaja como código: el texto libre de Meta no
llega a la persona del cliente (el partner lo ve entero en su consola).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus_api.services.reservations import templates

from .deps import LiteScope, lite_scope

router = APIRouter(prefix="/reservas")
SCOPE = lite_scope("reservas")


class ReservasTemplateOut(BaseModel):
    #: El nombre de la plantilla en Meta (``reserva_confirmada``…), el que se le
    #: dice al partner.
    name: str
    state: templates.TemplateState
    #: Solo si ``state = rejected``: el motivo de Meta, como código.
    rejection: templates.Rejection | None = None
    #: Solo si ``state = not_created``: no hay número de WhatsApp, se está
    #: creando, o se borró en Meta.
    why_not_created: templates.NotCreated | None = None
    #: Desde cuándo está así (lo último que dijo Meta).
    since: datetime | None = None


class ReservasTemplatesOut(BaseModel):
    #: El cliente tiene un número de WhatsApp de Meta conectado.
    whatsapp: bool
    approved: int
    items: list[ReservasTemplateOut]


@router.get("/templates", response_model=ReservasTemplatesOut)
async def read_templates(scope: LiteScope = Depends(SCOPE)) -> ReservasTemplatesOut:
    view = await templates.templates_view(scope.session)
    return ReservasTemplatesOut(
        whatsapp=view.whatsapp,
        approved=view.approved,
        items=[
            ReservasTemplateOut(
                name=i.name,
                state=i.state,
                rejection=i.rejection,
                why_not_created=i.why_not_created,
                since=i.since,
            )
            for i in view.items
        ],
    )


__all__ = ["ReservasTemplateOut", "ReservasTemplatesOut", "router"]
