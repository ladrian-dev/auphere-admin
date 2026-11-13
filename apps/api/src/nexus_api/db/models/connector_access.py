"""Qué partners pueden usar cada conector — spec 060.

Dos tablas de plataforma, sin ``tenant_id`` y sin RLS, como ``connectors`` y
``platform_settings`` (research D3): el turno las lee dentro de la sesión del
cliente, que solo fija ``app.tenant_id``, y una RLS por ``app.partner_id``
escondería las filas, lo que con «sin fila = habilitado» abriría todo.

El conector va por su slug, no por ``connectors.id``: los de Composio no tienen
fila hasta el primer consentimiento (research D1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base


class ConnectorAccessDefault(Base):
    """El valor por defecto de un conector para los partners. Sin fila: habilitado."""

    __tablename__ = "connector_access_defaults"
    __table_args__ = (
        CheckConstraint(
            "connector_slug = lower(connector_slug)",
            name="ck_connector_access_defaults_slug_lower",
        ),
    )

    connector_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ConnectorPartnerAccess(Base):
    """La decisión propia de un partner sobre un conector. Las dos vistas del
    panel (partner y conector) escriben aquí."""

    __tablename__ = "connector_partner_access"
    __table_args__ = (
        CheckConstraint(
            "connector_slug = lower(connector_slug)",
            name="ck_connector_partner_access_slug_lower",
        ),
    )

    connector_slug: Mapped[str] = mapped_column(Text, primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    set_by: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
