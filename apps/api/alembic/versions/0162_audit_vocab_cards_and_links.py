"""Specs 040 and 041: the new audit rows read in words in the partner's audit.

The WhatsApp link for the owner and the saved card, the charging mode and the
credit line wrote actions with no sentence, so the partner would read them as
code («Auphere · billing.credit_limit_set · partner:…»).

Revision ID: 0162_audit_vocab_cards_and_links
Revises: 0161_partner_card_and_charges
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0162_audit_vocab_cards_and_links"
down_revision: str | Sequence[str] | None = "0161_partner_card_and_charges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (action, category, severity, es, en)
ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "channel.signup_link.created",
        "channels",
        "info",
        "{actor} creó un enlace para que {client} conecte su WhatsApp.",
        "{actor} created a link for {client} to connect its WhatsApp.",
    ),
    (
        "channel.signup_link.revoked",
        "channels",
        "info",
        "{actor} anuló el enlace de WhatsApp de {client}.",
        "{actor} revoked the WhatsApp link of {client}.",
    ),
    (
        "channel.signup_link.connect",
        "channels",
        "info",
        "{client} conectó su WhatsApp con el enlace.",
        "{client} connected its WhatsApp with the link.",
    ),
    (
        "billing.card_saved",
        "billing",
        "info",
        "{actor} guardó una tarjeta para los cobros.",
        "{actor} saved a card for charges.",
    ),
    (
        "billing.card_removed",
        "billing",
        "warning",
        "{actor} quitó la tarjeta de los cobros.",
        "{actor} removed the card used for charges.",
    ),
    (
        "billing.charging_set",
        "billing",
        "info",
        "{actor} cambió cómo se cobra el saldo.",
        "{actor} changed how the balance is charged.",
    ),
    (
        "billing.credit_limit_set",
        "billing",
        "info",
        "{actor} cambió la línea de crédito del pospago.",
        "{actor} changed the postpaid credit line.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for action, category, severity, es, en in ROWS:
        bind.execute(
            sa.text(
                "INSERT INTO console_audit_vocabulary "
                "(action, category, severity, summary_es, summary_en) "
                "VALUES (:action, :category, :severity, :es, :en) "
                "ON CONFLICT (action) DO NOTHING"
            ),
            {"action": action, "category": category, "severity": severity, "es": es, "en": en},
        )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = ANY(:actions)"),
        {"actions": [r[0] for r in ROWS]},
    )
