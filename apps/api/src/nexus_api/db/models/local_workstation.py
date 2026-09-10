"""Modelos del puesto de trabajo en la máquina del partner (migraciones 0106 y 0107).

**La máquina es del partner** (spec 002, Requisito 4). ``partner_devices`` va con
RLS forzada **por partner y por persona**: la dueña ve las suyas; quien tenga
``app.workstation_manager`` ve todas las de su partner; sin GUC, nada. Lo que sí es
dato de tenant —a qué clientes sirve una máquina y en qué directorio— vive en
``device_client_links``, por tenant, como la lista blanca.

Tres decisiones que se ven en los modelos y son decisiones, no descuidos:

* ``PartnerDevice`` **no tiene columna de estado**. La presencia se deriva de
  ``last_heartbeat_at`` (001-R4.1/4.2): un booleano se quedaría diciendo
  «conectada» si muere el proceso que debía actualizarlo.
* ``credential_generation`` es lo que hace **revocable y rotable** a una credencial
  apátrida: el token lleva ``gen`` y la fila dice cuál vale.
* ``DevicePairingCode`` guarda un **hash**, nunca el código: el código es la
  credencial de un solo uso y no puede quedar consultable.
* ``LocalExecution`` **no guarda la salida del comando** (§III).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

# ── vocabulario cerrado ────────────────────────────────────────────────
#
# Las listas son cerradas a propósito y las repite un CHECK en la base de datos.
# Un motivo fuera de la lista es un motivo que nadie diseñó, y la auditoría dejaría
# de poder responder «por qué».

OUTCOME_COMPLETADA = "completada"
OUTCOME_EXPIRADA = "expirada"
OUTCOME_TERMINADA = "terminada"
OUTCOME_DENEGADA = "denegada"
#: Spec 003 — la ejecución que espera a que la máquina la recoja. Los cuatro de
#: la 001 describían ejecuciones terminadas; sin este, una fila recién creada
#: tendría que mentir diciendo «completada» (§V).
OUTCOME_PENDIENTE = "pendiente"

OUTCOMES: tuple[str, ...] = (
    OUTCOME_PENDIENTE,
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
#: Spec 003 — la persona dijo «nunca». Tiene motivo propio para que la auditoría
#: distinga «lo prohibiste tú» de «ese ejecutable no está permitido».
DENIAL_POLITICA_NUNCA = "politica_nunca"
DENIAL_REASONS: tuple[str, ...] = (
    DENIAL_EJECUTABLE_NO_PERMITIDO,
    DENIAL_METACARACTERES,
    DENIAL_FUERA_DEL_DIRECTORIO,
    DENIAL_SIN_VERIFICAR,
    DENIAL_DISPOSITIVO_AUSENTE,
    DENIAL_POLITICA_NUNCA,
)

#: Spec 003 — los tres modos de la política de ejecución local (Requisito 10).
#: Ordenados de más restrictivo a menos: ``EXEC_MODES.index`` **es** la
#: comparación, y por eso no hay dos sitios donde decir cuál gana.
EXEC_NEVER = "never"
EXEC_ASK = "ask"
EXEC_ALWAYS = "always"
EXEC_MODES: tuple[str, ...] = (EXEC_NEVER, EXEC_ASK, EXEC_ALWAYS)


def most_restrictive(*modes: str | None) -> str:
    """El más restrictivo de los modos dados. Ausente cuenta como ``ask``.

    Es la regla entera del Requisito 10.2 y vive aquí, junto al vocabulario,
    para que nadie la reimplemente con un ``if`` distinto.
    """
    known = [m for m in modes if m in EXEC_MODES]
    if not known:
        return EXEC_ASK
    return min(known, key=EXEC_MODES.index)


PLATFORM_MACOS = "macos"
PLATFORM_WINDOWS = "windows"
PLATFORMS: tuple[str, ...] = (PLATFORM_MACOS, PLATFORM_WINDOWS)

#: Por qué una máquina dejó de valer. Cerrado (Requisito 11.5).
REVOKED_DESEMPAREJADA = "desemparejada"
REVOKED_ARCHIVADA_CONSOLA = "archivada_consola"
REVOKED_PERTENENCIA_RETIRADA = "pertenencia_retirada"
REVOKED_REASONS: tuple[str, ...] = (
    REVOKED_DESEMPAREJADA,
    REVOKED_ARCHIVADA_CONSOLA,
    REVOKED_PERTENENCIA_RETIRADA,
)


class PartnerDevice(Base):
    """La máquina emparejada: del partner, de la persona que la emparejó, con su latido."""

    __tablename__ = "partner_devices"
    __table_args__ = (
        CheckConstraint("platform IN ('macos', 'windows')", name="partner_devices_platform_check"),
        CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN ("
            + ", ".join(f"'{r}'" for r in REVOKED_REASONS)
            + ")",
            name="partner_devices_revoked_reason_check",
        ),
        Index("ix_partner_devices_partner_enrolled", "partner_id", "enrolled_at"),
        Index("ix_partner_devices_principal", "principal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    #: La persona dueña — decisión 9: privado por persona. Texto, no UUID: es
    #: ``partner_memberships.user_id``, que lo es. **Se lee**: la RLS filtra por ella.
    principal_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    #: Lo que la máquina dijo de sí misma al emparejar; propuesto como nombre.
    hostname: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Sube en cada renovación. La credencial lleva ``gen`` y solo vale la actual
    #: (y la anterior, 60 s).
    credential_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    credential_rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    #: Borrar no existe: se archiva, y queda por qué.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeviceClientLink(Base):
    """A qué cliente sirve una máquina y en qué directorio. Dato de tenant (RLS)."""

    __tablename__ = "device_client_links"
    __table_args__ = (
        Index(
            "uq_device_client_links_active",
            "device_id",
            "tenant_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index("ix_device_client_links_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner_devices.id", ondelete="CASCADE"), nullable=False
    )
    #: NULL hasta que **la máquina** lo declare (Requisito 7). La consola no teclea rutas.
    workdir: Mapped[str | None] = mapped_column(Text, nullable=True)
    declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declared_by_device: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: La persona que vinculó desde la consola.
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DevicePairingCode(Base):
    """El código de emparejamiento: un uso, diez minutos, hash en reposo. Del partner."""

    __tablename__ = "device_pairing_codes"
    __table_args__ = (Index("ix_device_pairing_codes_partner", "partner_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    #: Quien pidió el código será la dueña de la máquina que lo canjee.
    principal_id: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partner_devices.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LocalExecutable(Base):
    """Un ejecutable permitido para un tenant. Se añade solo desde la consola."""

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
    """Permiso durable de unos argumentos para un ejecutable ya permitido."""

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
    action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalExecution(Base):
    """Qué se ejecutó o se denegó, con su motivo. Nunca qué dijo el comando."""

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
    children_reaped: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    #: Spec 003 — de quién y de qué trabajo fue. La persona es la que decidió;
    #: el teammate **nunca** es el actor de la auditoría (§5.6 de la revisión).
    principal_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    teammate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: Cuándo se entregó a la máquina. Una ``pendiente`` sin esto todavía no la
    #: recogió nadie; con esto y sin cerrar, se colgó y hay que caducarla.
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PartnerLocalExecPolicy(Base):
    """El techo del partner (Requisito 10.1). Ausente significa ``ask``."""

    __tablename__ = "partner_local_exec_policy"
    __table_args__ = (
        CheckConstraint(
            "ceiling IN (" + ", ".join(f"'{m}'" for m in EXEC_MODES) + ")",
            name="partner_local_exec_policy_ceiling_check",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), primary_key=True
    )
    ceiling: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ask'"))
    updated_by: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class PrincipalLocalExecPref(Base):
    """Lo que **una persona** prefiere, global o por ejecutable (Requisito 10.1).

    De la persona y de su partner: la RLS lleva las dos claves, así que la
    preferencia de una no toca a nadie más. Es lo que hace que «permitir
    siempre» no pueda convertirse en un permiso de equipo por descuido.
    """

    __tablename__ = "principal_local_exec_prefs"
    __table_args__ = (
        CheckConstraint(
            "mode IN (" + ", ".join(f"'{m}'" for m in EXEC_MODES) + ")",
            name="principal_local_exec_prefs_mode_check",
        ),
        Index(
            "uq_principal_local_exec_prefs_global",
            "partner_id",
            "principal_id",
            unique=True,
            postgresql_where=text("executable IS NULL"),
        ),
        Index(
            "uq_principal_local_exec_prefs_executable",
            "partner_id",
            "principal_id",
            "executable",
            unique=True,
            postgresql_where=text("executable IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    principal_id: Mapped[str] = mapped_column(Text, nullable=False)
    #: NULL = la preferencia global de esta persona.
    executable: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "DENIAL_POLITICA_NUNCA",
    "DENIAL_REASONS",
    "EXEC_ALWAYS",
    "EXEC_ASK",
    "EXEC_MODES",
    "EXEC_NEVER",
    "OUTCOMES",
    "OUTCOME_PENDIENTE",
    "PLATFORMS",
    "REVOKED_REASONS",
    "DeviceClientLink",
    "DevicePairingCode",
    "LocalArgumentGrant",
    "LocalExecutable",
    "LocalExecution",
    "PartnerDevice",
    "PartnerLocalExecPolicy",
    "PrincipalLocalExecPref",
    "most_restrictive",
]
