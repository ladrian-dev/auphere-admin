"""Un agente solo se referencia desde su propio cliente — spec 030 (iteración 3,
garantías 2 y 5 de ``architecture/agent-isolation.md``).

0152 enlazó ``agent_configs.agent_id`` y ``channels.agent_id`` a ``agents.id``
con una clave foránea de una columna. Eso deja que una versión o un número del
cliente A apunte al agente del cliente B: la comprobación de la clave foránea
no pasa por la RLS, y el admin recibe ``agent_id`` por la URL. Ninguna ruta lo
hace hoy a propósito, pero la garantía no puede depender de que nadie se
equivoque.

Aquí la base de datos lo impide: ``agents`` gana una unicidad
``(tenant_id, id)`` y las dos tablas que deciden quién contesta y con qué
apuntan a ella con ``(tenant_id, agent_id)``.

* ``agent_configs`` — ``ON DELETE CASCADE``, como la clave que sustituye.
* ``channels`` — ``ON DELETE SET NULL (agent_id)`` (Postgres 15+): al borrar
  el agente se vacía SOLO ``agent_id``; un ``SET NULL`` a secas vaciaría
  también ``tenant_id``.

Los agentes no se borran (se archivan, §IV); el borrado llega solo con el del
cliente, que se lleva todo a la vez.

Revision ID: 0155_agents_tenant_fk
Revises: 0154_agents_audit_vocab
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0155_agents_tenant_fk"
down_revision: str | Sequence[str] | None = "0154_agents_audit_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _single_fk(table: str) -> str | None:
    """The name of 0152's one-column foreign key to ``agents`` (auto-named)."""
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT c.conname FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_class r ON r.oid = c.confrelid "
                "WHERE c.contype = 'f' AND t.relname = :table AND r.relname = 'agents' "
                "AND array_length(c.conkey, 1) = 1"
            ),
            {"table": table},
        )
        .first()
    )
    return str(row[0]) if row else None


def upgrade() -> None:
    op.create_unique_constraint("uq_agents_tenant_id_id", "agents", ["tenant_id", "id"])
    for table in ("agent_configs", "channels"):
        name = _single_fk(table)
        if name:
            op.drop_constraint(name, table, type_="foreignkey")
    op.execute(
        "ALTER TABLE agent_configs ADD CONSTRAINT fk_agent_configs_tenant_agent "
        "FOREIGN KEY (tenant_id, agent_id) REFERENCES agents (tenant_id, id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE channels ADD CONSTRAINT fk_channels_tenant_agent "
        "FOREIGN KEY (tenant_id, agent_id) REFERENCES agents (tenant_id, id) "
        "ON DELETE SET NULL (agent_id)"
    )


def downgrade() -> None:
    op.drop_constraint("fk_channels_tenant_agent", "channels", type_="foreignkey")
    op.drop_constraint("fk_agent_configs_tenant_agent", "agent_configs", type_="foreignkey")
    # The names Postgres gave 0152's keys, so a later upgrade finds them again.
    op.create_foreign_key(
        "agent_configs_agent_id_fkey",
        "agent_configs",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "channels_agent_id_fkey", "channels", "agents", ["agent_id"], ["id"], ondelete="SET NULL"
    )
    op.drop_constraint("uq_agents_tenant_id_id", "agents", type_="unique")
