"""El turno fiable — spec 047, ola 1 (migración 0176, ``data-model.md`` §5).

- ``turn_effects``: una acción con efecto (reservar, cobrar, enviar un enlace,
  enviar la respuesta, cobrar el turno) ocurre como mucho una vez aunque el turno
  se reintente. La clave es ``{turn_id}:{acción}`` y es única por cliente
  (requisito 1.3).
- ``meta_reconciliation_runs``: lo que Meta dice que entregó frente a lo
  guardado, por canal y día (requisito 2.6).

Por cliente, con RLS FORCE; la conciliación apunta a su canal con FK compuesta.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey


class TurnEffect(UUIDPrimaryKey, Base):
    __tablename__ = "turn_effects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_turn_effects_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_turn_effects_key"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    effect: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    #: What the effect answered the first time, returned as-is on a retry.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class MetaReconciliationRun(UUIDPrimaryKey, Base):
    __tablename__ = "meta_reconciliation_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_meta_reconciliation_tenant_id"),
        UniqueConstraint("tenant_id", "channel_id", "date", name="uq_meta_reconciliation_day"),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name="fk_meta_reconciliation_channel",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The column is called ``date`` (data-model.md); the type is spelled
    # ``_dt.date`` so the annotation does not resolve to the attribute itself.
    date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    meta_count: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_count: Mapped[int] = mapped_column(Integer, nullable=False)
    diff: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
