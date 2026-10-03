"""Las dos herramientas del catálogo de Meta en ``tool_catalog`` (spec 022).

``catalog.search_products`` y ``catalog.get_product``: nativas, de solo
lectura, sin efectos, siempre disponibles — pero **solo aparecen** en
Capacidades cuando el número tiene un catálogo enlazado (``requires:
channel_catalog`` en ``capability_names``). Sin catálogo, la pantalla no las
enseña; con él, nacen encendidas en las plantillas de venta.

Revision ID: 0135_catalog_tools
Revises: 0134_audit_vocab_catalog
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text

from alembic import op

revision: str = "0135_catalog_tools"
down_revision: str | Sequence[str] | None = "0134_audit_vocab_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "0135_catalog_tools.json"


def upgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)
    bind = op.get_bind()
    for tool_name, spec in catalog.items():
        bind.execute(
            text(
                """
                INSERT INTO tool_catalog (
                    name, description, mcp_server,
                    input_schema, output_schema,
                    side_effects, capability_tags, cost_estimate,
                    connector_id, read_only, destructive, requires_consent,
                    default_mode
                ) VALUES (
                    :name, :description, 'meta-catalog-server',
                    CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                    CAST('{}' AS varchar[]),
                    CAST('{catalog,read}' AS varchar[]),
                    CAST('{}' AS jsonb),
                    NULL, true, false, false,
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
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "DELETE FROM tool_catalog WHERE name IN ('catalog.search_products', 'catalog.get_product')"
        )
    )
