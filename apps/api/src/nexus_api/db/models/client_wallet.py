"""La bolsa de cada cliente y su libro — spec 047 (migración 0195; ``data-model.md``
§7, research D25 a D29).

Unidades: cien milésimas de la moneda, las de los créditos de hoy. La bolsa nunca
baja de cero (CHECK); los asientos llevan signo y el saldo de después.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

#: La moneda de la cuenta y de las bolsas (research D26).
CURRENCIES: tuple[str, ...] = ("EUR", "USD")
#: Cien milésimas: una unidad de moneda son 100.000 de estas.
UNITS_PER_CURRENCY = 100_000


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=sql_text("now()"))


class ClientWallet(Base):
    """La bolsa: dinero apartado para un cliente (D25)."""

    __tablename__ = "client_wallets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    #: Saldo al empezar el mes más lo asignado en el mes: la base del 20 % (D27).
    month_base_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    month_spent_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    refill_up_to_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    alert_low_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    low_alerted_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    not_enough_alerted_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    empty_alerted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("now()"),
        onupdate=sql_text("now()"),
    )


class WalletTransfer(Base):
    """Un traspaso entre la cuenta del partner y las bolsas, con su cambio."""

    __tablename__ = "wallet_transfers"

    id: Mapped[uuid.UUID] = _uuid()
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    from_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    to_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    partner_amount_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    partner_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    client_amount_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    client_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=Decimal(1))
    fx_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = _now()


class ClientWalletEntry(Base):
    """El lado del cliente de cada asiento."""

    __tablename__ = "client_wallet_entries"

    id: Mapped[uuid.UUID] = _uuid()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    usage_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _now()
    #: El orden de los asientos: los de una transacción comparten ``created_at``
    #: (``now()``), y el cuadre necesita saber cuál fue el último (0196).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)


class AgentMonthlySpend(Base):
    """El gasto del mes de un agente, para su tope (44.1)."""

    __tablename__ = "agent_monthly_spend"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    spent_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FxRate(Base):
    """El cambio de referencia del BCE (plataforma)."""

    __tablename__ = "fx_rates"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    base: Mapped[str] = mapped_column(String(3), primary_key=True)
    quote: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fetched_at: Mapped[datetime] = _now()


class BalanceRequest(Base):
    """«Pedir saldo»: una al día por cliente (45.7)."""

    __tablename__ = "balance_requests"

    id: Mapped[uuid.UUID] = _uuid()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[str | None] = mapped_column(String(280), nullable=True)
    created_at: Mapped[datetime] = _now()


class PartnerBuildBudget(Base):
    """La partida «Construcción y pruebas» del mes (46.5, D29)."""

    __tablename__ = "partner_build_budget"

    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    cap_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BuildBudgetRequest(Base):
    """«Pedir ampliación» de la partida de construcción: una al día."""

    __tablename__ = "build_budget_requests"

    id: Mapped[uuid.UUID] = _uuid()
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = _now()


class WalletMigrationProposal(Base):
    """«Repartir tu saldo en bolsas» (55.3): lo que le queda a cada cliente."""

    __tablename__ = "wallet_migration_proposals"

    id: Mapped[uuid.UUID] = _uuid()
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _now()
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)


__all__ = [
    "CURRENCIES",
    "UNITS_PER_CURRENCY",
    "AgentMonthlySpend",
    "BalanceRequest",
    "BuildBudgetRequest",
    "ClientWallet",
    "ClientWalletEntry",
    "FxRate",
    "PartnerBuildBudget",
    "WalletMigrationProposal",
    "WalletTransfer",
]
