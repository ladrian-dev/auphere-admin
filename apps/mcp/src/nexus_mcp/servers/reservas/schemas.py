"""Esquemas de ``reservas.*`` (spec 043, ``contracts/agent-tools.md``).

**Ninguno tiene un campo de cliente** (spec 014): la persona es la del turno.
Las fechas y horas son las del negocio (``date`` + ``HH:MM``).

El servicio y la persona del equipo van por id o por nombre (``service_name``,
``staff_name``): entre turnos el agente solo conserva el texto, y los ids de un
turno no llegan al siguiente (fallo ``la-reserva-del-turno-siguiente-pierde-los-ids``).
Lo que no se resuelve es un ``refused`` con las opciones, nunca un error.
"""

from __future__ import annotations

import uuid
from datetime import date as Date  # noqa: N812 - un campo se llama «date»
from datetime import datetime

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class Money(OutputModel):
    amount_minor: int
    currency: str


class StaffRef(OutputModel):
    id: uuid.UUID
    name: str


class ServiceRef(OutputModel):
    id: uuid.UUID
    name: str


#: Lo que el modelo lee de un servicio o una persona que no se resolvió. El modelo
#: solo ve la descripción de la herramienta, no esta: cada herramienta lo repite.
UNRESOLVED_HELP = (
    "unknown_service | unknown_staff: the service or team member you named (by id or "
    "name) is not one you can book; ambiguous_service | ambiguous_staff: the name fits "
    "several. Call again in this same turn with one of `services` / `staff` (id or "
    "name), call reservas.services / reservas.find_slots, or ask the customer which one. "
    "Nothing was checked about the time: never tell the customer it is taken or "
    "unavailable because of this."
)
SERVICE_NAME_HELP = (
    "Services mode: the service by name, as the customer said it (e.g. 'corte'), when its "
    "service_id is not in this turn. Ignored when service_id is a service you offer."
)
STAFF_NAME_HELP = (
    "Services mode: the team member by name (e.g. 'Lucía'), when their staff_id is not in "
    "this turn. Omit both for anyone."
)
#: Las opciones para reintentar, con ``unknown_*`` o ``ambiguous_*``.
SERVICES_OPTIONS = "With unknown_service/ambiguous_service: the services to retry with."
STAFF_OPTIONS = (
    "With unknown_staff/ambiguous_staff/not_offered: who does this service, to retry with."
)


class ServiceItem(OutputModel):
    id: uuid.UUID
    name: str
    #: Spec 047: a service that is not bookable (a product, a menu) has no
    #: duration and no times; explain how it is ordered instead.
    bookable: bool = True
    #: Spec 043, R14.1: ``no_staff``, nobody on the team does it right now, so it cannot be
    #: booked. Do not promise a time: say so and pass it to a person.
    why_not: str | None = None
    duration_minutes: int | None
    description: str | None = None
    #: ``none`` (the team confirms it), ``free`` or ``amount`` (``price``).
    price_kind: str = "none"
    price: Money | None = None
    staff: list[StaffRef]


class ServicesInput(InputModel):
    pass


class ServicesOutput(OutputModel):
    mode: str
    services: list[ServiceItem] = Field(default_factory=list)
    max_party: int | None = None


class FindSlotsInput(InputModel):
    date: Date = Field(description="Business-local day to search.")
    service_id: uuid.UUID | None = Field(default=None, description="Services mode: the service.")
    service_name: str | None = Field(default=None, max_length=120, description=SERVICE_NAME_HELP)
    staff_id: uuid.UUID | None = Field(
        default=None, description="Services mode: a team member, or omit for anyone."
    )
    staff_name: str | None = Field(default=None, max_length=120, description=STAFF_NAME_HELP)
    party_size: int | None = Field(default=None, ge=1, le=500, description="Capacity mode.")


class SlotOut(OutputModel):
    time: str
    staff: list[StaffRef] = Field(default_factory=list)
    left: int | None = None


class FindSlotsOutput(OutputModel):
    date: Date
    closed: bool
    why_closed: str | None = None
    slots: list[SlotOut] = Field(default_factory=list)
    first_fit: str | None = None
    refused: str | None = Field(default=None, description=UNRESOLVED_HELP)
    services: list[ServiceRef] = Field(default_factory=list, description=SERVICES_OPTIONS)
    staff: list[StaffRef] = Field(default_factory=list, description=STAFF_OPTIONS)


class BookingBrief(OutputModel):
    id: uuid.UUID
    status: str
    date: Date
    start: str
    end: str
    starts_at: datetime
    party_size: int
    service_name: str | None = None
    staff_name: str | None = None
    note: str | None = None


class CreateInput(InputModel):
    date: Date
    time: str = Field(pattern=HHMM)
    service_id: uuid.UUID | None = None
    service_name: str | None = Field(default=None, max_length=120, description=SERVICE_NAME_HELP)
    staff_id: uuid.UUID | None = None
    staff_name: str | None = Field(default=None, max_length=120, description=STAFF_NAME_HELP)
    any_staff: bool = False
    party_size: int = Field(default=1, ge=1, le=500)
    note: str | None = Field(default=None, max_length=500)
    join_waitlist: bool = Field(
        default=False, description="Services: also notify them if an earlier slot frees up."
    )
    idempotency_key: str = Field(
        min_length=1,
        max_length=120,
        description="Stable for this request: repeating it returns the same booking instead of a second one, e.g. 'reserva:{date}:{time}'.",
    )
    conversation_id: uuid.UUID | None = None


class CreateOutput(OutputModel):
    booking: BookingBrief | None = None
    idempotent_replay: bool = False
    refused: str | None = Field(
        default=None,
        description=(
            "slot_taken | too_large | too_soon | too_far | closed | hours_missing | "
            "not_bookable | not_offered | no_staff | unknown_service | unknown_staff | "
            "ambiguous_service | ambiguous_staff. slot_taken is the only one that means "
            "the time is taken. too_large: escalate to a person with "
            "escalate.escalate_to_human. not_offered: you do not handle that service; "
            "say so and hand the conversation to the team; with `staff`, that team member "
            "does not do it: offer one of them. " + UNRESOLVED_HELP
        ),
    )
    first_fit: str | None = None
    services: list[ServiceRef] = Field(default_factory=list, description=SERVICES_OPTIONS)
    staff: list[StaffRef] = Field(default_factory=list, description=STAFF_OPTIONS)


class ListMineInput(InputModel):
    only_upcoming: bool = True


class ListMineOutput(OutputModel):
    bookings: list[BookingBrief]


class RescheduleInput(InputModel):
    booking_id: uuid.UUID
    date: Date
    time: str = Field(pattern=HHMM)
    staff_id: uuid.UUID | None = None
    staff_name: str | None = Field(
        default=None,
        max_length=120,
        description=(
            "Services mode: another team member by name (e.g. 'Lucía'), when their staff_id "
            "is not in this turn. Omit both to keep the same person."
        ),
    )


class RescheduleOutput(OutputModel):
    booking: BookingBrief | None = None
    refused: str | None = Field(
        default=None,
        description=(
            "slot_taken | too_large | too_soon | too_far | closed | hours_missing | "
            "not_offered | unknown_staff | ambiguous_staff. " + UNRESOLVED_HELP
        ),
    )
    first_fit: str | None = None
    staff: list[StaffRef] = Field(default_factory=list, description=STAFF_OPTIONS)


class CancelInput(InputModel):
    booking_id: uuid.UUID


class CancelOutput(OutputModel):
    booking: BookingBrief
    offered_to_waitlist: bool


class ConfirmAttendanceInput(InputModel):
    attending: bool
    booking_id: uuid.UUID | None = None


class ConfirmAttendanceOutput(OutputModel):
    booking: BookingBrief


class JoinWaitlistInput(InputModel):
    date: Date | None = None
    time: str | None = Field(default=None, pattern=HHMM)
    party_size: int = Field(default=1, ge=1, le=500)
    service_id: uuid.UUID | None = None
    service_name: str | None = Field(default=None, max_length=120, description=SERVICE_NAME_HELP)
    staff_id: uuid.UUID | None = None
    staff_name: str | None = Field(default=None, max_length=120, description=STAFF_NAME_HELP)
    until: Date | None = None
    booking_id: uuid.UUID | None = None


class JoinWaitlistOutput(OutputModel):
    #: ``None`` only with ``refused``: nobody was put on the list.
    entry_id: uuid.UUID | None = None
    status: str | None = None
    refused: str | None = Field(default=None, description="not_offered | " + UNRESOLVED_HELP)
    services: list[ServiceRef] = Field(default_factory=list, description=SERVICES_OPTIONS)
    staff: list[StaffRef] = Field(default_factory=list, description=STAFF_OPTIONS)


class AnswerOfferInput(InputModel):
    accept: bool
    conversation_id: uuid.UUID | None = None


class AnswerOfferOutput(OutputModel):
    result: str  # booked | late_taken | declined | no_offer
    booking: BookingBrief | None = None
