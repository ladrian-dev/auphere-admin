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


class AllocationOut(BaseModel):
    client_ref: str
    cap: int
    remaining: int


class AllocationIn(BaseModel):
    """Solo el tope. El cliente es ``{ref}``; el partner sale del principal."""

    model_config = ConfigDict(extra="forbid")

    cap: int = Field(ge=0)
