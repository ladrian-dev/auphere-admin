"""The agent's escalation reads as a sentence.

``conversation.escalated`` is written by the agent's own tool
(``apps/mcp``, ``escalate_to_human``), which the vocabulary guard did not
scan, so in staging it read «Auphere · conversation.escalated · …». The
reason the model wrote stays out of the sentence: it is free text and can
carry the end customer's data.

Revision ID: 0145_audit_vocab_escalated
Revises: 0144_audit_revoke_names_person
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0145_audit_vocab_escalated"
down_revision: str | Sequence[str] | None = "0144_audit_revoke_names_person"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROW = (
    "conversation.escalated",
    "agents",
    "warning",
    "El agente de {client} pasó una conversación al equipo.",
    "{client}'s agent handed a conversation to the team.",
)


def upgrade() -> None:
    action, category, severity, es, en = ROW
    op.get_bind().execute(
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
    op.get_bind().execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": ROW[0]}
    )
