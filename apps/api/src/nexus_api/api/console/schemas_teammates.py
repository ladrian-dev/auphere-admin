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
