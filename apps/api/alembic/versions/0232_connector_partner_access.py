"""Qué partners pueden usar cada conector — spec 060 (T001, requisitos 1.1, 1.2, 2.2 y 3.2).

- ``connector_access_defaults``: el valor por defecto de un conector para los
  partners. Sin fila significa habilitado, así que al desplegar nada cambia (1.1).
- ``connector_partner_access``: la decisión propia de un partner sobre un
  conector. Las dos vistas del panel escriben aquí (3.3).

Las dos son datos de plataforma, sin ``tenant_id`` y sin RLS, con los permisos de
``platform_settings`` (0231). El conector va por su slug, no por
``connectors.id``: los de Composio no tienen fila hasta el primer consentimiento
(research D1 y D3).

También siembra las frases de ``console_audit_vocabulary`` de los cambios y del
consentimiento que llega cuando el partner ya no puede usar el conector.

Revision ID: 0232_connector_partner_access
Revises: 0231_platform_settings
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0232_connector_partner_access"
down_revision: str | Sequence[str] | None = "0231_platform_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "connector_access.default_changed",
        "admin",
        "info",
        "Auphere cambió para qué partners está disponible un conector por defecto.",
        "Auphere changed which partners a connector is available to by default.",
    ),
    (
        "connector.unavailable_for_partner",
        "agents",
        "info",
        "{connector} no quedó conectado en {client}: su partner ya no puede usarlo.",
        "{connector} was not connected for {client}: its partner can no longer use it.",
    ),
    (
        "connector_access.partner_changed",
        "admin",
        "info",
        "Auphere cambió si un conector está disponible para un partner.",
        "Auphere changed whether a connector is available to a partner.",
    ),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE connector_access_defaults (
            connector_slug text PRIMARY KEY,
            enabled boolean NOT NULL,
            reason text NOT NULL,
            updated_by text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_connector_access_defaults_slug_lower
                CHECK (connector_slug = lower(connector_slug))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE connector_partner_access (
            connector_slug text NOT NULL,
            partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
            enabled boolean NOT NULL,
            reason text NOT NULL,
            set_by text NOT NULL,
            set_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (connector_slug, partner_id),
            CONSTRAINT ck_connector_partner_access_slug_lower
                CHECK (connector_slug = lower(connector_slug))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_connector_partner_access_partner_id "
        "ON connector_partner_access (partner_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON connector_access_defaults, connector_partner_access TO nexus_app"
    )

    bind = op.get_bind()
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
    op.execute("DROP TABLE IF EXISTS connector_partner_access")
    op.execute("DROP TABLE IF EXISTS connector_access_defaults")
