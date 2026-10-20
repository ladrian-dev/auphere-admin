"""Admin wallet — spec 033. Everything a person reads or writes is US$ cents.

The path partner is the source of truth; nothing in a body names a partner.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: US$ 10 000 — the most one top-up can add. A typo with two zeros more should
#: be a 422, not a balance.
MAX_TOPUP_CENTS = 1_000_000


class AdminPurchasedIn(BaseModel):
    """A top-up. The amount in cents; the key from the form that sent it, so a
    double click or a network retry credits once (R3.1, R3.2)."""

    model_config = ConfigDict(extra="forbid")

    amount_cents: int = Field(ge=1, le=MAX_TOPUP_CENTS)
    idempotency_key: uuid.UUID


class AdminWalletOut(BaseModel):
    #: The weekly pool (Companion and teammates). Not money the clients spend.
    included_cents: int
    #: Recharged balance: what the clients' turns spend.
    purchased_cents: int
    available_cents: int
    #: Sum of the clients' monthly caps.
    assigned_cents: int
    included_expires_at: datetime | None
    exhausted: bool
    #: Only on a top-up response: the key was already used, nothing credited.
    duplicate: bool = False


class AdminLedgerOut(BaseModel):
    id: uuid.UUID
    kind: str
    bucket: str
    amount_cents: int
    tenant_id: uuid.UUID | None
    client_name: str | None
    created_at: datetime


class AdminReconcileOut(BaseModel):
    """R2.4: stored recharged balance against the book, in cents and credits.

    The credits are exact; the cents are for reading. ``balanced`` is decided
    on credits so a sub-cent difference is not hidden by rounding."""

    balanced: bool
    stored_cents: int
    expected_cents: int
    difference_credits: int
    credits_cents: int
    debits_cents: int
    expiries_cents: int
