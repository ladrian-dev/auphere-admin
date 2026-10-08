"""Lo que una persona hace en la Bandeja, dicho en una frase — spec 030 (R16.1).

La Auditoría del partner lee las filas de sus clientes: las acciones de la
Bandeja salen con la persona (``client:<correo>``) y una frase, nunca con el
contenido de un mensaje o de una nota (solo longitudes y nombres de etiqueta).

Revision ID: 0151_inbox_audit_vocab
Revises: 0150_inbox_tables
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0151_inbox_audit_vocab"
down_revision: str | Sequence[str] | None = "0150_inbox_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "inbox.takeover",
        "clients",
        "info",
        "{actor} tomó el control de una conversación de {client}.",
        "{actor} took over a conversation of {client}.",
    ),
    (
        "inbox.released",
        "clients",
        "info",
        "{actor} devolvió una conversación de {client} al agente.",
        "{actor} handed a conversation of {client} back to the agent.",
    ),
    (
        "inbox.message_sent",
        "clients",
        "info",
        "{actor} respondió a un cliente de {client} desde la bandeja.",
        "{actor} replied to a customer of {client} from the inbox.",
    ),
    (
        "inbox.attachment_sent",
        "clients",
        "info",
        "{actor} envió un archivo a un cliente de {client} desde la bandeja.",
        "{actor} sent a file to a customer of {client} from the inbox.",
    ),
    (
        "inbox.resolved",
        "clients",
        "info",
        "{actor} resolvió una conversación de {client}.",
        "{actor} resolved a conversation of {client}.",
    ),
    (
        "inbox.reopened",
        "clients",
        "info",
        "{actor} reabrió una conversación de {client}.",
        "{actor} reopened a conversation of {client}.",
    ),
    (
        "inbox.tagged",
        "clients",
        "info",
        "{actor} etiquetó una conversación de {client}.",
        "{actor} tagged a conversation of {client}.",
    ),
    (
        "inbox.untagged",
        "clients",
        "info",
        "{actor} quitó una etiqueta de una conversación de {client}.",
        "{actor} removed a tag from a conversation of {client}.",
    ),
    (
        "inbox.note_saved",
        "clients",
        "info",
        "{actor} guardó una nota interna de un contacto de {client}.",
        "{actor} saved an internal note about a contact of {client}.",
    ),
    (
        "inbox.reply_saved",
        "clients",
        "info",
        "{actor} guardó una respuesta para la bandeja de {client}.",
        "{actor} saved a reply for {client}'s inbox.",
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
