"""Esquemas de ``/console/teammates`` (spec 003).

Mismas reglas que el resto de ``/console/*``: ningún esquema lleva
``partner_id``, ``principal_id`` ni ``tenant_id``; nada con forma de cuerpo de
mensaje. Los identificadores de estado (``my_state``) son enums estables y la
pantalla pone la palabra.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .schemas_companion import CompanionBudgetOut

#: Lo que la persona tiene con un teammate, derivado de su último run.
MY_STATES: tuple[str, ...] = ("en_marcha", "esperandote", "en_pausa_por_tope", "en_espera")


class PermissionsIn(BaseModel):
    """Los cinco interruptores del formulario (diseño v3)."""

    read: bool = True
    write: bool = False
    spend: bool = False
    publish: bool = False
    contact: bool = False


class TeammateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    job: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)
    permissions: PermissionsIn = Field(default_factory=PermissionsIn)
    local_exec: bool = False


class TeammatePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    job: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    permissions: PermissionsIn | None = None
    local_exec: bool | None = None


class TeammateOut(BaseModel):
    id: uuid.UUID
    name: str
    job: str
    model: str
    tool_names: list[str]
    permissions: dict[str, Any]
    local_exec: bool
    status: str
    created_at: datetime
    archived_at: datetime | None = None
    #: Derivados del hilo de **la persona que pregunta** con este teammate.
    my_state: str
    my_unread: bool
    my_thread_id: uuid.UUID | None = None
    #: Título de la última tarea terminada de la persona con este teammate (US2).
    last_done: str | None = None


class ModelChoiceOut(BaseModel):
    id: str
    note: str
    cost_label: str


class JobsOut(BaseModel):
    jobs: list[str]
    models: list[ModelChoiceOut]


# ── la tarea y la bandeja (spec 003, US2) ──────────────────────────────


class TaskOut(BaseModel):
    """Una tarea de la persona. ``state`` y ``cause`` son enums estables."""

    id: uuid.UUID
    thread_id: uuid.UUID
    teammate_id: uuid.UUID
    title: str
    state: str
    expires_at: datetime
    current_run_id: uuid.UUID | None = None
    pending_action_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None


class TeammateRefOut(BaseModel):
    id: uuid.UUID
    name: str


class InboxItemOut(BaseModel):
    """Una tarjeta de Pendientes. Sin cuerpos de mensaje y sin ids de tenant."""

    action_id: uuid.UUID
    task_id: uuid.UUID | None
    thread_id: uuid.UUID
    run_id: uuid.UUID | None
    teammate: TeammateRefOut
    title: str
    kind: str
    level: str
    client_ref: str | None
    proposed_at: datetime
    #: `false` cuando el permiso que exige aplicar esto no es del rol: la
    #: tarjeta lo dice **antes**, en vez de dejar decidir y comerse un 403 (§V).
    can_decide: bool


class TeammateChangeOut(BaseModel):
    """Una nota de «este teammate cambió» (R2.4).

    ``fields`` son identificadores estables —``job``, ``permissions``,
    ``local_exec``, ``model``— y la pantalla escribe la frase. No lleva valores:
    ni los de antes ni los de ahora. Un histórico de configuraciones es otra
    cosa, y esta nota solo tiene que explicar por qué el teammate se comporta
    distinto desde aquí.
    """

    id: uuid.UUID
    fields: list[str]
    #: Quién lo cambió, con el nombre que tenía entonces; ``null`` si no consta.
    by: str | None
    at: datetime


# ── el consumo de Cuenta (spec 003, US5) ───────────────────────────────


class TeammateUsageRowOut(BaseModel):
    """Lo que el equipo entero gastó con un teammate este mes.

    En **tokens**, que es la unidad del medidor y del tope (C9). No hay
    importe: ``companion.runs`` no guarda con qué modelo corrió cada turno, así
    que un número en dólares sería una estimación con el precio de hoy — y un
    número inventado en una pantalla de consumo es peor que no darlo.
    """

    teammate_id: uuid.UUID
    name: str
    input_tokens: int
    output_tokens: int
    runs: int


class TeammatesUsageOut(BaseModel):
    """``budget`` es **el mismo objeto** que ``/console/companion/budget``
    (R9.1): un medidor, no dos que se parezcan."""

    budget: CompanionBudgetOut
    by_teammate: list[TeammateUsageRowOut]
