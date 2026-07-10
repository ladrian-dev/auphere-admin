"""drop tenant_widget_configs (web widget removed)

Revision ID: 0051_drop_tenant_widget_configs
Revises: 0050_tenant_widget_config
Create Date: 2026-07-11

The public web chat widget was rolled back — Barber Supply's agent is
WhatsApp-only. Migration 0050 stays in history (prod was already stamped
at it) and this migration drops the now-unused table. The rest of the
widget code was reverted; nothing references this table anymore.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision: str = "0051_drop_tenant_widget_configs"
down_revision: str | Sequence[str] | None = "0050_tenant_widget_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE ALL ON tenant_widget_configs FROM nexus_app")
    op.drop_table("tenant_widget_configs")


def downgrade() -> None:
    # Recreate the table shape from 0050 so downgrade is reversible.
    op.create_table(
        "tenant_widget_configs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("public_key", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "allowed_origins",
            ARRAY(sa.String(255)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column("greeting", sa.Text, nullable=True),
        sa.Column("appearance", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("GRANT SELECT ON tenant_widget_configs TO nexus_app")
