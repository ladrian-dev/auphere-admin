"""Las dos acciones de la agenda que la auditoría de la consola no sabía decir.

``console.agenda.update`` (spec 057: encender o apagar la agenda de un agente) y
``reservations.template_requested`` (las plantillas de Reservas que se piden a Meta)
se escribían sin frase en ``console_audit_vocabulary``: la consola las enseñaba con
el código en crudo. Lo vio ``tests/unit/test_console_audit_words.py`` el 2026-11-10,
al correr la suite entera antes de pasar a producción.

Revision ID: 0230_audit_words_agenda
Revises: 0229_agenda_from_agent
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0230_audit_words_agenda"
down_revision: str | Sequence[str] | None = "0229_agenda_from_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "console.agenda.update",
        "agents",
        "info",
        "{actor} cambió la agenda de un agente de {client}.",
        "{actor} changed the agenda of an agent of {client}.",
    ),
    (
        "reservations.template_requested",
        "clients",
        "info",
        "{actor} pidió a Meta una plantilla de Reservas para {client}.",
        "{actor} asked Meta for a Reservations template for {client}.",
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
