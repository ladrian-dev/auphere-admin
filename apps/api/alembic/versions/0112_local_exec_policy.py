"""Spec 003 — la política de ejecución local, en tres capas (Requisito 10).

La 001 dejó **la lista blanca de ejecutables**, que es del cliente y se toca
desde la consola. La 003 le añade encima dos capas que solo pueden **restringir**:

* ``partner_local_exec_policy`` — el techo del partner, que ponen owner y admin
  desde la página de equipo. Ausente significa ``ask``.
* ``principal_local_exec_prefs`` — lo que cada persona prefiere, global o por
  ejecutable. Es **de la persona y de su partner**: la preferencia de una no
  toca a nadie más, que es la razón de que la RLS lleve las dos claves.

Y la regla que las une: **gana la más restrictiva**, y ninguna de las dos puede
ampliar lo que la lista blanca permite. El ``never`` de la persona deniega con
motivo propio (``politica_nunca``) para que la auditoría distinga «lo prohibiste
tú» de «ese ejecutable no está permitido».

``local_executions`` gana además de quién y de qué tarea fue cada ejecución, y
cuándo se entregó a la máquina — sin lo cual no se puede reintentar ni caducar.

Revision ID: 0112_local_exec_policy
Revises: 0111_teammate_tasks
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0112_local_exec_policy"
down_revision: str | Sequence[str] | None = "0111_teammate_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "NULLIF(current_setting('app.partner_id', true), '')::uuid"
_PRINCIPAL = "NULLIF(current_setting('app.principal_id', true), '')"

MODES = ("ask", "always", "never")

#: El motivo nuevo. Los cinco de la 001 no se tocan.
DENIAL_POLITICA_NUNCA = "politica_nunca"
DENIAL_REASONS = (
    "ejecutable_no_permitido",
    "metacaracteres",
    "fuera_del_directorio",
    "sin_verificar",
    "dispositivo_ausente",
    DENIAL_POLITICA_NUNCA,
)


def upgrade() -> None:
    modes = ", ".join(f"'{m}'" for m in MODES)

    op.create_table(
        "partner_local_exec_policy",
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        #: Una fila sin valor explícito no restringe: el defecto seguro lo pone
        #: la preferencia de la persona, que es ``ask``.
        sa.Column("ceiling", sa.Text(), nullable=False, server_default="always"),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"ceiling IN ({modes})", name="partner_local_exec_policy_ceiling_check"),
    )
    op.execute("ALTER TABLE partner_local_exec_policy ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_local_exec_policy FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY partner_local_exec_policy_partner ON partner_local_exec_policy
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )

    op.create_table(
        "principal_local_exec_prefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_id", sa.Text(), nullable=False),
        #: NULL = la preferencia global de esta persona.
        sa.Column("executable", sa.Text(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"mode IN ({modes})", name="principal_local_exec_prefs_mode_check"),
        sa.CheckConstraint(
            r"executable IS NULL OR executable ~ '^[A-Za-z0-9._+-]{1,128}$'",
            name="principal_local_exec_prefs_executable_check",
        ),
    )
    # Dos índices parciales y no un UNIQUE con NULL dentro: en Postgres dos
    # NULL son distintos, así que un UNIQUE ``(partner, principal, executable)``
    # dejaría meter dos preferencias globales para la misma persona.
    op.create_index(
        "uq_principal_local_exec_prefs_global",
        "principal_local_exec_prefs",
        ["partner_id", "principal_id"],
        unique=True,
        postgresql_where=sa.text("executable IS NULL"),
    )
    op.create_index(
        "uq_principal_local_exec_prefs_executable",
        "principal_local_exec_prefs",
        ["partner_id", "principal_id", "executable"],
        unique=True,
        postgresql_where=sa.text("executable IS NOT NULL"),
    )
    op.execute("ALTER TABLE principal_local_exec_prefs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE principal_local_exec_prefs FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY principal_local_exec_prefs_owner ON principal_local_exec_prefs
        USING (partner_id = {_PARTNER} AND principal_id = {_PRINCIPAL})
        WITH CHECK (partner_id = {_PARTNER} AND principal_id = {_PRINCIPAL})
        """
    )

    # ── la auditoría gana contexto ────────────────────────────────────
    op.add_column("local_executions", sa.Column("principal_id", sa.Text(), nullable=True))
    op.add_column("local_executions", sa.Column("teammate_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("local_executions", sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "local_executions", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True)
    )
    #: ``pendiente`` es lo que espera a que la máquina la recoja. Los cuatro de
    #: la 001 describían ejecuciones **terminadas**; sin este, una fila recién
    #: creada tendría que mentir diciendo «completada».
    op.execute("ALTER TABLE local_executions DROP CONSTRAINT local_executions_outcome_check")
    op.create_check_constraint(
        "local_executions_outcome_check",
        "local_executions",
        "outcome IN ('pendiente', 'completada', 'expirada', 'terminada', 'denegada')",
    )
    op.execute("ALTER TABLE local_executions DROP CONSTRAINT local_executions_denial_reason_check")
    op.create_check_constraint(
        "local_executions_denial_reason_check",
        "local_executions",
        "denial_reason IS NULL OR denial_reason IN ("
        + ", ".join(f"'{r}'" for r in DENIAL_REASONS)
        + ")",
    )
    op.create_index(
        "ix_local_executions_device_pending",
        "local_executions",
        ["device_id", "outcome"],
        postgresql_where=sa.text("outcome = 'pendiente'"),
    )


def downgrade() -> None:
    op.drop_index("ix_local_executions_device_pending", table_name="local_executions")
    op.execute("ALTER TABLE local_executions DROP CONSTRAINT local_executions_denial_reason_check")
    op.create_check_constraint(
        "local_executions_denial_reason_check",
        "local_executions",
        "denial_reason IS NULL OR denial_reason IN ('ejecutable_no_permitido', 'metacaracteres', "
        "'fuera_del_directorio', 'sin_verificar', 'dispositivo_ausente')",
    )
    op.execute("ALTER TABLE local_executions DROP CONSTRAINT local_executions_outcome_check")
    op.create_check_constraint(
        "local_executions_outcome_check",
        "local_executions",
        "outcome IN ('completada', 'expirada', 'terminada', 'denegada')",
    )
    op.drop_column("local_executions", "dispatched_at")
    op.drop_column("local_executions", "task_id")
    op.drop_column("local_executions", "teammate_id")
    op.drop_column("local_executions", "principal_id")
    op.execute("DROP POLICY IF EXISTS principal_local_exec_prefs_owner ON principal_local_exec_prefs")
    op.drop_index("uq_principal_local_exec_prefs_executable", table_name="principal_local_exec_prefs")
    op.drop_index("uq_principal_local_exec_prefs_global", table_name="principal_local_exec_prefs")
    op.drop_table("principal_local_exec_prefs")
    op.execute("DROP POLICY IF EXISTS partner_local_exec_policy_partner ON partner_local_exec_policy")
    op.drop_table("partner_local_exec_policy")
