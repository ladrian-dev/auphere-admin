"""Respuestas del libro Fase 3 en ``/console/*``. Sin partner_id del cliente."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WalletOut(BaseModel):
    included_remaining: int
    purchased_remaining: int
    available: int
    reserve: int
    included_expires_at: datetime | None
    exhausted: bool
    #: Spec 004 (R7.1) — el TAMAÑO del pool semanal, para que la consola pueda
    #: pintar una proporción sin derivarla de restas que no significan eso.
    #: El partner no ve esta cifra; ve el porcentaje que sale de ella.
    pool_size: int = 0
    included_percent_used: float = 0.0


class AllocationOut(BaseModel):
    client_ref: str
    cap: int
    remaining: int


class AllocationIn(BaseModel):
    """Solo el tope. El cliente es ``{ref}``; el partner sale del principal."""

    model_config = ConfigDict(extra="forbid")

    cap: int = Field(ge=0)


class PurchasedIn(BaseModel):
    """Recarga del cubo purchased. El partner sale del principal."""

    model_config = ConfigDict(extra="forbid")

    qty: int = Field(gt=0)
