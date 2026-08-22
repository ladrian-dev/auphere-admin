"""Respuestas del libro Fase 3 en ``/console/*``. Sin partner_id del cliente."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WalletOut(BaseModel):
    included_remaining: int
    purchased_remaining: int
    available: int
    included_expires_at: datetime | None
    exhausted: bool


class AllocationOut(BaseModel):
    client_ref: str
    cap: int
    remaining: int
