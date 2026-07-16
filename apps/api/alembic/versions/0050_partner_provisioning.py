"""Partner auto-provisioning blueprint (ADR-028 Fase 2b)

Revision ID: 0050_partner_provisioning
Revises: 0051_drop_tenant_widget_configs
Create Date: 2026-07-09

Adds the per-partner agent blueprint so ``POST /v1/partners/clients`` can
leave a working agent behind, not just a bare tenant:

- ``partners.default_seed_template`` — seed template ref (e.g.
  ``cobranza_v1``) rendered + promoted as agent_config v1 for every
  client the partner provisions. NULL = no auto-agent (assisted
  onboarding, operator seeds from the admin panel).
- ``partners.default_connector_slug`` — ``api_key`` connector installed
  with the credentials the partner sends at provision time (e.g.
  ``amigable_cobro``). NULL = no auto-connector.
- ``partners.auto_activate`` — flip the tenant PROVISIONING → ACTIVE when
  its WhatsApp signup completes AND an active agent_config exists. False
  = the operator reviews and activates by hand.

No new grants: the provision surface runs the tenant-scoped writes
(agent_configs, tenant_credentials, tenant_connectors) under the same
role and RLS scope the admin endpoints already use.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0050_partner_provisioning"
down_revision: str | Sequence[str] | None = "0051_drop_tenant_widget_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "partners",
        sa.Column("default_seed_template", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "partners",
        sa.Column("default_connector_slug", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "partners",
        sa.Column(
            "auto_activate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("partners", "auto_activate")
    op.drop_column("partners", "default_connector_slug")
    op.drop_column("partners", "default_seed_template")
