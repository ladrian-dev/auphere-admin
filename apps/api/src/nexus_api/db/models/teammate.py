"""El roster de teammates (spec 003, Requisito 1; migración 0109).

Un teammate es un dato del **partner**: todos sus miembros ven los mismos
(decisión 8) y la RLS filtra por ``app.partner_id`` sin mirar a la persona. Lo
que sí es de la persona es el **hilo** con ese teammate (``companion.threads``,
RLS por ``principal_id`` desde 0090), y eso no cambia aquí.

Tres decisiones visibles en las columnas:

* ``tool_names`` es la verdad operativa del catálogo y **siempre** un
  subconjunto de ``ALL_TOOLS`` (Requisito 4); ``permissions`` es lo que el
  formulario pintó — los cinco interruptores del diseño — y se conserva para
  volver a pintarlo, no para decidir nada.
* No hay ``DELETE``: la base lo revoca a ``nexus_app`` (R2.6). Se archiva.
* No hay ``scope`` (``personal`` / ``team``): decisión 8 lo eliminó.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

TEAMMATE_ACTIVE = "active"
TEAMMATE_ARCHIVED = "archived"
TEAMMATE_STATUSES: tuple[str, ...] = (TEAMMATE_ACTIVE, TEAMMATE_ARCHIVED)

#: La semilla de oficios del diseño v3 (``jobList``). El partner puede escribir el suyo.
JOB_SEED: tuple[str, ...] = (
    "Atención al cliente",
    "Ventas y CRM",
    "Investigación",
    "Desarrollo",
    "Finanzas",
    "Datos y reportes",
    "Documentos",
    "Operaciones",
)

#: Los cinco interruptores del formulario (diseño v3, ``perms``).
PERMISSION_KEYS: tuple[str, ...] = ("read", "write", "spend", "publish", "contact")


class Teammate(Base):
    """Un teammate del partner: oficio, modelo, catálogo y política."""

    __tablename__ = "teammates"
    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="teammates_name_len"),
        CheckConstraint("char_length(job) BETWEEN 1 AND 80", name="teammates_job_len"),
        CheckConstraint("status IN ('active', 'archived')", name="teammates_status_check"),
        CheckConstraint(
            "(status = 'archived') = (archived_at IS NOT NULL)",
            name="teammates_archived_consistent",
        ),
        Index("ix_teammates_partner_status", "partner_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    job: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    #: Subconjunto de ``ALL_TOOLS``. Lo valida ``services.teammate_catalog``.
    tool_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    permissions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    local_exec: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.status == TEAMMATE_ACTIVE


#: Los campos cuyo cambio la persona necesita ver en su hilo (R2.4, migración
#: 0113). El nombre no está: cambiarlo no cambia lo que el teammate puede hacer.
CHANGED_FIELDS: tuple[str, ...] = ("job", "permissions", "local_exec", "model")


class TeammateChange(Base):
    """«Este teammate cambió», como hecho del partner.

    No es una copia de una nota en cada hilo —eso exigiría escribir dentro del
    hilo de otra persona, que es justo lo que la RLS de 0090 impide— sino el
    hecho, del que cada hilo deriva su nota al cargar. Guarda **qué campos**
    cambiaron y quién, nunca los valores: la pantalla ya enseña lo que hay hoy.
    """

    __tablename__ = "teammate_changes"
    __table_args__ = (
        Index("ix_teammate_changes_teammate_at", "teammate_id", "changed_at"),
        CheckConstraint(
            "fields <@ ARRAY['job', 'permissions', 'local_exec', 'model']::text[] "
            "AND array_length(fields, 1) >= 1",
            name="teammate_changes_fields_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    teammate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teammates.id", ondelete="CASCADE"), nullable=False
    )
    fields: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    changed_by: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
