"""Conector de Quédate y vínculos de clientes finales con sistemas externos — spec 061
(enmienda del 2026-11-16, sobre la API del agente de Quédate).

- ``customer_connector_accounts``: el vínculo de un cliente final con su anfitrión
  en Quédate. **Sin credencial**: las llamadas van con la clave del negocio (ADR
  ``decisions/2026-11-13-adr-credenciales-de-terceros-por-cliente-final``,
  enmendado). Lleva RLS forzada por tenant, FK a ``tenants`` y FK compuesta a
  ``customers``, ambas con borrado en cascada, y es único por tenant, cliente final
  y conector, y por tenant, conector y cuenta externa (una cuenta, una persona).
- El conector ``quedate`` (``ON CONFLICT DO NOTHING``: la semilla lo reaplica en
  cada despliegue) con ``auto_enable_on_connect=false``, y sus 27 filas de
  ``tool_catalog`` desde ``alembic/data/0233_quedate_tools.json``. Esa
  instantánea sale de los modelos Pydantic de las herramientas; si cambia, se
  escribe otra migración.
- ``connector_access_defaults('quedate', false)``: nace deshabilitado para los
  partners (spec 060). Auphere lo habilita para cada partner desde el panel, en
  cada entorno.
- Las frases del vocabulario de auditoría: el vínculo, su fallo y una escritura en
  Quédate sin respuesta.

Revision ID: 0233_quedate_connector
Revises: 0232_connector_partner_access
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0233_quedate_connector"
down_revision: str | Sequence[str] | None = "0232_connector_partner_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "0233_quedate_tools.json"
)

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "connector.customer_account_linked",
        "agents",
        "info",
        "Un agente vinculó a una persona con su cuenta de anfitriona en Quédate.",
        "An agent linked a person to their Quédate host account.",
    ),
    (
        "connector.customer_account_link_failed",
        "agents",
        "warning",
        "Puede que Quédate creara la cuenta de una persona, pero no quedó vinculada en Auphere.",
        "Quédate may have created a person's account, but it was not linked in Auphere.",
    ),
    (
        "connector.external_write_unconfirmed",
        "agents",
        "warning",
        "Un agente escribió en un sistema externo y no hubo respuesta: puede que se hiciera.",
        "An agent wrote to an external system and got no answer: it may have gone through.",
    ),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE customer_connector_accounts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            customer_id uuid NOT NULL,
            connector_slug text NOT NULL,
            external_user_id text NOT NULL,
            state jsonb NOT NULL DEFAULT '{}'::jsonb,
            needs_review boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_customer_connector_accounts
                UNIQUE (tenant_id, customer_id, connector_slug),
            CONSTRAINT uq_customer_connector_accounts_external
                UNIQUE (tenant_id, connector_slug, external_user_id),
            CONSTRAINT fk_customer_connector_accounts_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_customer_connector_accounts_customer
                FOREIGN KEY (tenant_id, customer_id)
                REFERENCES customers (tenant_id, id) ON DELETE CASCADE,
            CONSTRAINT ck_customer_connector_accounts_slug_lower
                CHECK (connector_slug = lower(connector_slug))
        )
        """
    )
    op.create_index(
        "ix_customer_connector_accounts_tenant_id", "customer_connector_accounts", ["tenant_id"]
    )
    op.execute("ALTER TABLE customer_connector_accounts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE customer_connector_accounts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY customer_connector_accounts_tenant_isolation "
        f"ON customer_connector_accounts USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON customer_connector_accounts TO nexus_app")

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO connectors (
                slug, display_name, vendor, category, capabilities,
                auth_kind, mcp_server_ref, provider_meta,
                auto_enable_on_connect, auto_enable_destructive,
                consent_link_template_name, status
            ) VALUES (
                'quedate', 'Quédate', 'Amacrux', 'lodging',
                CAST(:capabilities AS varchar[]),
                'api_key', 'internal:quedate', CAST('{}' AS jsonb),
                false, false, NULL, 'available'
            )
            ON CONFLICT (slug) DO NOTHING
            """
        ),
        {"capabilities": ["read", "write"]},
    )
    connector_id = bind.execute(
        sa.text("SELECT id FROM connectors WHERE slug = 'quedate'")
    ).scalar()
    if connector_id is None:
        raise RuntimeError("quedate connector row missing after insert")

    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)
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
                    :name, :description, 'quedate-server',
                    CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                    CAST(:side_effects AS varchar[]),
                    CAST(:capability_tags AS varchar[]),
                    CAST('{}' AS jsonb),
                    :connector_id, :read_only, false, true, 'always'
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
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
                "side_effects": list(spec["side_effects"]),
                "capability_tags": ["quedate", "read" if spec["read_only"] else "write"],
                "connector_id": connector_id,
                "read_only": bool(spec["read_only"]),
            },
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO connector_access_defaults (connector_slug, enabled, reason, updated_by)
            VALUES ('quedate', false, 'Conector de Amacrux (spec 061)', 'migration:0233')
            ON CONFLICT (connector_slug) DO NOTHING
            """
        )
    )

    for action, category, severity, es, en in VOCABULARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT CAST(:a AS VARCHAR(80)), CAST(:c AS VARCHAR(40)),
                       CAST(:s AS VARCHAR(10)), CAST(:es AS TEXT), CAST(:en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary WHERE action = CAST(:a AS VARCHAR(80))
                )
                """
            ),
            {"a": action, "c": category, "s": severity, "es": es, "en": en},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for action, *_ in VOCABULARY:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": action}
        )
    bind.execute(sa.text("DELETE FROM connector_access_defaults WHERE connector_slug = 'quedate'"))
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        names = list(json.load(fh))
    bind.execute(sa.text("DELETE FROM tool_catalog WHERE name = ANY(:n)"), {"n": names})
    op.execute("DROP TABLE customer_connector_accounts")
