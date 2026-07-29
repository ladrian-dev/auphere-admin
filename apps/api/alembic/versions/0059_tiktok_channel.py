"""TikTok as a channel type (Business Messaging API)

Revision ID: 0059_tiktok_channel
Revises: 0058_cobranza_send_reminders
Create Date: 2026-07-28

Second real channel after ``whatsapp_meta``. TikTok Business Messaging lets
an authorised Business Account exchange direct messages with TikTok users;
the tenant authorises the single Auphere developer app (Tech-Provider shape,
same as Meta) and the platform stores the resulting OAuth tokens.

Schema impact is deliberately minimal — the channel abstraction was built
multi-provider from day one:

- ``channels`` already carries ``provider`` (``"tiktok"``) +
  ``provider_identifier`` (the TikTok ``business_id``) and its
  ``uq_channels_type_provider_id`` constraint keeps the pair unique.
- ``tenant_credentials`` already stores an opaque Fernet-encrypted payload
  keyed by ``integration`` — TikTok uses ``integration="tiktok_bm"``.
- ``customers.identifier`` is ``String(255)``, wide enough for a TikTok
  ``open_id``.

So the only DDL is the new enum value. PG ≥ 12 allows ALTER TYPE ... ADD
VALUE inside the migration transaction as long as the new value isn't used
in the same transaction (it isn't — first use is at runtime), which is the
same pattern 0047 used for ``tenant_status``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0059_tiktok_channel"
down_revision: str | Sequence[str] | None = "0058_cobranza_send_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'tiktok'")


def downgrade() -> None:
    # 'tiktok' stays in channel_type: PG can't drop enum values and
    # recreating the type would rewrite every channels row for no gain.
    pass
