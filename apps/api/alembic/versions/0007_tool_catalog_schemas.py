"""sync tool_catalog input/output schemas with the real Pydantic models

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-08

The seed in 0003 inserted ``tool_catalog`` rows with empty ``input_schema``
and ``output_schema`` so Block C could function with deterministic stubs.
Block D ships real Pydantic models and the LLM gets these schemas as the
``tools=`` parameter for function-calling — they must be real.

Strategy: load the JSON snapshot generated from
``nexus_mcp.MCPRegistry.get_tool_definitions`` at the time this migration
was authored. The snapshot lives next to the migration in
``apps/api/alembic/data/0007_tool_schemas.json``. When the Pydantic models
evolve, write a new migration with a new snapshot — never edit this one.

Idempotent: every UPDATE is keyed on the tool's ``name``, so running this
migration twice is a no-op.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0007_tool_schemas.json",
)


def upgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog = json.load(fh)

    for tool_name, schemas in catalog.items():
        op.execute(
            """
            UPDATE tool_catalog
               SET input_schema  = :input_schema::jsonb,
                   output_schema = :output_schema::jsonb,
                   updated_at    = now()
             WHERE name = :name
            """.replace(":input_schema", _jsonb_literal(schemas["input_schema"]))
            .replace(":output_schema", _jsonb_literal(schemas["output_schema"]))
            .replace(":name", _quote(tool_name))
        )


def downgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog = json.load(fh)
    for tool_name in catalog.keys():
        op.execute(
            f"""
            UPDATE tool_catalog
               SET input_schema = '{{}}'::jsonb,
                   output_schema = '{{}}'::jsonb,
                   updated_at = now()
             WHERE name = {_quote(tool_name)}
            """
        )


def _jsonb_literal(obj: dict) -> str:
    """Embed a JSON object as a SQL string literal — single-quote escape."""
    return "'" + json.dumps(obj).replace("'", "''") + "'"


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"
