"""La membresía mensual de un cliente — spec 077.

Un cliente con membresía solo envía mientras esté activa (requisito 9). La paga
él mismo por Stripe (``payer='stripe'``) o su partner de su saldo
(``payer='partner_wallet'``, un cargo fijo mensual en el libro del partner).

Es del cliente: FORCE RLS por ``tenant_id`` (garantía 1, migración 0242). Una
viva por cliente; quitarla la archiva (``archived_at``), nunca la borra.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey

PAYER_STRIPE: Final = "stripe"
PAYER_PARTNER_WALLET: Final = "partner_wallet"
PAYERS: Final = (PAYER_STRIPE, PAYER_PARTNER_WALLET)

STATUS_PENDING: Final = "pending"
STATUS_ACTIVE: Final = "active"
STATUS_PAST_DUE: Final = "past_due"
STATUS_CANCELED: Final = "canceled"
STATUSES: Final = (STATUS_PENDING, STATUS_ACTIVE, STATUS_PAST_DUE, STATUS_CANCELED)

#: Lo que vale la membresía si el operador no dice otra cosa (Tecfin: 40 USD).
DEFAULT_AMOUNT_CENTS: Final = 4000


class ServiceMembership(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "service_memberships"
    __table_args__ = (
        CheckConstraint(
            "payer IN ('stripe', 'partner_wallet')", name="ck_service_memberships_payer"
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'past_due', 'canceled')",
            name="ck_service_memberships_status",
        ),
        CheckConstraint("amount_cents > 0", name="ck_service_memberships_amount"),
        UniqueConstraint("tenant_id", "id", name="uq_service_memberships_tenant_id"),
    )

    payer: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Bolsa: el importe nuevo, que se cobra a partir del periodo siguiente.
    pending_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=STATUS_PENDING, server_default=text("'pending'")
    )
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Bolsa: el periodo que toca cobrar, guardado ANTES de cobrar. La clave del
    #: cargo sale de aquí, así que repetir tras una caída no cobra dos veces.
    next_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_email: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(String, nullable=True)
    checkout_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure: Mapped[str | None] = mapped_column(String, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[str | None] = mapped_column(String, nullable=True)
