"""Desde cuándo lee el agente una conversación, y el cierre por inactividad — spec 064.

Requisitos 4 y 5. Una conversación resuelta es un asunto cerrado: si el contacto
vuelve a escribir, el agente empieza sin lo anterior. Y el negocio puede hacer
que las conversaciones sin mensajes se resuelvan solas.

``conversations``:

- ``context_from``: desde cuándo lee el agente el hilo. ``NULL`` = desde
  ``attended_at``, como hasta ahora. La Bandeja no lo usa: sigue enseñando el
  hilo entero.
- ``cut_on_reopen``: lo pone ``inbox_lifecycle.resolve``. Dice que la próxima
  reapertura por el contacto o por un aviso del sistema corta. Las filas que ya
  existen quedan en ``false``: una conversación resuelta antes de esta
  migración no corta hasta que se vuelva a resolver (requisito 4.8).

``client_access``:

- ``inbox_autoclose_hours``: el plazo sin mensajes. ``NULL`` = nunca, que es el
  valor de partida; 24, 72, 168 o 720 (requisito 5.1).

``console_audit_vocabulary``: la frase de ``inbox.settings_changed``, la acción
que deja el cambio de ese plazo. Sin ella la consola la enseñaría con el código en
crudo (``tests/unit/test_console_audit_words.py``).

Ninguna de las tres reescribe su tabla: son anulables, o un booleano con valor
por defecto constante. Las dos tablas ya llevan RLS por ``tenant_id``.

El identificador cabe en los 32 caracteres de ``alembic_version.version_num``.

Revision ID: 0236_context_cut_and_autoclose
Revises: 0235_quedate_listing_catalog_ids
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0236_context_cut_and_autoclose"
down_revision: str | Sequence[str] | None = "0235_quedate_listing_catalog_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_client_access_inbox_autoclose"
#: As in 0229: if a long transaction holds ``conversations``, fail in 5 s instead of
#: queueing an ACCESS EXCLUSIVE lock that would stop every read and write behind it.
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s'"

#: (action, category, severity, es, en)
VOCABULARY: tuple[str, str, str, str, str] = (
    "inbox.settings_changed",
    "clients",
    "info",
    "{actor} cambió el cierre por inactividad de la bandeja de {client}.",
    "{actor} changed the inactivity closing of the inbox of {client}.",
)


def upgrade() -> None:
    op.execute(LOCK_TIMEOUT)
    op.add_column(
        "conversations", sa.Column("context_from", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("cut_on_reopen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("client_access", sa.Column("inbox_autoclose_hours", sa.Integer(), nullable=True))
    op.create_check_constraint(
        CHECK,
        "client_access",
        "inbox_autoclose_hours IS NULL OR inbox_autoclose_hours IN (24, 72, 168, 720)",
    )
    action, category, severity, es, en = VOCABULARY
    op.get_bind().execute(
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
    op.execute(LOCK_TIMEOUT)
    op.get_bind().execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": VOCABULARY[0]}
    )
    op.drop_constraint(CHECK, "client_access", type_="check")
    op.drop_column("client_access", "inbox_autoclose_hours")
    op.drop_column("conversations", "cut_on_reopen")
    op.drop_column("conversations", "context_from")
