"""«Conectores», nunca «Integraciones», también en las frases de Auditoría —
spec 047 (requisito 49.1), recorrido UI. La 0197 sembró tres frases que decían
«una integración»; en pantalla la palabra es «conector».

Revision ID: 0203_audit_vocab_connectors
Revises: 0202_audit_vocabulary_more
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0203_audit_vocab_connectors"
down_revision: str | Sequence[str] | None = "0202_audit_vocabulary_more"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (acción, español y inglés de ahora, español e inglés de la 0197)
ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    ("integration.activated",
     "{actor} activó un conector en un agente de {client}.",
     "{actor} turned on a connector for an agent of {client}.",
     "{actor} activó una integración en un agente de {client}.",
     "{actor} turned on an integration for an agent of {client}."),
    ("integration.deactivated",
     "{actor} desconectó un conector de {client}.",
     "{actor} disconnected a connector of {client}.",
     "{actor} desconectó una integración de {client}.",
     "{actor} disconnected an integration of {client}."),
    ("integration.reauth_required",
     "Un conector de {client} hay que volver a autorizarlo.",
     "A connector of {client} needs to be authorized again.",
     "Una integración de {client} hay que volver a autorizarla.",
     "An integration of {client} needs to be authorized again."),
)  # fmt: skip


def _vocabulary() -> sa.TableClause:
    return sa.table(
        "console_audit_vocabulary",
        sa.column("action", sa.String),
        sa.column("summary_es", sa.Text),
        sa.column("summary_en", sa.Text),
    )


def upgrade() -> None:
    vocabulary = _vocabulary()
    for action, es, en, _old_es, _old_en in ROWS:
        op.execute(
            vocabulary.update()
            .where(vocabulary.c.action == action)
            .values(summary_es=es, summary_en=en)
        )


def downgrade() -> None:
    vocabulary = _vocabulary()
    for action, _es, _en, old_es, old_en in ROWS:
        op.execute(
            vocabulary.update()
            .where(vocabulary.c.action == action)
            .values(summary_es=old_es, summary_en=old_en)
        )
