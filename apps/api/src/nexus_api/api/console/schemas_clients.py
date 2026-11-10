"""Esquemas del ciclo de vida, la lista y el Panel del cliente con la consola
nueva (spec 047, de la T062 a la T067; ``contracts/console-api.md`` §2).

Amplían los de hoy (``ClientSummaryOut``, ``ClientOut``, ``ClientPageOut``) sin
quitar nada: la consola de hoy los sigue leyendo igual. El dinero va como
``{amount_micros, currency}`` (cien milésimas de la moneda, contrato §Convenciones)
y ningún campo lleva un coste (C9): lo que el partner ve es lo consumido al precio
que paga, nunca lo que le cuesta a Auphere.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import ClientOut, ClientPageOut, ClientSummaryOut
from .schemas_business import ClientReadOut

Lifecycle = Literal["active", "paused", "archived"]
ClientAction = Literal[
    "edit",
    "assign_balance",
    "request_balance",
    "new_agent",
    "archive",
    "restore",
    "delete",
]
AgentVisible = Literal["archived", "paused", "draft", "serving", "testing", "ready_no_channel"]
Tone = Literal["positive", "info", "warn", "danger", "muted"]
PauseReason = Literal["manual", "no_balance", "agent_cap", "client_paused", "client_archived"]
AttentionCode = Literal[
    "no_balance",
    "channel_problem",
    "integration_reauth",
    "agent_cap",
    "agent_without_channel",
    "low_balance",
    "no_agents",
]
BagState = Literal["ok", "low", "not_enough", "empty", "unlimited", "unassigned"]
MissingSection = Literal["hours", "services", "locations", "sources", "links"]


class MoneyOut(BaseModel):
    amount_micros: int
    currency: Literal["EUR", "USD"]


class VisibleStateOut(BaseModel):
    """``agent_lifecycle.visible_state``: la consola no lo recalcula (25.5)."""

    code: AgentVisible
    tone: Tone
    pause_reason: PauseReason | None = None


class ClientAgentOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    visible_state: VisibleStateOut


class AgentsSummaryOut(BaseModel):
    total: int
    serving: int
    testing: int
    ready_no_channel: int
    draft: int
    paused: int


class AttentionReasonOut(BaseModel):
    code: AttentionCode
    count: int


class AttentionOut(BaseModel):
    """La regla única (requisito 7.2): la misma en la lista y en el Panel."""

    needs: bool
    reasons: list[AttentionReasonOut]


class BagOut(BaseModel):
    """La bolsa del cliente (hasta la ola 7, ``partner_allocations``)."""

    state: BagState
    balance: MoneyOut | None = None
    assigned: MoneyOut | None = None
    spent: MoneyOut | None = None
    pct_spent: float | None = None
    pct_left: float | None = None
    #: Al ritmo de los últimos 7 días completos; ``None`` con menos de 3 días de consumo.
    days_left: float | None = None
    days_estimable: bool = False
    alerts: list[Literal["warn_80", "empty"]] = Field(default_factory=list)


class ClientListRowOut(ClientSummaryOut):
    """Una fila de la lista con la consola nueva (requisito 7.1)."""

    niche: str | None = None
    lifecycle: Lifecycle = "active"
    attention: AttentionOut | None = None
    agents: list[ClientAgentOut] = Field(default_factory=list)
    agents_summary: AgentsSummaryOut | None = None
    bag: BagOut | None = None
    allowed: list[ClientAction] = Field(default_factory=list)


class ClientCountsOut(BaseModel):
    all: int
    attention: int
    active: int
    archived: int


class ClientListOut(ClientPageOut):
    items: list[ClientListRowOut]  # type: ignore[assignment]
    #: Los contadores de los filtros, sobre lo buscado (solo con la consola nueva).
    counts: ClientCountsOut | None = None


class ClientDetailOut(ClientOut):
    """``GET /console/clients/{ref}``: la cabecera, el ciclo de vida, lo que
    edita el modal y la revisión de los datos básicos para ``If-Match``."""

    niche: str | None = None
    info: str | None = None
    website: str | None = None
    country: str | None = None
    price_currency: str | None = None
    wallet_currency: Literal["EUR", "USD"] | None = None
    eu_only: bool | None = None
    #: Spec 047 (54.6): la restricción soberana, que fija Auphere; el partner la ve
    #: como insignia y no la cambia.
    sovereign: bool = False
    lifecycle: Lifecycle = "active"
    revision: int | None = None
    allowed: list[ClientAction] = Field(default_factory=list)


class ClientEditIn(BaseModel):
    """El modal «Editar cliente» (requisito 6.1). Lo que no llega no cambia.
    ``{name, timezone}``, la forma de hoy, sigue valiendo."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    niche: str | None = Field(default=None, min_length=2, max_length=80)
    info: str | None = Field(default=None, max_length=2000)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    timezone: str | None = Field(default=None, max_length=64)
    price_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    wallet_currency: Literal["EUR", "USD"] | None = None
    eu_only: bool | None = None


class AgentLifecycleOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    visible_state: VisibleStateOut
    #: Cómo estaba antes de archivar el cliente (lo que vuelve al restaurarlo).
    before: VisibleStateOut | None = None


class ClientLifecycleOut(BaseModel):
    """Archivar o restaurar (requisitos 6.4 y 6.5)."""

    ref: str
    lifecycle: Lifecycle
    previous: Lifecycle | None = None
    agents: list[AgentLifecycleOut]
    #: «Deshacer» del aviso: ``restore`` tras archivar.
    undo: Literal["restore"] | None = None
    #: Spec 047 (43.13): lo que queda en la bolsa al archivar, para ofrecer
    #: devolverlo a la cuenta (``POST …/bag/lower``). ``None``: no queda nada.
    bag_left: MoneyOut | None = None


class AgentShareOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    spent: MoneyOut
    share_pct: float


class TopAgentOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    visible_state: VisibleStateOut
    spent: MoneyOut
    conversations: int
    #: Lo consumido entre sus conversaciones del mes (al precio del partner).
    spend_per_conversation: MoneyOut | None = None
    #: El tope mensual del agente (ola 7); ``None`` sin tope.
    cap: MoneyOut | None = None


class MonthOut(BaseModel):
    period_start: date
    period_end: date
    conversations: int
    handed_to_person: int
    resolved_without_person: int
    resolved_pct: float | None = None
    spent: MoneyOut


class MissingOut(BaseModel):
    """Lo primero que le falta a la ficha, con su botón (requisito 14.5)."""

    section: MissingSection
    action: Literal["add_hours", "add_services", "add_locations", "add_sources", "add_links"]


class ClientPanelOut(BaseModel):
    """``GET /console/clients/{ref}/panel`` (requisito 14)."""

    ref: str
    name: str
    niche: str | None = None
    lifecycle: Lifecycle
    bag: BagOut
    attention: AttentionOut
    spend_by_agent: list[AgentShareOut]
    month: MonthOut
    top_agents: list[TopAgentOut]
    agents_total: int
    missing: MissingOut | None = None
    read: ClientReadOut
    allowed: list[ClientAction]


__all__ = [
    "AgentLifecycleOut",
    "AgentShareOut",
    "AgentsSummaryOut",
    "AttentionOut",
    "AttentionReasonOut",
    "BagOut",
    "ClientAgentOut",
    "ClientCountsOut",
    "ClientDetailOut",
    "ClientEditIn",
    "ClientLifecycleOut",
    "ClientListOut",
    "ClientListRowOut",
    "ClientPanelOut",
    "MissingOut",
    "MoneyOut",
    "MonthOut",
    "TopAgentOut",
    "VisibleStateOut",
]
