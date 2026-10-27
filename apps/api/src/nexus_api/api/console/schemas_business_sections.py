"""Esquemas de las secciones de Negocio — spec 047, T057 y T058 (``console-api.md`` §3).

Datos básicos, sedes, horario, fechas especiales, servicios, políticas y
preguntas frecuentes. Cada sección devuelve su ``revision`` (y el ``ETag``) y
``allowed``: la consola no pinta lo que la persona no puede hacer (§V). Ninguna
respuesta lleva ids internos del cliente.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
)

Action = Literal["edit"]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HHMM = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
Close = Annotated[str, StringConstraints(pattern=r"^(([01][0-9]|2[0-3]):[0-5][0-9]|24:00)$")]
SectionState = Literal["complete", "read_pending", "pending", "optional"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShiftIn(_In):
    open: HHMM
    #: Igual o anterior a la apertura: cierra al día siguiente.
    close: Close
    #: Lo que la consola leyó; se ignora (lo decide la hora de cierre).
    overnight: bool | None = None


class ShiftOut(_Out):
    open: str
    close: str
    #: «Nocturno · cierra al día siguiente».
    overnight: bool


class _Section(_Out):
    revision: int
    state: SectionState
    allowed: list[Action]


# ── datos básicos ──────────────────────────────────────────────────────────


class BasicsIn(_In):
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)] | None = None
    niche: Annotated[str, StringConstraints(min_length=2, max_length=80)] | None = None
    info: Annotated[str, StringConstraints(max_length=2000)] | None = None
    website: Annotated[str, StringConstraints(max_length=300)] | None = None
    country: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")] | None = None
    timezone: Annotated[str, StringConstraints(max_length=64)] | None = None
    price_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    eu_only: bool | None = None


class BasicsOut(_Section):
    name: str
    niche: str
    info: str | None
    website: str | None
    country: str | None
    timezone: str
    price_currency: str | None
    eu_only: bool


# ── horario ────────────────────────────────────────────────────────────────


class HoursIn(_In):
    layout: Literal["blocks", "daily"] = "daily"
    days: dict[Day, list[ShiftIn]] = Field(default_factory=dict)
    #: Pasar a «Por bloques» con días distintos: la persona ya vio qué se pierde.
    confirm_loss: bool = False
    #: Solo una sede: quitar su horario propio y usar el del negocio.
    inherit: bool = False
    #: Solo el negocio: quedarse sin horario («el agente dirá que no lo sabe»).
    clear: bool = False


class HoursOut(_Section):
    location_id: uuid.UUID | None
    #: Una sede sin horario propio enseña el del negocio.
    inherits: bool
    layout: Literal["blocks", "daily"] | None
    days: dict[Day, list[ShiftOut]]
    #: «Así lo dirá el agente» (requisito 10.5); ``None`` sin horario.
    label: str | None


# ── sedes ──────────────────────────────────────────────────────────────────


class LocationIn(_In):
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    address: Annotated[str, StringConstraints(max_length=300)] | None = None
    phone_e164: Annotated[str, StringConstraints(max_length=20)] | None = None


class LocationPatchIn(_In):
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    address: Annotated[str, StringConstraints(max_length=300)] | None = None
    phone_e164: Annotated[str, StringConstraints(max_length=20)] | None = None


class LocationOut(_Out):
    id: uuid.UUID
    name: str
    address: str | None
    phone_e164: str | None
    own_hours: bool
    #: La frase que vale para la sede: la suya o la del negocio.
    label: str | None
    archived: bool


class LocationsOut(_Section):
    items: list[LocationOut]
    created_id: uuid.UUID | None = None


# ── fechas especiales ──────────────────────────────────────────────────────


class SpecialDateIn(_In):
    name: Annotated[str, StringConstraints(max_length=80)] | None = None
    location_id: uuid.UUID | None = None
    from_: date = Field(alias="from")
    to: date
    closed: bool
    shifts: list[ShiftIn] = Field(default_factory=list, max_length=6)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SpecialDatePatchIn(_In):
    name: Annotated[str, StringConstraints(max_length=80)] | None = None
    location_id: uuid.UUID | None = None
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None
    closed: bool | None = None
    shifts: list[ShiftIn] | None = Field(default=None, max_length=6)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SpecialDateOut(_Out):
    id: uuid.UUID
    name: str
    location_id: uuid.UUID | None
    from_: date = Field(serialization_alias="from")
    to: date
    closed: bool
    shifts: list[ShiftOut]
    archived: bool


class SpecialDatesOut(_Section):
    items: list[SpecialDateOut]
    created_id: uuid.UUID | None = None


# ── servicios ──────────────────────────────────────────────────────────────


class PriceIn(_In):
    kind: Literal["none", "free", "amount"]
    amount_minor: int | None = Field(default=None, ge=0, le=10**12)


class PriceOut(_Out):
    """La forma del ClientSpec: ``{kind}`` o ``{kind: "amount", amount_minor}``."""

    kind: Literal["none", "free", "amount"]
    amount_minor: int | None = None

    @model_serializer(mode="wrap")
    def _without_empty_amount(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        out: dict[str, Any] = handler(self)
        if out.get("amount_minor") is None:
            out.pop("amount_minor", None)
        return out


class ServiceIn(_In):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None
    bookable: bool = True
    duration_min: int | None = None
    price: PriceIn = Field(default_factory=lambda: PriceIn(kind="none"))
    #: Quién lo hace en Reservas: ``"all"`` o la lista de personas.
    staff: Literal["all"] | list[uuid.UUID] = "all"


class ServicePatchIn(_In):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None
    bookable: bool | None = None
    duration_min: int | None = None
    price: PriceIn | None = None
    staff: Literal["all"] | list[uuid.UUID] | None = None


class ServiceAgentsIn(_In):
    mode: Literal["all_agents", "list"]
    agent_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class AgentsOfService(_Out):
    mode: Literal["all_agents", "list"]
    agent_ids: list[uuid.UUID]


class AgentRef(_Out):
    id: uuid.UUID
    name: str


class AgentOption(AgentRef):
    #: «Atiende todos los servicios».
    serves_all: bool


class ServiceOut(_Out):
    id: uuid.UUID
    name: str
    description: str | None
    bookable: bool
    duration_min: int | None
    price: PriceOut
    currency: str
    staff: Literal["all"] | list[uuid.UUID]
    agents: AgentsOfService
    #: «Lo usan» (requisito 11.2).
    used_by: list[AgentRef]
    archived: bool


class ServicesOut(_Section):
    #: La moneda de los precios del negocio y sus decimales (requisito 11.7).
    currency: str
    exponent: int
    items: list[ServiceOut]
    agents: list[AgentOption]
    created_id: uuid.UUID | None = None


# ── políticas y preguntas frecuentes ───────────────────────────────────────

Policy = Annotated[str, StringConstraints(max_length=1000)]


class PoliciesIn(_In):
    cancellation: Policy | None = None
    payments: Policy | None = None
    deposit: Policy | None = None
    no_show: Policy | None = None


class PoliciesOut(_Section):
    cancellation: str | None
    payments: str | None
    deposit: str | None
    no_show: str | None


class FaqIn(_In):
    q: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    a: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class FaqPatchIn(_In):
    q: Annotated[str, StringConstraints(min_length=1, max_length=300)] | None = None
    a: Annotated[str, StringConstraints(min_length=1, max_length=2000)] | None = None
    #: Confirmar una «Sugerido · confirma» es ``false``.
    suggested: bool | None = None


class FaqOut(_Out):
    id: uuid.UUID
    q: str
    a: str
    suggested: bool


class FaqsOut(_Section):
    items: list[FaqOut]
    created_id: uuid.UUID | None = None


__all__ = [
    "AgentOption",
    "AgentRef",
    "AgentsOfService",
    "BasicsIn",
    "BasicsOut",
    "FaqIn",
    "FaqOut",
    "FaqPatchIn",
    "FaqsOut",
    "HoursIn",
    "HoursOut",
    "LocationIn",
    "LocationOut",
    "LocationPatchIn",
    "LocationsOut",
    "PoliciesIn",
    "PoliciesOut",
    "PriceIn",
    "PriceOut",
    "ServiceAgentsIn",
    "ServiceIn",
    "ServiceOut",
    "ServicePatchIn",
    "ServicesOut",
    "ShiftIn",
    "ShiftOut",
    "SpecialDateIn",
    "SpecialDateOut",
    "SpecialDatePatchIn",
    "SpecialDatesOut",
]
