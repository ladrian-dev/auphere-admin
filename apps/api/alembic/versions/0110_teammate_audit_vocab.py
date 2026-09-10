"""Spec 003 — vocabulario de auditoría de los teammates (Requisito 13).

Ocho actos, y en todos el ``{actor}`` es la **persona**: un teammate nunca es
actor de auditoría (`[[00-revision-del-diseno-v3]]` §5.6).

Revision ID: 0110_teammate_audit_vocab
Revises: 0109_teammates
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0110_teammate_audit_vocab"
down_revision: str | Sequence[str] | None = "0109_teammates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS = (
    ("teammate.created", "teammates", "info", "{actor} creó el teammate {teammate}.", "{actor} created the teammate {teammate}."),
    ("teammate.updated", "teammates", "info", "{actor} cambió el teammate {teammate}.", "{actor} changed the teammate {teammate}."),
    ("teammate.archived", "teammates", "info", "{actor} archivó el teammate {teammate}.", "{actor} archived the teammate {teammate}."),
    ("local_policy.ceiling_changed", "teammates", "warning", "{actor} puso el techo de ejecución local en {ceiling}.", "{actor} set the local execution ceiling to {ceiling}."),
    ("local_policy.pref_changed", "teammates", "info", "{actor} cambió su preferencia de ejecución local ({executable}: {mode}).", "{actor} changed their local execution preference ({executable}: {mode})."),
    ("local_exec.allowed_once", "teammates", "info", "{actor} permitió una vez {executable} en {machine}.", "{actor} allowed {executable} once on {machine}."),
    ("local_exec.allowed_by_policy", "teammates", "info", "{actor} tenía «permitir siempre» y {executable} se ejecutó en {machine}.", "{actor} had “always allow” and {executable} ran on {machine}."),
    ("local_exec.denied_by_policy", "teammates", "warning", "{actor} tenía «nunca» y {executable} no se ejecutó.", "{actor} had “never” and {executable} did not run."),
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
            {"action": action, "category": category, "severity": severity, "summary_es": summary_es, "summary_en": summary_en},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for action, *_ in ROWS:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = CAST(:action AS VARCHAR(80))"),
            {"action": action},
        )
