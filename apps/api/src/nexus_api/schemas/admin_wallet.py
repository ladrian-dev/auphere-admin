"""Admin C3 wallet — path partner is the source of truth. No partner_id in body."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminPurchasedIn(BaseModel):
    """Recarga purchased. El partner sale del path, nunca del cuerpo."""

    model_config = ConfigDict(extra="forbid")

    qty: int = Field(gt=0)


class AdminWalletOut(BaseModel):
    included_remaining: int
    purchased_remaining: int
    available: int
    reserve: int
    included_expires_at: datetime | None
    exhausted: bool


class AdminLedgerOut(BaseModel):
    id: uuid.UUID
    bucket: str
    qty: int
    reason: str
    created_at: datetime
