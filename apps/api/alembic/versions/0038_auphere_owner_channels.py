"""auphere_owner_channels — DB-backed registry of Auphere backchannel numbers

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-24

Replaces the hardcoded ``settings.auphere_owner_phone`` /
``settings.auphere_owner_number_id`` / ``settings.auphere_owner_webhook_secret``
trio with a per-row registry the operator can manage from the admin UI.

Why:

- **Multi-country**: Auphere CL (+56), AR (+54), MX (+52), ES (+34) — each
  in its own WABA, each potentially with its own webhook secret.
- **Rotation**: when Meta bans a number, swap in a new one without
  redeploy.
- **White-label**: premium tenants can have a dedicated Auphere number.
- **Multi-provider**: ``provider`` distinguishes ``ycloud`` from
  ``meta`` so the same registry survives the eventual YCloud → Meta
  migration.

Pattern: global lookup table (no RLS) — same as ``owner_phone_index``
and ``connectors``. The webhook + outbox resolve a row by ``phone_e164``
(inbound) or by ``OwnerPhoneIndex.auphere_channel_id`` / default
(outbound). When the table is empty AND ``settings.auphere_owner_phone``
is set, the code falls back to the legacy single-number behaviour so
Phase 1 keeps working uninterrupted.

The ``UNIQUE WHERE`` partial index pins ONE default per provider — the
fallback the resolver picks when an ``OwnerPhoneIndex`` row has no
explicit ``auphere_channel_id``.

``OwnerPhoneIndex.auphere_channel_id`` is added nullable + ``ON DELETE
SET NULL`` so deleting a channel falls back to the provider's default
instead of orphaning the owner registration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auphere_owner_channels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("phone_e164", sa.String(20), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_phone_id", sa.String(120), nullable=True),
        # Fernet-encrypted webhook secret. NULL means "use the shared
        # provider-level secret from settings" — useful when every
        # Auphere number under the same WABA shares one HMAC secret.
        sa.Column("webhook_secret_encrypted", postgresql.BYTEA, nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.CheckConstraint(
            "provider IN ('ycloud', 'meta')",
            name="ck_auphere_owner_channels_provider",
        ),
    )
    # Partial unique index: exactly one default per provider AMONG
    # active channels. Allows the operator to flip the default safely
    # (deactivate the old one first, mark the new one as default, then
    # reactivate the old one as non-default).
    op.create_index(
        "uq_auphere_owner_channels_default_per_provider",
        "auphere_owner_channels",
        ["provider"],
        unique=True,
        postgresql_where=sa.text("is_default = true AND active = true"),
    )
    op.create_index(
        "idx_auphere_owner_channels_active",
        "auphere_owner_channels",
        ["active"],
    )

    # Each owner registration can optionally point at a specific Auphere
    # channel. NULL = the resolver picks the default channel for the
    # provider (with optional country_code match against the tenant's
    # market). SET NULL on delete so deleting a channel does NOT
    # cascade-delete owner registrations — they just fall back.
    op.add_column(
        "owner_phone_index",
        sa.Column(
            "auphere_channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auphere_owner_channels.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_owner_phone_index_auphere_channel",
        "owner_phone_index",
        ["auphere_channel_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_owner_phone_index_auphere_channel",
        table_name="owner_phone_index",
    )
    op.drop_column("owner_phone_index", "auphere_channel_id")
    op.drop_index(
        "idx_auphere_owner_channels_active",
        table_name="auphere_owner_channels",
    )
    op.drop_index(
        "uq_auphere_owner_channels_default_per_provider",
        table_name="auphere_owner_channels",
    )
    op.drop_table("auphere_owner_channels")
