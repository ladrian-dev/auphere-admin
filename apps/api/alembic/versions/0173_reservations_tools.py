"""Reservas — spec 043: las herramientas ``reservas.*`` en el catálogo y el
vocabulario de auditoría del cambio de modo.

Una herramienta nueva se registra en ``tool_catalog`` en la misma entrega que la
introduce (``.claude/rules/tenant-isolation.md``): sin registro no existe para el
runtime, y ``AgentConfigService`` no deja ponerla en la lista blanca de ningún
agente. Los esquemas salen de ``alembic/data/0173_reservations_tools.json``,
congelado desde el registro (``model_json_schema()`` de cada herramienta).

``read_only`` marca las de consulta, que un administrador de solo lectura
(spec 024) puede usar. Ninguna es destructiva ni pide consentimiento: escriben
en la agenda del propio negocio.

Revision ID: 0173_reservations_tools
Revises: 0172_reservations_schema
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "0173_reservations_tools"
down_revision: str | Sequence[str] | None = "0172_reservations_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "0173_reservations_tools.json"

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "reservations.mode_changed",
        "clients",
        "warning",
        "Auphere cambió el modo de Reservas de {client}.",
        "Auphere changed {client}'s Reservations mode.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)
    for tool_name, spec in catalog.items():
        read_only = not spec["side_effects"]
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
                    :name, :description, 'reservas-server',
                    CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                    CAST(:side_effects AS varchar[]),
                    CAST('{booking,reservas}' AS varchar[]),
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
                "read_only": read_only,
            },
        )

    for action, category, severity, summary_es, summary_en in VOCABULARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT
                    CAST(:action AS VARCHAR(80)),
                    CAST(:category AS VARCHAR(40)),
                    CAST(:severity AS VARCHAR(10)),
                    CAST(:summary_es AS TEXT),
                    CAST(:summary_en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary
                    WHERE action = CAST(:action AS VARCHAR(80))
                )
                """
            ),
            {
                "action": action,
                "category": category,
                "severity": severity,
                "summary_es": summary_es,
                "summary_en": summary_en,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = 'reservations.mode_changed'")
    )
    bind.execute(sa.text("DELETE FROM tool_catalog WHERE name LIKE 'reservas.%'"))
