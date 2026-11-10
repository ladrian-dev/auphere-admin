"""QA 2026-10-30: las frases de Auditoría de dos acciones nuevas de canales.

El cron de meta_social desconecta un canal cuyo acceso lleva una semana
perdido (INC-09) y la consola guarda cómo atiende Instagram los comentarios
(INC-07). ``test_console_audit_words`` exige una frase por acción que
escribe el código.

Solo datos de plataforma: ``console_audit_vocabulary`` no tiene ``tenant_id``.

Revision ID: 0211_audit_words_meta_fixes
Revises: 0210_sector_tests_read_only
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from alembic import op

revision: str = "0211_audit_words_meta_fixes"
down_revision: str | Sequence[str] | None = "0210_sector_tests_read_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (acción, categoría, gravedad, español, inglés)
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("channel.meta_social.access_lost", "channels", "warning",
     "Se desconectó {account} en {client}: llevaba una semana sin acceso a Meta.",
     "{account} was disconnected from {client}: it had no access to Meta for a week."),
    ("console.channel.comments", "channels", "info",
     "{actor} cambió cómo atiende el agente los comentarios de Instagram en {client}.",
     "{actor} changed how the agent handles Instagram comments for {client}."),
)  # fmt: skip


def upgrade() -> None:
    vocabulary = sa.table(
        "console_audit_vocabulary",
        sa.column("action", sa.String),
        sa.column("category", sa.String),
        sa.column("severity", sa.String),
        sa.column("summary_es", sa.Text),
        sa.column("summary_en", sa.Text),
    )
    for action, category, severity, es, en in VOCABULARY:
        op.execute(
            insert(vocabulary)
            .values(
                action=action, category=category, severity=severity, summary_es=es, summary_en=en
            )
            .on_conflict_do_nothing(index_elements=["action"])
        )


def downgrade() -> None:
    actions = ", ".join(f"'{row[0]}'" for row in VOCABULARY)
    op.execute(f"DELETE FROM console_audit_vocabulary WHERE action IN ({actions})")
