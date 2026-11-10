"""Spec 047, enmienda (58.5): las frases de Auditoría de las guías del sector.

El panel escribe tres acciones al revisar y convertir una guía generada
(``services/builder/guides/promotion.py``) y la 0207 no sembró sus frases;
``test_console_audit_words`` exige una por acción que escribe el código.

Solo datos de plataforma: ``console_audit_vocabulary`` no tiene ``tenant_id``.

Revision ID: 0209_audit_words_sector_guides
Revises: 0208_sector_test_needs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from alembic import op

revision: str = "0209_audit_words_sector_guides"
down_revision: str | Sequence[str] | None = "0208_sector_test_needs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (acción, categoría, gravedad, español, inglés)
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("generated_guide.reviewed", "agents", "info",
     "{actor} revisó la guía generada para {client}.",
     "{actor} reviewed the guide generated for {client}."),
    ("generated_guide.promoted", "agents", "info",
     "{actor} convirtió la guía generada para {client} en guía de Auphere.",
     "{actor} turned the guide generated for {client} into an Auphere guide."),
    ("sector_guide.promoted", "agents", "info",
     "{actor} añadió una guía de Auphere a partir de una guía generada.",
     "{actor} added an Auphere guide from a generated guide."),
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
