"""seed las 6 tools agendapro.* en tool_catalog con status='internal'

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-09

Bloque E entrega 6 tools internas que el booking-server invoca cuando el
tenant tiene la integration AgendaPro activa. Las marca con
``status='internal'`` (enum value agregado en migración 0008).

``status='internal'`` significa, por contrato:
- NO se incluyen en ``MCPRegistry.get_tool_definitions(whitelist)`` que
  alimenta a LiteLLM con las definitions function-calling. El LLM NUNCA
  las ve.
- NO se aceptan en el body del PUT /agent-config (Bloque G las filtra).
- Solo invocables vía ``MCPRegistry.dispatch_internal`` con
  ``caller_token`` válido.

El snapshot de schemas vive en ``alembic/data/0009_agendapro_internal_tools.json``.
Cuando los Pydantic models cambien, se escribe una nueva migración con
nuevo snapshot — no se edita esta.

Idempotente: ON CONFLICT (name) DO NOTHING.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0009_agendapro_internal_tools.json",
)


def upgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        tools = json.load(fh)

    for tool in tools:
        op.execute(
            f"""
            INSERT INTO tool_catalog
                (name, description, mcp_server, side_effects, capability_tags,
                 input_schema, output_schema, cost_estimate, status)
            VALUES (
                {_q(tool["name"])},
                {_q(tool["description"])},
                {_q(tool["mcp_server"])},
                ARRAY[{",".join(_q(s) for s in tool["side_effects"])}]::varchar(40)[],
                ARRAY[{",".join(_q(t) for t in tool["capability_tags"])}]::varchar(40)[],
                {_jsonb(tool["input_schema"])},
                {_jsonb(tool["output_schema"])},
                '{{}}'::jsonb,
                'internal'
            )
            ON CONFLICT (name) DO UPDATE SET
                description = EXCLUDED.description,
                input_schema = EXCLUDED.input_schema,
                output_schema = EXCLUDED.output_schema,
                status = EXCLUDED.status,
                updated_at = now()
            """
        )


def downgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        tools = json.load(fh)
    names = ",".join(_q(t["name"]) for t in tools)
    op.execute(f"DELETE FROM tool_catalog WHERE name IN ({names})")


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _jsonb(obj: dict) -> str:
    return "'" + json.dumps(obj).replace("'", "''") + "'::jsonb"
