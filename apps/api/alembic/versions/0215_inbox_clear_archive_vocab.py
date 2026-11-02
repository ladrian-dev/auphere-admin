"""«Vaciar» y «Eliminar» un chat de la Bandeja, dichos en una frase (owner, 2026-11-01).

Revision ID: 0215_inbox_clear_archive_vocab
Revises: 0214_trace_ids_fit_instagram
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0215_inbox_clear_archive_vocab"
down_revision: str | Sequence[str] | None = "0214_trace_ids_fit_instagram"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "inbox.cleared",
        "clients",
        "info",
        "{actor} vació un chat de {client}.",
        "{actor} cleared a chat of {client}.",
    ),
    (
        "inbox.archived",
        "clients",
        "info",
        "{actor} eliminó un chat de {client} de la bandeja.",
        "{actor} deleted a chat of {client} from the inbox.",
    ),
)


def upgrade() -> None:
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
