"""Respuestas del libro Fase 3 en ``/console/*``. Sin partner_id del cliente."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: Spec 027: the partner reads and writes money. Every amount is an integer
#: number of cents of ``currency``; the ledger stays in credits and only
#: ``billing.pricing`` converts. No float: a float of money lies in the last
#: cent.
MAX_CENTS = 100_000_000  # 1 000 000 US$, far above any real cap


class WalletOut(BaseModel):
    included_remaining_cents: int
    purchased_remaining_cents: int
    available_cents: int
    #: ``available`` minus the sum of caps. Negative when the caps promise
    #: more than there is.
    reserve_cents: int
    included_expires_at: datetime | None
    exhausted: bool
    #: Spec 004 (R7.1): the share of the included pool already used.
    included_percent_used: float = 0.0
    currency: str = "USD"


class AllocationOut(BaseModel):
    client_ref: str
    cap_cents: int
    remaining_cents: int
    currency: str = "USD"


class MoveAllocationIn(BaseModel):
    """Spec 016 (R3.1): mover tope entre dos clientes propios, de una vez.
    Spec 027: la cantidad es dinero."""

    model_config = ConfigDict(extra="forbid")

    from_ref: str = Field(min_length=1, max_length=120)
    to_ref: str = Field(min_length=1, max_length=120)
    amount_cents: int = Field(ge=1, le=MAX_CENTS)


class MoveAllocationOut(BaseModel):
    """Los dos topes después del movimiento. ``from``/``to`` como en el body."""

    model_config = ConfigDict(populate_by_name=True)

    from_: AllocationOut = Field(alias="from")
    to: AllocationOut


class AllocationIn(BaseModel):
    """Solo el tope. El cliente es ``{ref}``; el partner sale del principal."""

    model_config = ConfigDict(extra="forbid")

    cap_cents: int = Field(ge=0, le=MAX_CENTS)


# ``PurchasedIn`` se borró con la spec 005, junto a la ruta que lo usaba. Era
# el cuerpo de una llamada con la que un partner se acreditaba saldo sin pagar;
# ahora el crédito entra por el aviso del pago confirmado. Dejar el esquema sin
# su ruta invitaría a volver a colgarle una.
