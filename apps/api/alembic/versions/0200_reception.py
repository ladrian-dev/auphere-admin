"""Recepción que deriva — spec 047, T177 y T178 (requisito 53; ``data-model.md`` §3 y §5).

Lo que el modelo de datos pide ya está desde la ola 4: ``agents.is_reception``
(0190) y, en ``conversations``, ``handled_by_agent_id`` con su FK compuesta
``(tenant_id, handled_by_agent_id) → agents (tenant_id, id)`` y
``reception_hops`` (0191). La RLS de ``conversations`` no cambia. Aquí:

- **la herramienta** ``reception.handoff`` en ``tool_catalog``, en la misma
  entrega que la introduce (``.claude/rules/tenant-isolation.md``): sin registro no
  existe para el runtime y ``AgentConfigService`` no deja ponerla en ninguna lista
  blanca. Su esquema sale de ``alembic/data/0200_reception_tool.json``, congelado
  desde el registro (``model_json_schema()``). Escribe en la conversación del
  propio negocio: ni destructiva ni con consentimiento;
- **un índice parcial** para la FK de ``handled_by_agent_id`` (archivar o borrar
  un agente no recorre la tabla) y la Bandeja por agente;
- **un CHECK** de que los saltos no son negativos (el corte de bucles cuenta hacia
  arriba desde cero).

Revision ID: 0200_reception
Revises: 0199_agent_suggestions
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0200_reception"
down_revision: str | Sequence[str] | None = "0199_agent_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "0200_reception_tool.json"
TOOL = "reception.handoff"


def upgrade() -> None:
    bind = op.get_bind()
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict[str, Any]] = json.load(fh)
    for tool_name, spec in catalog.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO tool_catalog (
                    name, description, mcp_server,
                    input_schema, output_schema,
                    side_effects, capability_tags, cost_estimate,
                    connector_id, read_only, destructive, requires_consent,
                    default_mode
                ) VALUES (
                    :name, :description, 'reception-server',
                    CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                    CAST(:side_effects AS varchar[]),
                    CAST('{reception,handoff}' AS varchar[]),
                    CAST('{}' AS jsonb),
                    NULL, :read_only, false, false,
                    'always'
                )
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    input_schema = EXCLUDED.input_schema,
                    output_schema = EXCLUDED.output_schema
                """
            ),
            {
                "name": tool_name,
                "description": spec["description"],
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
                "side_effects": list(spec["side_effects"]),
                "read_only": not spec["side_effects"],
            },
        )

    op.execute(
        "CREATE INDEX ix_conversations_handled_by_agent "
        "ON conversations (tenant_id, handled_by_agent_id) "
        "WHERE handled_by_agent_id IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE conversations ADD CONSTRAINT ck_conversations_reception_hops "
        "CHECK (reception_hops >= 0)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_reception_hops"
    )
    op.execute("DROP INDEX IF EXISTS ix_conversations_handled_by_agent")
    op.get_bind().execute(sa.text("DELETE FROM tool_catalog WHERE name = :name"), {"name": TOOL})
