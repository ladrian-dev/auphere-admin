"""Spec 016: vocabulary for moving quota, choosing the model, linking the AgendaPro page and connecting a connector.

Revision ID: 0128_console_audit_vocab_016
Revises: 0127_teammate_instructions
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0128_console_audit_vocab_016"
down_revision: str | Sequence[str] | None = "0127_teammate_instructions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS = (
    (
        "console.allocation.move",
        "usage",
        "info",
        "{actor} movió {qty} créditos de {from} a {to}.",
        "{actor} moved {qty} credits from {from} to {to}.",
    ),
    (
        "console.model.update",
        "agents",
        "info",
        "{actor} cambió el modelo de {client} a {model}.",
        "{actor} changed {client}'s model to {model}.",
    ),
    (
        "console.integration.agendapro_url",
        "agents",
        "info",
        "{actor} cambió la agenda de AgendaPro de {client}.",
        "{actor} changed {client}'s AgendaPro booking page.",
    ),
    (
        "console.connector.connect",
        "agents",
        "info",
        "{actor} conectó {connector} en {client}.",
        "{actor} connected {connector} on {client}.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for action, category, severity, summary_es, summary_en in ROWS:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT
                    CAST(:action AS VARCHAR(80)),
                    CAST(:category AS VARCHAR(40)),
                    CAST(:severity AS VARCHAR(10)),
                    CAST(:summary_es AS TEXT),
                    CAST(:summary_en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary
                    WHERE action = CAST(:action AS VARCHAR(80))
                )
                """
            ),
            {
                "action": action,
                "category": category,
                "severity": severity,
                "summary_es": summary_es,
                "summary_en": summary_en,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for action, *_ in ROWS:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :action"),
            {"action": action},
        )
