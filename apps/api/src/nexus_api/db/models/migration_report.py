"""Los informes del ensayo y la activación de la consola nueva — spec 047 (migración
0201; ``data-model.md`` §10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base


class MigrationReport(Base):
    """Un ensayo (``dry_run``) o una activación (``activation``) de un partner."""

    __tablename__ = "migration_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sql_text("gen_random_uuid()")
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    eval_diff: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    audience_diff: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Por qué lo lanzó la persona de Auphere (cada escritura lleva su motivo).
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )


__all__ = ["MigrationReport"]
