"""channel_signup_links — spec 040

A link the operator or the partner copies and sends to the business owner, so
WhatsApp's Embedded Signup (coexistence or Cloud API) runs on the owner's own
phone or computer — where they are already logged in to Meta — instead of on
the partner's.

Only the SHA-256 of the token is stored (like ``signup_requests``): a dump of
the table cannot connect anything. A link is single use (``consumed_at``),
expires (``expires_at``) and can be revoked.

**No RLS, on purpose.** The public page knows nothing but the token, so the
row has to be found *before* any tenant scope exists — the same reason
``signup_requests`` has none. Once found, the signup itself runs under the
link's tenant GUC. Every reader filters by ``token_hash`` or by an explicit
``tenant_id``.

Revision ID: 0160_channel_signup_links
Revises: 0159_partner_console_modules
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0160_channel_signup_links"
down_revision: str | Sequence[str] | None = "0159_partner_console_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_signup_links",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False, server_default="whatsapp"),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_id", UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("channel IN ('whatsapp')", name="ck_channel_signup_links_channel"),
        sa.CheckConstraint(
            "mode IN ('coexistence', 'cloud_api')", name="ck_channel_signup_links_mode"
        ),
    )
    op.create_index(
        "uq_channel_signup_links_token_hash", "channel_signup_links", ["token_hash"], unique=True
    )
    op.create_index("ix_channel_signup_links_tenant", "channel_signup_links", ["tenant_id"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON channel_signup_links TO nexus_app")


def downgrade() -> None:
    op.drop_table("channel_signup_links")
