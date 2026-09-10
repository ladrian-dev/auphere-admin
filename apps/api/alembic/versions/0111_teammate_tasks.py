"""Spec 003 — la tarea, que sobrevive al turno (Requisitos 3.2 y 6).

Un run del Companion tiene techo de duración y un aparcado más viejo se da por
muerto. Una aprobación de teammate que caducara por eso sería una pantalla que
miente (§V), así que aquí entra el sujeto que faltaba: **la tarea**. El run pasa
a ser un turno de una tarea; la tarea encadena turnos, es lo que espera a la
persona, y es lo que caduca.

Tres decisiones visibles en el esquema:

* ``companion.teammate_tasks`` cuelga del hilo y hereda su RLS por ``EXISTS``,
  como ``messages`` y ``actions`` desde 0090. No lleva ``principal_id`` como
  llave de la política: la llave es el hilo, y así no hay dos verdades.
* ``actions.task_id`` en vez de un ``expires_at`` nullable: dice **qué tarea**
  espera —que es lo que ``hitl.requested`` necesita— y evita que las filas
  viejas del Companion queden ambiguamente «sin caducidad».
* ``actions.level`` con defecto ``informativo``: lo que ya existía no
  interrumpe a nadie.

Revision ID: 0111_teammate_tasks
Revises: 0110_teammate_audit_vocab
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0111_teammate_tasks"
down_revision: str | Sequence[str] | None = "0110_teammate_audit_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "companion"
_PRINCIPAL = "NULLIF(current_setting('app.principal_id', true), '')"

TASK_STATES = ("en_marcha", "esperandote", "pausada_por_tope", "terminada", "cancelada", "caducada")
LEVELS = ("critico", "aviso", "informativo")


def upgrade() -> None:
    op.create_table(
        "teammate_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "teammate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teammates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("principal_id", sa.String(120), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="en_marcha"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pending_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{s}'" for s in TASK_STATES) + ")",
            name="teammate_tasks_state_check",
        ),
        sa.CheckConstraint(
            "(pending_action_id IS NULL) OR (state = 'esperandote')",
            name="teammate_tasks_pending_only_when_waiting",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_teammate_tasks_state_expires", "teammate_tasks", ["state", "expires_at"], schema=SCHEMA
    )
    op.create_index(
        "ix_teammate_tasks_thread", "teammate_tasks", ["thread_id", "created_at"], schema=SCHEMA
    )
    op.execute(f"ALTER TABLE {SCHEMA}.teammate_tasks ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {SCHEMA}.teammate_tasks FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY companion_teammate_tasks_principal_isolation ON {SCHEMA}.teammate_tasks
        USING (
            EXISTS (
                SELECT 1 FROM {SCHEMA}.threads t
                 WHERE t.id = teammate_tasks.thread_id
                   AND t.principal_id = {_PRINCIPAL}
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM {SCHEMA}.threads t
                 WHERE t.id = teammate_tasks.thread_id
                   AND t.principal_id = {_PRINCIPAL}
            )
        )
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.teammate_tasks TO nexus_app")

    # ``waiting`` es un estado nuevo del run: el turno cerró aparcado y la tarea
    # sigue. El CHECK de 0091 no lo conocía.
    op.drop_constraint("ck_companion_runs_status", "runs", schema=SCHEMA)
    op.create_check_constraint(
        "ck_companion_runs_status",
        "runs",
        "status IN ('running', 'waiting', 'completed', 'cancelled', 'error', 'interrupted', 'paused')",
        schema=SCHEMA,
    )
    op.add_column(
        "runs",
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.teammate_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "actions",
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.teammate_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "actions",
        sa.Column("level", sa.Text(), nullable=False, server_default="informativo"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "actions_level_check",
        "actions",
        "level IN (" + ", ".join(f"'{level}'" for level in LEVELS) + ")",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_companion_actions_status_task", "actions", ["status", "task_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_companion_actions_status_task", table_name="actions", schema=SCHEMA)
    op.drop_constraint("actions_level_check", "actions", schema=SCHEMA)
    op.drop_column("actions", "level", schema=SCHEMA)
    op.drop_column("actions", "task_id", schema=SCHEMA)
    op.drop_column("runs", "task_id", schema=SCHEMA)
    op.drop_constraint("ck_companion_runs_status", "runs", schema=SCHEMA)
    op.create_check_constraint(
        "ck_companion_runs_status",
        "runs",
        "status IN ('running', 'completed', 'cancelled', 'error', 'interrupted', 'paused')",
        schema=SCHEMA,
    )
    op.execute(
        f"DROP POLICY IF EXISTS companion_teammate_tasks_principal_isolation ON {SCHEMA}.teammate_tasks"
    )
    op.drop_index("ix_teammate_tasks_thread", table_name="teammate_tasks", schema=SCHEMA)
    op.drop_index("ix_teammate_tasks_state_expires", table_name="teammate_tasks", schema=SCHEMA)
    op.drop_table("teammate_tasks", schema=SCHEMA)
