"""Lo que se hace con los agentes de un cliente, dicho en una frase — spec 030
(iteración 3, R14 y R16.1).

La Auditoría del partner enseña estas filas como el resto: quién, sobre qué
cliente, y nunca un prompt.

Revision ID: 0154_agents_audit_vocab
Revises: 0153_agents_backfill
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0154_agents_audit_vocab"
down_revision: str | Sequence[str] | None = "0153_agents_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "agent.created",
        "agents",
        "info",
        "{actor} creó un agente nuevo para {client}.",
        "{actor} created a new agent for {client}.",
    ),
    (
        "agent.renamed",
        "agents",
        "info",
        "{actor} cambió el nombre de un agente de {client}.",
        "{actor} renamed an agent of {client}.",
    ),
    (
        "agent.archived",
        "agents",
        "warning",
        "{actor} archivó un agente de {client}.",
        "{actor} archived an agent of {client}.",
    ),
    (
        "channel.agent_assigned",
        "channels",
        "warning",
        "{actor} cambió qué agente contesta en un número de {client}.",
        "{actor} changed which agent answers on a number of {client}.",
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
