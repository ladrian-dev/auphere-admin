"""Spec 075 (requisito 8.4): las frases de auditoría de editar una plantilla.

Editar una plantilla de WhatsApp deja ``console.template.edit`` (la persona de
la consola) o ``admin.template.edit`` (el operador del panel). Sin su frase, la
consola las enseña en crudo (``test_console_audit_words`` y
``test_every_console_action_written_has_vocabulary``).

Revision ID: 0243_template_edit_vocabulary
Revises: 0242_service_memberships
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0243_template_edit_vocabulary"
down_revision: str | Sequence[str] | None = "0242_service_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "console.template.edit",
        "channels",
        "info",
        "{actor} editó la plantilla {template} de {client}.",
        "{actor} edited the template {template} of {client}.",
    ),
    (
        "admin.template.edit",
        "channels",
        "info",
        "Auphere editó la plantilla {template} de {client}.",
        "Auphere edited the template {template} of {client}.",
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
