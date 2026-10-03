"""Vocabulario de auditoría para desvincular un número.

Desconectar un canal no existía —ni en la consola ni en la API—, así que su
acción tampoco tenía cómo leerse. Sin esta fila, la auditoría le enseñaría al
partner `console.channel.disconnect` tal cual, que es justo lo que la pantalla
de Auditoría existe para no hacer.

`warning` y no `info`, como su gemela `console.channel.connect`: soltar el
número por el que atiende un agente es de las cosas que alguien va a buscar en
el registro el día que se pregunte por qué dejaron de llegar mensajes.

Revision ID: 0131_audit_vocab_disconnect
Revises: 0130_client_limit_is_a_guard
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0131_audit_vocab_disconnect"
down_revision: str | Sequence[str] | None = "0130_client_limit_is_a_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS = (
    (
        "console.channel.disconnect",
        "channels",
        "warning",
        "{actor} desvinculó un número de {client}.",
        "{actor} unlinked a number from {client}.",
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
