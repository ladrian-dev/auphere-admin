"""Spec 017: vocabulary for switching a capability and changing the billing e-mail.

Revision ID: 0129_console_audit_vocab_017
Revises: 0128_console_audit_vocab_016
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0129_console_audit_vocab_017"
down_revision: str | Sequence[str] | None = "0128_console_audit_vocab_016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS = (
    (
        "console.capability.update",
        "agents",
        "info",
        "{actor} cambió la capacidad {capability} de {client}: {change}.",
        "{actor} changed {client}'s capability {capability}: {change}.",
    ),
    (
        "console.billing.email_update",
        "billing",
        "info",
        "{actor} cambió el correo de facturación.",
        "{actor} changed the billing e-mail.",
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
