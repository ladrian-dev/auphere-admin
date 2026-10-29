"""Instagram and Messenger channels (spec 049)

Revision ID: 0175_meta_social_channels
Revises: 0174_reservation_calendars
Create Date: 2026-10-29

Three pieces, none of them a new table:

- ``messenger`` joins the ``channel_type`` enum (``instagram`` is there since
  0001). Instagram channels use ``provider="meta_instagram"`` and the
  professional account id; Messenger channels ``provider="meta_messenger"``
  and the Page id. Credentials go encrypted in ``channels.config_encrypted``,
  the same column the WhatsApp numbers already use.
- ``partners.beta_channels``: the channels Auphere has switched on for a
  partner before Meta approves them for everyone. A partner without the value
  does not see the channel at all (constitution §V).
- The audit vocabulary for connecting, disconnecting and erasing data.

``ALTER TYPE ... ADD VALUE`` runs inside the migration transaction because the
value is not used in it, same as 0059.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0175_meta_social_channels"
down_revision: str | Sequence[str] | None = "0174_reservation_calendars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "channel.instagram.connect",
        "channels",
        "warning",
        "{actor} conectó la cuenta de Instagram {account} en {client}.",
        "{actor} connected the Instagram account {account} for {client}.",
    ),
    (
        "channel.messenger.connect",
        "channels",
        "warning",
        "{actor} conectó la Página de Facebook {account} en {client}.",
        "{actor} connected the Facebook Page {account} for {client}.",
    ),
    (
        "channel.meta_social.disconnect",
        "channels",
        "warning",
        "{actor} desconectó {account} en {client}.",
        "{actor} disconnected {account} from {client}.",
    ),
    (
        "channel.meta_social.needs_attention",
        "channels",
        "warning",
        "{account} dejó de responder en {client}: hay que revisarlo.",
        "{account} stopped answering for {client}: it needs checking.",
    ),
    (
        "channel.meta_social.purge",
        "channels",
        "info",
        "Se borraron los mensajes de {account} en {client}, 30 días después de desconectarlo.",
        "The messages of {account} for {client} were erased, 30 days after it was disconnected.",
    ),
    (
        "customer.meta_social.erase",
        "channels",
        "warning",
        "{actor} borró los datos de una persona de {account} en {client}.",
        "{actor} erased a person's data from {account} for {client}.",
    ),
)


def upgrade() -> None:
    op.execute("ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'messenger'")

    op.add_column(
        "partners",
        sa.Column(
            "beta_channels",
            postgresql.ARRAY(sa.String(16)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
    )
    op.create_check_constraint(
        "ck_partners_beta_channels",
        "partners",
        "beta_channels <@ ARRAY['instagram', 'messenger']::varchar[]",
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
    op.drop_constraint("ck_partners_beta_channels", "partners", type_="check")
    op.drop_column("partners", "beta_channels")
    # 'messenger' stays in channel_type: PG can't drop enum values.
