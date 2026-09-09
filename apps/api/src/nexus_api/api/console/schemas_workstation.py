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
    workdir: str
    app_version: str | None = None
    last_heartbeat_at: datetime | None = None
    #: Derivado del latido, nunca almacenado: si el proceso que lo actualizaría
    #: muere, la presencia decae sola en vez de quedarse mintiendo (§V).
    presence: str
    enrolled_at: datetime


class DeviceIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    platform: str = Field(pattern="^(macos|windows)$")
    workdir: str = Field(min_length=1)
    app_version: str | None = None


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
