"""Spec 017 (R5): lo que la consola lee y escribe en «Capacidades».

Una capacidad es lo que el agente sabe hacer. Por dentro puede ser una
herramienta del catálogo o una habilidad del bundle; para el partner es la
misma cosa y por eso salen por la misma puerta.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from .capability_names import Function

Kind = Literal["tool", "skill"]
#: Los dos que quedan. «needs_approval» se retira (R5.7): hoy se comporta
#: como un bloqueo y engaña a quien lo elige.
CapabilityMode = Literal["always", "blocked"]


class CapabilityConnectorOut(BaseModel):
    slug: str
    display_name: str
    status: str


class CapabilityModeOut(BaseModel):
    default: CapabilityMode
    #: Lo que el partner fijó a mano, si lo hizo.
    override: CapabilityMode | None = None
    effective: CapabilityMode
    #: Lo que la pantalla puede ofrecer. Nunca incluye «needs_approval».
    options: list[CapabilityMode] = Field(
        default_factory=lambda: cast(list[CapabilityMode], ["always", "blocked"])
    )


class CapabilityTechnicalOut(BaseModel):
    """Lo que solo importa cuando algo va mal: nombre interno, tipo, versión
    y etiquetas. La pantalla lo pliega (R5.6)."""

    name: str
    kind: Kind
    version: str | None = None
    tags: list[str] = Field(default_factory=list)


class CapabilityOut(BaseModel):
    key: str
    kind: Kind
    business_name: str
    description: str
    function: Function
    sectors: list[str] = Field(default_factory=list)
    #: La plantilla del sector la enciende por defecto (R5.3).
    recommended: bool = False
    #: Se está viendo pese a ser de otro sector (solo con `all=true`).
    other_sector: bool = False
    enabled: bool
    enabled_in_active: bool
    #: Encendida **y** con lo que necesita para funcionar. Una capacidad
    #: encendida sin su conector no es utilizable, pero sí es una decisión
    #: legítima del partner (owner, 2026-09-26).
    usable: bool
    connector: CapabilityConnectorOut | None = None
    mode: CapabilityModeOut | None = None
    read_only: bool = False
    destructive: bool = False
    technical: CapabilityTechnicalOut


class CapabilityGroupOut(BaseModel):
    function: Function
    items: list[CapabilityOut]


class CapabilitiesOut(BaseModel):
    """El envoltorio: qué sector filtra, en qué versión estamos y cuántas se
    quedaron fuera por no ser de este sector."""

    sector: str | None = None
    has_draft: bool = False
    version: int | None = None
    active_version: int | None = None
    hidden_by_sector: int = 0
    groups: list[CapabilityGroupOut] = Field(default_factory=list)


class CapabilityUpdateIn(BaseModel):
    """**Un cambio por llamada** (R5.4).

    La pantalla vieja mandaba la lista blanca entera en cada guardado, así
    que dos personas editando a la vez se pisaban sin enterarse. Aquí se
    nombra la capacidad y lo que cambia de ella.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=128)
    kind: Kind
    enabled: bool | None = None
    #: `needs_approval` **sí** se acepta en el tipo, para poder contestar
    #: «mode_not_supported» y no un volcado de validación: quien lo pide
    #: merece saber por qué no, no que el servidor le hable en esquema.
    mode: Literal["always", "blocked", "needs_approval"] | None = None


class CapabilityUpdatedOut(BaseModel):
    capability: CapabilityOut
    draft_created: bool
    version: int | None = None
    updated_at: datetime | None = None
