"""Esquemas de ``/console/clients/{ref}/workstation``.

Dos reglas de este repo que se ven en los nombres de los campos:

* **Ningún esquema lleva ``tenant_id``.** El partner habla ``external_client_ref``;
  el id interno no sale de la API.
* **Nada con forma de cuerpo de mensaje.** Por eso el motivo de una denegación viaja
  como ``denial_code`` —vocabulario cerrado, no prosa— y no como ``reason``. La
  auditoría responde "qué pasó", no "qué dijo el comando": la salida no se guarda.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DeviceOut(BaseModel):
    id: uuid.UUID
    display_name: str
    platform: str
    #: Del vínculo con este cliente; NULL mientras la máquina no lo declare.
    workdir: str | None = None
    app_version: str | None = None
    last_heartbeat_at: datetime | None = None
    #: Derivado del latido, nunca almacenado: si el proceso que lo actualizaría
    #: muere, la presencia decae sola en vez de quedarse mintiendo (§V).
    presence: str
    enrolled_at: datetime


class ExecutableOut(BaseModel):
    id: uuid.UUID
    executable: str
    added_by: str
    added_at: datetime


class ExecutableIn(BaseModel):
    #: El mismo patrón que el CHECK de la base: sin separadores de ruta y sin
    #: metacaracteres. Lo que el gate rechazaría no se llega a guardar.
    executable: str = Field(pattern=r"^[A-Za-z0-9._+-]{1,128}$")


class ExecutionOut(BaseModel):
    id: uuid.UUID
    executable: str
    outcome: str
    denial_code: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    exit_code: int | None = None
    children_reaped: int


class SessionToolEntry(BaseModel):
    """Una fila del catálogo.

    ``reaches_network`` es **opcional a propósito**: ausente significa *sin
    declarar*, y sin declarar cuenta como que alcanza la red (Requisito 14.2).
    Ponerle un defecto `False` convertiría el olvido en permiso.
    """

    name: str
    reaches_network: bool | None = None


class SessionToolCatalogOut(BaseModel):
    tools: list[SessionToolEntry]


# ── spec 002: el puesto de trabajo a nivel de partner ───────────────────


class PairingCodeOut(BaseModel):
    """El código, **una sola vez**; la base guarda su hash."""

    code: str
    expires_at: datetime
    ttl_seconds: int


class MachineClientOut(BaseModel):
    ref: str
    name: str | None = None
    workdir: str | None = None
    needs_directory: bool


class MachineOut(BaseModel):
    id: uuid.UUID
    display_name: str
    hostname: str
    platform: str
    app_version: str | None = None
    presence: str
    last_heartbeat_at: datetime | None = None
    enrolled_at: datetime
    #: La persona dueña. Solo se rellena para quien puede ver todas (gestor).
    owner_user_id: str
    owner_display_name: str | None = None
    mine: bool
    archived_at: datetime | None = None
    archived_reason: str | None = None
    clients: list[MachineClientOut]


class MachineRenameIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class LinkClientIn(BaseModel):
    client_ref: str = Field(min_length=1, max_length=255)


class SetupStepOut(BaseModel):
    key: str
    done: bool
    #: Cuántas cosas quedan (clientes sin directorio, clientes sin ejecutables…).
    pending: int = 0


class SetupOut(BaseModel):
    complete: bool
    steps: list[SetupStepOut]


# ── spec 003: ejecutar en la máquina (Requisitos 3.3 y 10) ─────────────


class ExecutionIn(BaseModel):
    """Lo que un teammate pide ejecutar.

    ``args`` es lista y **nunca** una cadena: una cadena volvería a abrir la
    puerta que el gate cierra comprobando metacaracteres elemento a elemento
    (001-R2.4). ``cwd_relative`` es relativo al directorio que la máquina
    declaró para este cliente; la contención lo vuelve a comprobar allí.
    """

    executable: str = Field(min_length=1, max_length=128)
    args: list[str] = Field(default_factory=list, max_length=64)
    cwd_relative: str | None = Field(default=None, max_length=1024)


class ExecutionOutcomeOut(BaseModel):
    """Lo que la plataforma contesta a quien pidió ejecutar.

    Tres decisiones y ninguna más: se ejecutó, hace falta permiso, o no.
    ``stdout_sample`` solo viene en la primera, es una muestra acotada y va
    marcada como **dato**: lo que un programa escribe no son instrucciones
    (§III), y quien lo entregue al modelo tiene que decirlo.
    """

    decision: str
    executable: str
    argv_signature: str
    execution_id: uuid.UUID | None = None
    outcome: str | None = None
    exit_code: int | None = None
    stdout_sample: str | None = None
    untrusted: bool = False
    #: Vocabulario cerrado, nunca prosa (C8).
    denial_code: str | None = None
    #: El techo del partner bajó lo que esta persona pidió (Requisito 10.4).
    capped: bool = False
    #: El modo que de verdad se aplicó: `ask` · `always` · `never`.
    mode: str = "ask"


class LocalExecPolicyOut(BaseModel):
    ceiling: str
    global_mode: str
    per_executable: list[LocalExecPrefOut] = Field(default_factory=list)
    #: `effective` ya lleva el techo aplicado; `capped` dice si lo bajó.
    effective: str
    capped: bool


class LocalExecPrefOut(BaseModel):
    executable: str
    mode: str
    effective: str
    capped: bool


class LocalExecPrefIn(BaseModel):
    #: `null` = la preferencia global de esta persona.
    executable: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._+-]{1,128}$")
    mode: str = Field(pattern="^(ask|always|never)$")


class LocalExecCeilingIn(BaseModel):
    ceiling: str = Field(pattern="^(ask|always|never)$")


class LocalExecCeilingOut(BaseModel):
    ceiling: str
    updated_by: str | None = None
