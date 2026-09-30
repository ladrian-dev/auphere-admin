"""Vocabulario de auditoría para el catálogo del número (spec 022).

Enlazar, cambiar o desconectar el catálogo de Commerce Manager es una
acción consecuente: cambia lo que el agente enseña a los clientes finales
desde el turno siguiente. Sin esta fila la pantalla de Auditoría enseñaría
``console.channel.catalog`` tal cual.

``info``, no ``warning``: cambia qué productos se enseñan, no si el agente
atiende.

Revision ID: 0134_audit_vocab_catalog
Revises: 0133_waba_live_count
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0134_audit_vocab_catalog"
down_revision: str | Sequence[str] | None = "0133_waba_live_count"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS = (
    (
        "console.channel.catalog",
        "channels",
        "info",
        "{actor} cambió el catálogo de {client}.",
        "{actor} changed the catalogue of {client}.",
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
