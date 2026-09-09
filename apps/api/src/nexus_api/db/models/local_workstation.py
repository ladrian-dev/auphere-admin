"""Modelos del puesto de trabajo en la máquina del partner (migración 0106).

Las cuatro tablas viven en ``public`` y están protegidas por RLS **por
``tenant_id``**, forzada. El código que las toca DEBE aplicar ``app.tenant_id``
dentro de la transacción; sin el GUC no se ve ninguna fila, que es lo que se quiere.

Dos cosas que se notan al leer los modelos y son decisiones, no descuidos:

* ``PartnerDevice`` **no tiene columna de estado**. La presencia se deriva de
  ``last_heartbeat_at`` (Requisito 4.1/4.2). Un booleano se quedaría diciendo
  "conectado" si muere el proceso que debía actualizarlo, y §V no admite una
  pantalla que miente.
* ``LocalExecution`` **no guarda la salida del comando**. Guarda que ocurrió, no lo
  que dijo: la salida es contenido leído (§III) y el hilo de un teammate no
  transcribe texto de cliente final.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

# ── vocabulario cerrado ────────────────────────────────────────────────
#
# Las dos listas son cerradas a propósito y las repite un CHECK en la base de
# datos. Un motivo de denegación fuera de la lista es un motivo que nadie diseñó,
# y la auditoría dejaría de poder responder "por qué".

OUTCOME_COMPLETADA = "completada"
OUTCOME_EXPIRADA = "expirada"
OUTCOME_TERMINADA = "terminada"
OUTCOME_DENEGADA = "denegada"
OUTCOMES: tuple[str, ...] = (
    OUTCOME_COMPLETADA,
    OUTCOME_EXPIRADA,
    OUTCOME_TERMINADA,
    OUTCOME_DENEGADA,
)

DENIAL_EJECUTABLE_NO_PERMITIDO = "ejecutable_no_permitido"
DENIAL_METACARACTERES = "metacaracteres"
DENIAL_FUERA_DEL_DIRECTORIO = "fuera_del_directorio"
DENIAL_SIN_VERIFICAR = "sin_verificar"
DENIAL_DISPOSITIVO_AUSENTE = "dispositivo_ausente"
DENIAL_REASONS: tuple[str, ...] = (
    DENIAL_EJECUTABLE_NO_PERMITIDO,
    DENIAL_METACARACTERES,
    DENIAL_FUERA_DEL_DIRECTORIO,
    DENIAL_SIN_VERIFICAR,
    DENIAL_DISPOSITIVO_AUSENTE,
)

PLATFORM_MACOS = "macos"
PLATFORM_WINDOWS = "windows"
PLATFORMS: tuple[str, ...] = (PLATFORM_MACOS, PLATFORM_WINDOWS)


class PartnerDevice(Base):
    """La máquina declarada por el partner, su latido y su directorio de trabajo."""

    __tablename__ = "partner_devices"
    __table_args__ = (
        CheckConstraint("platform IN ('macos', 'windows')", name="partner_devices_platform_check"),
        Index("ix_partner_devices_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    #: La persona dueña del dispositivo — decisión 9: hilo privado por persona.
    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    #: Directorio declarado por el partner. Se revalida al usarse, no solo al declararse.
    workdir: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    #: Borrar no existe: se archiva.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalExecutable(Base):
    """La lista blanca: qué puede ejecutarse en la máquina de este tenant.

    Solo se modifica desde la consola y por una persona (Requisito 2.1). Arranca
    **vacía** por tenant: no hay ejecutables por defecto y no hay lista global — un
    default global sería justamente el "global" que §I prohíbe.
    """

    __tablename__ = "local_executables"
    __table_args__ = (
        CheckConstraint(
            r"executable ~ '^[A-Za-z0-9._+-]{1,128}$'", name="local_executables_name_check"
        ),
        Index(
            "uq_local_executables_active",
            "tenant_id",
            "executable",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    executable: Mapped[str] = mapped_column(Text, nullable=False)
    added_by: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalArgumentGrant(Base):
    """Permiso durable para unos argumentos de un ejecutable **ya permitido**.

    Nunca crea ejecutables: si el ejecutable no está en la lista, no hay grant que
    valga (Requisito 2.2). El ``id`` es un uuid5 determinista sobre
    ``(tenant, ejecutable, firma de argv)`` y se escribe con UPSERT, para que dos
    aprobaciones simultáneas no creen dos filas.
    """

    __tablename__ = "local_argument_grants"
    __table_args__ = (
        Index(
            "uq_local_argument_grants_active",
            "tenant_id",
            "executable_id",
            "argv_signature",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    executable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("local_executables.id", ondelete="CASCADE"), nullable=False
    )
    argv_signature: Mapped[str] = mapped_column(Text, nullable=False)
    #: Apunta a ``companion.actions``, donde vive la aprobación durable. Sin FK:
    #: esa tabla está bajo RLS por principal y en otro contexto acotado.
    action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalExecution(Base):
    """La auditoría: una fila por intento, **incluidas las denegaciones**."""

    __tablename__ = "local_executions"
    __table_args__ = (
        CheckConstraint(
            "outcome IN (" + ", ".join(f"'{o}'" for o in OUTCOMES) + ")",
            name="local_executions_outcome_check",
        ),
        CheckConstraint(
            "denial_reason IS NULL OR denial_reason IN ("
            + ", ".join(f"'{r}'" for r in DENIAL_REASONS)
            + ")",
            name="local_executions_denial_reason_check",
        ),
        CheckConstraint(
            "(outcome <> 'denegada') OR (denial_reason IS NOT NULL)",
            name="local_executions_denial_needs_reason_check",
        ),
        Index("ix_local_executions_tenant_started", "tenant_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner_devices.id", ondelete="CASCADE"), nullable=False
    )
    #: Verbatim: se guarda aunque el ejecutable se archive después de la lista.
    executable: Mapped[str] = mapped_column(Text, nullable=False)
    argv_signature: Mapped[str] = mapped_column(Text, nullable=False)
    grant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    denial_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Cuántos procesos hijos hubo que recoger (Requisito 12.3).
    children_reaped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


__all__ = [
    "DENIAL_DISPOSITIVO_AUSENTE",
    "DENIAL_EJECUTABLE_NO_PERMITIDO",
    "DENIAL_FUERA_DEL_DIRECTORIO",
    "DENIAL_METACARACTERES",
    "DENIAL_REASONS",
    "DENIAL_SIN_VERIFICAR",
    "OUTCOMES",
    "OUTCOME_COMPLETADA",
    "OUTCOME_DENEGADA",
    "OUTCOME_EXPIRADA",
    "OUTCOME_TERMINADA",
    "PLATFORMS",
    "PLATFORM_MACOS",
    "PLATFORM_WINDOWS",
    "LocalArgumentGrant",
    "LocalExecutable",
    "LocalExecution",
    "PartnerDevice",
]
