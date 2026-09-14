"""Esquemas de ``/admin/signups`` — spec 006, Requisito 8."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SignupPartnerOut(BaseModel):
    """La empresa que salió de una solicitud, cuando salió alguna."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    #: ``active`` / ``suspended``. **No es el nivel** y no se mezcla con él.
    status: str
    #: ``free`` cuando no hay fila en ``partner_subscriptions``: la ausencia de
    #: fila *es* Free, un estado válido y diseñado (ADR-037).
    tier: str


class SignupRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    status: str
    #: ``password`` o ``google``. Nunca ``null``: obligar a quien lee el panel a
    #: saber que `null` significa «con contraseña» es trasladarle un detalle de
    #: almacenamiento.
    provider: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None
    #: ``None`` mientras el registro está a medias. Que sea nulo es la señal de
    #: que esto **todavía no es un partner**, y es el requisito, no un descuido.
    partner: SignupPartnerOut | None
