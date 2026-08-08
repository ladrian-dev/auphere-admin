"""tenants.tier — performance isolation tier (WP-10, plataforma v2 Fase 1).

``priority`` tenants publish to their own inbound stream consumed by a
dedicated runner pool, so a burst on ``standard`` cannot move their p95.
Default ``standard`` for every existing and new tenant; flipping a tenant
to ``priority`` is an operator action in the admin, not a deploy.

Note: the technical plan numbered this 0060; ``0060_woo_checkout_link``
landed on main after the plan's baseline, so the chain shifts by one.

Revision ID: 0061_tenant_tier
Revises: 0060_woo_checkout_link
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0061_tenant_tier"
down_revision: str | Sequence[str] | None = "0060_woo_checkout_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tenant_tier = sa.Enum("standard", "priority", name="tenant_tier")
    tenant_tier.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "tenants",
        sa.Column(
            "tier",
            tenant_tier,
            nullable=False,
            server_default="standard",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "tier")
    sa.Enum(name="tenant_tier").drop(op.get_bind(), checkfirst=True)
