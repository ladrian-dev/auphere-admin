"""Spec 085: the owner link connects Instagram and Messenger too.

``channel_signup_links`` (spec 040, 0160; agent and one pending per agent in
0191) already had ``channel``; its CHECK only allowed ``whatsapp``.

- ``channel`` admits ``instagram`` and ``messenger``.
- ``mode`` admits ``meta_login``: «the owner signs in to Meta». An Instagram
  or Messenger link carries no mode the partner picks — the owner chooses how
  to sign in on their page — so it always stores this one.
- ``ck_channel_signup_links_mode_per_channel`` ties each channel to its modes:
  WhatsApp to its three, Instagram and Messenger to ``meta_login`` alone.
- ``uq_channel_signup_links_one_pending`` becomes one pending link per agent
  **and channel**: an agent may wait for its WhatsApp and its Instagram at once.

The downgrade drops the Instagram and Messenger links first (0191's CHECKs
would refuse them) and restores 0191's constraints.

Revision ID: 0244_owner_links_meta_social
Revises: 0243_template_edit_vocabulary
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0244_owner_links_meta_social"
down_revision: str | Sequence[str] | None = "0243_template_edit_vocabulary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PENDING = "WHERE consumed_at IS NULL AND revoked_at IS NULL AND agent_id IS NOT NULL"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE channel_signup_links
            DROP CONSTRAINT ck_channel_signup_links_channel,
            ADD CONSTRAINT ck_channel_signup_links_channel CHECK (
                channel IN ('whatsapp', 'instagram', 'messenger')
            ),
            DROP CONSTRAINT ck_channel_signup_links_mode,
            ADD CONSTRAINT ck_channel_signup_links_mode CHECK (
                mode IN ('coexistence', 'cloud_api', 'whatsapp_login', 'meta_login')
            ),
            ADD CONSTRAINT ck_channel_signup_links_mode_per_channel CHECK (
                (channel = 'whatsapp' AND mode IN ('coexistence', 'cloud_api', 'whatsapp_login'))
                OR (channel IN ('instagram', 'messenger') AND mode = 'meta_login')
            )
        """
    )
    op.execute("DROP INDEX uq_channel_signup_links_one_pending")
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_signup_links_one_pending "
        f"ON channel_signup_links (tenant_id, agent_id, channel) {_PENDING}"
    )


def downgrade() -> None:
    op.execute("DELETE FROM channel_signup_links WHERE channel <> 'whatsapp'")
    op.execute("DROP INDEX IF EXISTS uq_channel_signup_links_one_pending")
    op.execute(
        "CREATE UNIQUE INDEX uq_channel_signup_links_one_pending "
        f"ON channel_signup_links (tenant_id, agent_id) {_PENDING}"
    )
    op.execute(
        """
        ALTER TABLE channel_signup_links
            DROP CONSTRAINT IF EXISTS ck_channel_signup_links_mode_per_channel,
            DROP CONSTRAINT ck_channel_signup_links_mode,
            ADD CONSTRAINT ck_channel_signup_links_mode CHECK (
                mode IN ('coexistence', 'cloud_api', 'whatsapp_login')
            ),
            DROP CONSTRAINT ck_channel_signup_links_channel,
            ADD CONSTRAINT ck_channel_signup_links_channel CHECK (channel IN ('whatsapp'))
        """
    )
