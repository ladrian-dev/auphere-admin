"""Remove YCloud — Meta Cloud API becomes the only WhatsApp provider.

Schema:
- ``auphere_owner_channels.access_token_encrypted`` (BYTEA, nullable) —
  Fernet-encrypted Meta access token (system user / BISUAT) used to send
  from the Auphere backchannel number.
- ``owner_consultations.ycloud_message_id`` → ``provider_message_id``
  (rename; provider-agnostic wamid).
- ``auphere_owner_channels`` provider CHECK tightened to ``('meta')``.

Data:
- Delete ``auphere_owner_channels`` rows with ``provider='ycloud'``
  (``owner_phone_index.auphere_channel_id`` is ON DELETE SET NULL, so
  pinned owners fall back to the provider default).
- Delete ``tenant_connectors`` rows pointing at the ``whatsapp_ycloud``
  connector, then the connector row itself (FKs are RESTRICT).
- Mark ``channels`` rows with ``provider='ycloud'`` as DISCONNECTED.
  Conversation history is preserved; the demo tenants that used YCloud
  are deleted by the operator from the panel (full cascade lives in the
  tenant-delete endpoint, not here).

Revision ID: 0044_remove_ycloud_meta_only
Revises: 0043_owner_phone_index_confirmed_at
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_remove_ycloud_meta_only"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── schema ──────────────────────────────────────────────────────
    op.add_column(
        "auphere_owner_channels",
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.alter_column(
        "owner_consultations",
        "ycloud_message_id",
        new_column_name="provider_message_id",
    )

    # ── data: drop ycloud rows BEFORE tightening the CHECK ─────────
    op.execute(
        "DELETE FROM auphere_owner_channels WHERE provider = 'ycloud'"
    )
    op.execute(
        """
        DELETE FROM tenant_connectors
        WHERE connector_id IN (
            SELECT id FROM connectors WHERE slug = 'whatsapp_ycloud'
        )
        """
    )
    op.execute("DELETE FROM connectors WHERE slug = 'whatsapp_ycloud'")
    op.execute(
        "UPDATE channels SET status = 'disconnected' WHERE provider = 'ycloud'"
    )

    # ── constraint: meta is the only provider ───────────────────────
    op.drop_constraint(
        "ck_auphere_owner_channels_provider",
        "auphere_owner_channels",
        type_="check",
    )
    op.create_check_constraint(
        "ck_auphere_owner_channels_provider",
        "auphere_owner_channels",
        "provider IN ('meta')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_auphere_owner_channels_provider",
        "auphere_owner_channels",
        type_="check",
    )
    op.create_check_constraint(
        "ck_auphere_owner_channels_provider",
        "auphere_owner_channels",
        "provider IN ('ycloud', 'meta')",
    )
    op.alter_column(
        "owner_consultations",
        "provider_message_id",
        new_column_name="ycloud_message_id",
    )
    op.drop_column("auphere_owner_channels", "access_token_encrypted")
    # Deleted ycloud rows are NOT restorable — data downgrade is lossy
    # by design (the provider is gone).
