"""QA-19: vocabulary for login/logout and client alta/status.

Revision ID: 0105_console_audit_vocab_auth
Revises: 0104_operator_auth_if_missing
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0105_console_audit_vocab_auth"
down_revision: str | Sequence[str] | None = "0104_operator_auth_if_missing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS = (
    (
        "console.auth.login",
        "auth",
        "info",
        "{actor} inició sesión.",
        "{actor} signed in.",
    ),
    (
        "console.auth.logout",
        "auth",
        "info",
        "{actor} cerró sesión.",
        "{actor} signed out.",
    ),
    (
        "console.client.create",
        "clients",
        "info",
        "{actor} dio de alta a {client}.",
        "{actor} created {client}.",
    ),
    (
        "console.client.status",
        "clients",
        "info",
        "{actor} cambió el estado de {client} a {status}.",
        "{actor} set {client} to {status}.",
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
                    :action, :category, :severity, :summary_es, :summary_en
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary WHERE action = :action
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
    bind.execute(
        sa.text(
            "DELETE FROM console_audit_vocabulary WHERE action IN "
            "('console.auth.login', 'console.auth.logout')"
        )
    )
