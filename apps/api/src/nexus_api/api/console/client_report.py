"""El informe de un cliente — spec 083 (``specs/083-informe-del-piloto``,
``contracts/console-api.md``).

``GET /console/clients/{ref}/report?from=YYYY-MM-DD&to=YYYY-MM-DD``
[``conversations:read`` + ``usage:read``]: las conversaciones atendidas, cuántas
sin persona, la primera respuesta, las incidencias, el freno de reservas, la
agenda y los recordatorios (si el cliente tiene Reservas) y el gasto del
periodo, con los días del calendario del cliente. Todo lo calcula
``services/client_report.py``; aquí, el periodo y la forma.

``{ref}`` se resuelve bajo el partner del principal (404 opaco) y todo se lee con
la RLS del cliente. Ninguna respuesta lleva palabras de nadie, nombres ni
teléfonos (C8): los motivos son códigos (``cause``) y el dinero va a precio, en
``{amount_micros, currency}``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.services import client_report as svc

from .deps import ClientScope, client_scope

router = APIRouter(prefix="/clients/{ref}")

Cause = Literal[
    "escalated",
    "booking_unbacked",
    "booking_brake",
    "no_balance",
    "agent_cap",
    "paused_agent",
    "paused_channel",
    "paused_client",
    "archived_client",
    "channel_problem",
    "agent_unpublished",
    "no_model",
    "provider_failure",
    "turn_limit",
    "reception_loop",
    "agenda_not_ready",
    "other",
]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MoneyOut(_Out):
    #: Cien milésimas de la moneda de la cuenta del partner.
    amount_micros: int
    currency: str


class DayOut(_Out):
    day: date
    without_person: int
    with_person: int


class HourOut(_Out):
    #: La hora local del primer mensaje del contacto, de 0 a 23.
    hour: int
    without_person: int
    with_person: int


class WeekdayOut(_Out):
    #: ISO: 1 es lunes y 7, domingo.
    weekday: int
    without_person: int
    with_person: int


class ConversationsOut(_Out):
    total: int
    without_person: int
    with_person: int
    without_person_pct: float | None = None
    series: list[DayOut]
    #: 24 filas, de las 0 a las 23 en la zona del cliente (enmienda 2026-11-27).
    by_hour: list[HourOut]
    #: 7 filas, del lunes al domingo.
    by_weekday: list[WeekdayOut]


class FirstResponseOut(_Out):
    #: Conversaciones con algún envío del agente: el denominador del porcentaje.
    answered: int
    within_target: int
    within_target_pct: float | None = None
    median_seconds: int | None = None
    p90_seconds: int | None = None
    #: Conversaciones del periodo sin ningún envío del agente.
    unanswered: int


class CauseOut(_Out):
    cause: Cause
    total: int
    resolved: int


class IncidentOut(_Out):
    at: datetime
    cause: Cause
    resolved_at: datetime | None = None


class IncidentsOut(_Out):
    total: int
    resolved: int
    open: int
    by_cause: list[CauseOut]
    #: Las más recientes primero; como mucho 100.
    items: list[IncidentOut]
    truncated: bool


class BookingBrakeOut(_Out):
    stopped: int
    corrected: int
    handed_over: int


class WhoOut(_Out):
    agent: int
    person: int
    customer: int
    total: int


class ReminderOut(_Out):
    kind: Literal["reminder", "ask_confirmation"]
    sent: int
    failed: int
    skipped: int


class AgendaOut(_Out):
    created: WhoOut
    moved: WhoOut
    cancelled: WhoOut
    #: Las reservas sin confirmar que se liberaron solas.
    released: int
    reminders: list[ReminderOut]


class SpendOut(_Out):
    currency: str
    #: Lo que pagó la bolsa del cliente: conversaciones y pruebas a su cargo.
    total: MoneyOut
    conversations: MoneyOut
    client_tests: MoneyOut
    #: La estimación de los mensajes de Meta (siempre «aprox.»).
    meta: MoneyOut
    #: Lo de la bolsa pasó por un cambio de moneda.
    approx: bool
    per_conversation: MoneyOut | None = None


class TargetsOut(_Out):
    without_person_pct: int
    first_response_pct: int
    first_response_seconds: int


class ClientReportOut(_Out):
    day_from: date = Field(serialization_alias="from")
    day_to: date = Field(serialization_alias="to")
    timezone: str
    since: datetime
    until: datetime
    generated_at: datetime
    #: El cliente cierra solas las conversaciones inactivas.
    autoclose: bool
    targets: TargetsOut
    conversations: ConversationsOut
    first_response: FirstResponseOut
    incidents: IncidentsOut
    booking_brake: BookingBrakeOut
    #: ``None``: el cliente no tiene Reservas.
    agenda: AgendaOut | None = None
    #: ``None``: no se pudo leer (el resto del informe vale).
    spend: SpendOut | None = None


@router.get(
    "/report",
    response_model=ClientReportOut,
    response_model_by_alias=True,
    summary="El informe del cliente para unas fechas (spec 083)",
)
async def get_client_report(
    day_from: date = Query(alias="from", description="Primer día, en el calendario del cliente."),
    day_to: date = Query(alias="to", description="Último día, incluido."),
    scope: ClientScope = Depends(client_scope("conversations:read", "usage:read")),
) -> ClientReportOut:
    try:
        report = await svc.build_report(
            scope.session,
            tenant=scope.tenant,
            partner_id=scope.principal.partner.id,
            day_from=day_from,
            day_to=day_to,
        )
    except svc.PeriodInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": exc.code}
        ) from None
    return ClientReportOut.model_validate(report)


__all__ = ["router"]
