"""Varios agentes por cliente — spec 030, iteración 3 (R14).

Hasta aquí un cliente tenía **un** agente: sus versiones en ``agent_configs``,
una activa. Esta migración crea el agente como cosa propia y lo cuelga de
donde hace falta saber cuál responde:

* ``agents`` — los agentes de un cliente: nombre (único entre los activos del
  cliente) y estado ``active|archived`` (borrar no existe, constitución §IV).
  El *agente principal* es el activo más antiguo; no es columna. RLS ``FORCE``.
* ``agent_configs.agent_id`` — de qué agente es cada versión. Anulable aquí;
  0153 rellena, comprueba y la vuelve obligatoria.
* ``channels.agent_id`` — qué agente contesta en ese número. ``NULL`` = el
  principal (y lo es para las líneas solo de envío y el Playground).
* ``messages.agent_id``, ``usage_records.agent_id``, ``usage_ledger.agent_id``
  — quién escribió y a quién cargar el gasto. Anulables, sin FK: ``messages``
  y ``usage_records`` están particionadas y son historia.
* ``qa.threads.agent_id`` — el hilo de Playground fija su agente.

Los números de versión siguen siendo únicos **por cliente**
(``uq_agent_configs_tenant_version`` no se toca): ver la decisión en
``specs/030-consola-lite-del-cliente/data-model.md``.

Revision ID: 0152_agents
Revises: 0151_inbox_audit_vocab
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0152_agents"
down_revision: str | Sequence[str] | None = "0151_inbox_audit_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_agents_status"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_agents_name_not_blank"),
    )
    op.create_index("ix_agents_tenant_created", "agents", ["tenant_id", "created_at", "id"])
    op.create_index(
        "uq_agents_tenant_name_active",
        "agents",
        ["tenant_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.execute("ALTER TABLE agents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agents FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY agents_tenant_isolation ON agents {_POLICY}")

    op.add_column(
        "agent_configs",
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_agent_configs_agent", "agent_configs", ["agent_id"])
    op.add_column(
        "channels",
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    for table in ("messages", "usage_records", "usage_ledger"):
        op.add_column(table, sa.Column("agent_id", UUID(as_uuid=True), nullable=True))
    op.add_column("threads", sa.Column("agent_id", UUID(as_uuid=True), nullable=True), schema="qa")


def downgrade() -> None:
    op.drop_column("threads", "agent_id", schema="qa")
    for table in ("usage_ledger", "usage_records", "messages"):
        op.drop_column(table, "agent_id")
    op.drop_column("channels", "agent_id")
    op.drop_index("ix_agent_configs_agent", table_name="agent_configs")
    op.drop_column("agent_configs", "agent_id")
    op.execute("DROP POLICY IF EXISTS agents_tenant_isolation ON agents")
    op.drop_table("agents")
