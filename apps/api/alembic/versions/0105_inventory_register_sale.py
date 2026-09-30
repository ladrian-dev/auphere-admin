"""seed tool_catalog with inventory.register_sale (demo simulated sale)

Revision ID: 0105_inventory_register_sale
Revises: 0104_operator_auth_if_missing
Create Date: 2026-09-02

``inventory.register_sale`` es la ÚNICA tool de inventario con efecto de
escritura: descuenta stock en ``local_catalog_products`` para SIMULAR una
venta en la demo de farmacia. No es una venta real en un POS — el API de
Amigable Venta es de solo lectura — y la tool se rechaza a sí misma si el
backend activo del tenant es Amigable Venta.

Diferencias con las cuatro tools de lectura (migración 0102), que sí cuelgan
del connector ``amigable_venta``:

- ``connector_id = NULL``: opera sobre la tabla propia de Nexus, no sobre un
  connector. No hay nada a lo que dar consent, así que ``requires_consent = false``.
- ``destructive = true`` / ``read_only = false`` / ``side_effects = {mutates_db}``:
  el registry la salta en ``dry_run`` (QA Playground) y la marca destructiva.
- ``default_mode = 'always'``: el runtime del worker NO aplica
  ``tool_catalog.default_mode`` (solo overrides explícitos por tenant vía
  ``tenant_connector_tool_overrides`` — ver ``load_gated_tool_names``), así que
  este valor solo gobierna la UI de autoría de la consola. Se deja en
  ``always`` porque en la demo la venta SÍ se ejecuta al estar en el whitelist
  del agent_config; ponerla en ``blocked`` mentiría en el panel sin cambiar el
  runtime. El blast radius es nulo: ninguna otra plantilla la incluye.

Schema en ``alembic/data/0105_inventory_register_sale.json``, generado desde
los modelos Pydantic de la tool. Idempotente: ON CONFLICT (name) DO UPDATE.
El runtime la registra vía ``nexus_mcp.registry.build_default_registry``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0105_inventory_register_sale"
down_revision: str | Sequence[str] | None = "0104_operator_auth_if_missing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0105_inventory_register_sale.json",
)

_CAPABILITY_TAGS_BY_TOOL: dict[str, list[str]] = {
    "inventory.register_sale": ["inventory", "stock", "write"],
}


def upgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)

    bind = op.get_bind()

    for tool_name, spec in catalog.items():
        side_effects = spec["side_effects"]
        read_only = bool(spec["read_only"])
        destructive = bool(spec["destructive"])
        capability_tags = _CAPABILITY_TAGS_BY_TOOL.get(tool_name, ["inventory", "write"])

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
                    :name, :description, :mcp_server,
                    CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                    CAST(:side_effects AS varchar[]),
                    CAST(:capability_tags AS varchar[]),
                    CAST('{}' AS jsonb),
                    NULL, :read_only, :destructive, false,
                    :default_mode
                )
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    input_schema = EXCLUDED.input_schema,
                    output_schema = EXCLUDED.output_schema,
                    side_effects = EXCLUDED.side_effects,
                    capability_tags = EXCLUDED.capability_tags,
                    connector_id = EXCLUDED.connector_id,
                    read_only = EXCLUDED.read_only,
                    destructive = EXCLUDED.destructive,
                    requires_consent = EXCLUDED.requires_consent,
                    default_mode = EXCLUDED.default_mode
                """
            ),
            {
                "name": tool_name,
                "description": spec["description"],
                "mcp_server": "inventory-server",
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
                "side_effects": list(side_effects),
                "capability_tags": list(capability_tags),
                "read_only": read_only,
                "destructive": destructive,
                # Local-catalogue write — no connector, nothing to consent to.
                "default_mode": "always",
            },
        )


def downgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog = json.load(fh)
    names = list(catalog.keys())
    op.execute(
        "DELETE FROM tool_catalog WHERE name IN (" + ", ".join(f"'{n}'" for n in names) + ")"
    )
