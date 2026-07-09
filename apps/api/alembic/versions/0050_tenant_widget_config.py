"""web chat widget — tenant_widget_configs

Revision ID: 0050_tenant_widget_config
Revises: 0049_message_template_payload
Create Date: 2026-07-09

Public web chat widget channel (native chat bubble on a tenant's own
website). This adds the ONE new table the feature needs — everything else
(the agent graph, the ``nexus:inbound`` stream, ``ChannelType.WEB``, the
message/conversation model) already exists and is reused unchanged.

``tenant_widget_configs`` is a PLATFORM table (NOT tenant-scoped, no RLS)
— same trust model as ``partners``/``partner_tenants``: the
``public_key`` → ``tenant_id`` lookup runs at ``POST /v1/widget/session``
BEFORE any tenant scope exists. The resolved tenant is then baked into the
signed widget JWT and read exclusively from those claims downstream.

Grants ``nexus_app`` (the RLS-enforced role scoped requests switch to)
SELECT so the per-request fail-closed re-check (config still enabled?) can
run inside the tenant-scoped transaction. No write access — the config is
managed from the admin/seed surface which runs as the table owner.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision: str = "0050_tenant_widget_config"
down_revision: str | Sequence[str] | None = "0049_message_template_payload"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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

    # nexus_app re-checks ``enabled`` inside the tenant-scoped transaction
    # (fail-closed on a disabled widget). Read-only: config writes go
    # through the admin/seed surface running as the table owner.
    op.execute("GRANT SELECT ON tenant_widget_configs TO nexus_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON tenant_widget_configs FROM nexus_app")
    op.drop_table("tenant_widget_configs")
