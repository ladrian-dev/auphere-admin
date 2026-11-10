"""Autorizar una vez por cliente, activar por agente — spec 047, T127 (requisitos
35.1, 36.2 y 36.5; ``data-model.md`` §5, research D13).

- ``agent_connector_activations``: la activación de una conexión del cliente
  (``tenant_connectors``) para un agente, con su permiso (``read``,
  ``ask_before_write``, ``read_write``) y sus ajustes. Una por agente y conexión.
- ``tenant_connectors.last_checked_at``: la hora de la última comprobación de salud.
- ``connectors.settings_schema``: los ajustes que declara cada integración del
  catálogo (JSON Schema), para validarlos.
- **Datos**: cada agente vivo que hoy tiene en su lista herramientas de una conexión
  no desconectada recibe su activación con «Leer y escribir» (lo que ya hacía), y
  los ajustes repartidos que tiene esa conexión (la URL de la tienda de
  WooCommerce, el negocio de Amigable) y los recordatorios del agente
  (``policies.reminders``) pasan a los ajustes de la activación.

Revision ID: 0194_connector_activations
Revises: 0193_knowledge_layers
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0194_connector_activations"
down_revision: str | Sequence[str] | None = "0193_knowledge_layers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
PERMISSIONS = ("read", "ask_before_write", "read_write")

STATEMENTS = (
    "ALTER TABLE connectors ADD COLUMN settings_schema jsonb",
    """
    ALTER TABLE tenant_connectors
        ADD COLUMN last_checked_at timestamptz,
        ADD CONSTRAINT uq_tenant_connectors_tenant_id UNIQUE (tenant_id, id)
    """,
    f"""
    CREATE TABLE agent_connector_activations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid NOT NULL,
        connector_id uuid NOT NULL,
        permission varchar(20) NOT NULL,
        settings jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        created_by varchar(160),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_connector_activations_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_agent_connector_activations_one UNIQUE (tenant_id, agent_id, connector_id),
        CONSTRAINT ck_agent_connector_activations_permission CHECK (
            permission IN ({", ".join(f"'{p}'" for p in PERMISSIONS)})
        ),
        CONSTRAINT fk_agent_connector_activations_agent FOREIGN KEY (tenant_id, agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_agent_connector_activations_connection FOREIGN KEY (tenant_id, connector_id)
            REFERENCES tenant_connectors (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_agent_connector_activations_agent "
    "ON agent_connector_activations (tenant_id, agent_id)",
)

#: Los ajustes de una conexión que pasan a la activación (no secretos).
_ENDPOINT_SETTINGS = ("store_url", "business_uuid", "base_url")

_USES = sa.text(
    """
    SELECT tc.tenant_id, tc.id AS connection_id, tc.credentials_ref, a.id AS agent_id,
           (SELECT v.policies FROM agent_configs v
             WHERE v.tenant_id = a.tenant_id AND v.agent_id = a.id
             ORDER BY (v.status = 'active') DESC, v.version DESC LIMIT 1) AS policies,
           c.slug
      FROM tenant_connectors tc
      JOIN connectors c ON c.id = tc.connector_id
      JOIN agents a ON a.tenant_id = tc.tenant_id AND a.status = 'active'
     WHERE tc.status <> 'disconnected'
       AND EXISTS (
           SELECT 1 FROM agent_configs v
             JOIN tool_catalog t ON t.connector_id = tc.connector_id
            WHERE v.tenant_id = a.tenant_id AND v.agent_id = a.id
              AND v.status IN ('active', 'staged')
              AND v.tools ? t.name
       )
    """
)


def settings_for(slug: str, credentials_ref: Any, policies: Any) -> dict[str, Any]:
    """Los ajustes que hoy están repartidos y pasan a la activación."""
    out: dict[str, Any] = {}
    meta = (credentials_ref or {}).get("endpoint_meta") or {}
    if isinstance(meta, dict):
        out.update({k: meta[k] for k in _ENDPOINT_SETTINGS if meta.get(k)})
    reminders = (policies or {}).get("reminders")
    if slug.startswith("amigable") and isinstance(reminders, dict):
        out["reminders"] = reminders
    return out


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    op.execute("ALTER TABLE agent_connector_activations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_connector_activations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agent_connector_activations_tenant_isolation ON agent_connector_activations "
        f"USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON agent_connector_activations TO nexus_app")
    bind = op.get_bind()
    # La migración corre como dueña de las tablas: la RLS no la filtra.
    for row in bind.execute(_USES).mappings().all():
        bind.execute(
            sa.text(
                "INSERT INTO agent_connector_activations "
                "(tenant_id, agent_id, connector_id, permission, settings, created_by) "
                "VALUES (:t, :a, :c, 'read_write', CAST(:s AS jsonb), 'migration:0194') "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "t": row["tenant_id"],
                "a": row["agent_id"],
                "c": row["connection_id"],
                "s": json.dumps(settings_for(row["slug"], row["credentials_ref"], row["policies"])),
            },
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_connector_activations CASCADE")
    op.execute(
        "ALTER TABLE tenant_connectors DROP CONSTRAINT IF EXISTS uq_tenant_connectors_tenant_id, "
        "DROP COLUMN IF EXISTS last_checked_at"
    )
    op.execute("ALTER TABLE connectors DROP COLUMN IF EXISTS settings_schema")
