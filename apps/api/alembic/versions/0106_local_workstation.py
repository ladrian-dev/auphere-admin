"""Beta 2 — el puesto de trabajo del teammate en la máquina del partner.

Cuatro tablas para la superficie 3a: el dispositivo declarado, la lista blanca de
ejecutables, los permisos de argumentos y la auditoría de ejecución local.

Las cuatro llevan ``tenant_id`` y RLS **forzada**. Esto no es ceremonia: el runtime
lee varias tablas sin ``WHERE tenant_id`` a propósito, apoyándose en que Postgres
filtre, y ``test_21`` rompe la suite el día que aparece una tabla con ``tenant_id``
sin política.

Dos decisiones que se ven en el DDL y conviene leer antes de cambiarlas:

* ``partner_devices`` **no tiene columna de estado**. La presencia se deriva de
  ``last_heartbeat_at``. Guardar un booleano invitaría a que la pantalla siguiera
  diciendo "conectado" cuando el proceso que debía actualizarlo ha muerto, y §V no
  admite una pantalla que miente.
* ``local_executions`` **no guarda la salida del comando**. Guarda que ocurrió, no
  lo que dijo: la salida es contenido leído (§III) y el hilo de un teammate no
  transcribe texto de cliente final.

Revision ID: 0106_local_workstation
Revises: 0105_console_audit_vocab_auth
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0106_local_workstation"
down_revision: str | Sequence[str] | None = "0105_console_audit_vocab_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES: tuple[str, ...] = (
    "partner_devices",
    "local_executables",
    "local_argument_grants",
    "local_executions",
)

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

#: Lista cerrada. Un motivo fuera de ella es un motivo que nadie diseñó.
DENIAL_REASONS = (
    "ejecutable_no_permitido",
    "metacaracteres",
    "fuera_del_directorio",
    "sin_verificar",
    "dispositivo_ausente",
)

OUTCOMES = ("completada", "expirada", "terminada", "denegada")


def upgrade() -> None:
    op.create_table(
        "partner_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("workdir", sa.Text(), nullable=False),
        sa.Column("app_version", sa.Text(), nullable=True),
        # Sin columna de estado: la presencia se deriva de aquí.
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Borrar no existe: se archiva.
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "platform IN ('macos', 'windows')", name="partner_devices_platform_check"
        ),
    )
    op.create_index("ix_partner_devices_tenant", "partner_devices", ["tenant_id"])

    op.create_table(
        "local_executables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("executable", sa.Text(), nullable=False),
        sa.Column("added_by", sa.Text(), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        # Sin separadores de ruta ni metacaracteres: el gate lo revalida, pero la
        # base de datos no acepta guardar lo que el gate tendría que rechazar.
        sa.CheckConstraint(
            r"executable ~ '^[A-Za-z0-9._+-]{1,128}$'",
            name="local_executables_name_check",
        ),
    )
    # Un ejecutable activo por tenant. Los archivados no estorban.
    op.create_index(
        "uq_local_executables_active",
        "local_executables",
        ["tenant_id", "executable"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )

    op.create_table(
        "local_argument_grants",
        # uuid5 determinista sobre (tenant, ejecutable, firma): una carrera no crea dos.
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "executable_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("local_executables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("argv_signature", sa.Text(), nullable=False),
        # Apunta a companion.actions, donde vive la aprobación durable (state_hash,
        # decided_at, decided_by). Sin FK a propósito: esa tabla está bajo RLS por
        # principal y en otro contexto acotado; una FK entre los dos ataría el
        # ciclo de vida de una aprobación al de un permiso y complicaría su RLS.
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_local_argument_grants_active",
        "local_argument_grants",
        ["tenant_id", "executable_id", "argv_signature"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "local_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Verbatim: el ejecutable se guarda aunque después se archive de la lista.
        sa.Column("executable", sa.Text(), nullable=False),
        sa.Column("argv_signature", sa.Text(), nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("children_reaped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint(
            "outcome IN (" + ", ".join(f"'{o}'" for o in OUTCOMES) + ")",
            name="local_executions_outcome_check",
        ),
        sa.CheckConstraint(
            "denial_reason IS NULL OR denial_reason IN ("
            + ", ".join(f"'{r}'" for r in DENIAL_REASONS)
            + ")",
            name="local_executions_denial_reason_check",
        ),
        # Una denegación sin motivo es una denegación que nadie puede auditar.
        sa.CheckConstraint(
            "(outcome <> 'denegada') OR (denial_reason IS NOT NULL)",
            name="local_executions_denial_needs_reason_check",
        ),
    )
    op.create_index(
        "ix_local_executions_tenant_started", "local_executions", ["tenant_id", "started_at"]
    )

    # ── RLS por tenant, fail-closed ────────────────────────────────────────
    # Sin `SET LOCAL app.tenant_id`, cero filas. No hay lectura por encima del
    # tenant en estas cuatro: FORCE alcanza también al dueño de la tabla.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = {_TENANT})
            WITH CHECK (tenant_id = {_TENANT})
            """
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE IF EXISTS {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("local_executions")
    op.drop_table("local_argument_grants")
    op.drop_table("local_executables")
    op.drop_table("partner_devices")
