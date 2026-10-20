"""Vocabulario de auditoría de los teléfonos (spec 031, data-model §0162).

Cada entrada y cada cierre de un teléfono queda en la Auditoría con la persona,
el teléfono y quién lo cerró (R7.6). No se usa el prefijo ``device.*``: es de
las máquinas del escritorio (spec 002). El teléfono va en ``{machine}`` —su
nombre legible, «iPhone de Valeria»— y el motivo en ``{reason}``, que
``audit_words.REASON`` traduce.

Revision ID: 0162_client_phone_audit_vocab
Revises: 0161_client_push_deliveries
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0162_client_phone_audit_vocab"
down_revision: str | Sequence[str] | None = "0161_client_push_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "client_phone.signed_in",
        "auth",
        "info",
        "{actor} entró en la app desde {machine}.",
        "{actor} signed in to the app from {machine}.",
    ),
    (
        "client_phone.signed_out",
        "auth",
        "info",
        "{actor} cerró la sesión de la app en {machine}.",
        "{actor} signed out of the app on {machine}.",
    ),
    (
        "client_phone.closed",
        "auth",
        "warning",
        "{actor} cerró la sesión de {email} en {machine}.",
        "{actor} closed {email}'s session on {machine}.",
    ),
    (
        "client_phone.revoked",
        "auth",
        "info",
        "Se cerró la sesión de {email} en {machine}: {reason}.",
        "{email}'s session on {machine} was closed: {reason}.",
    ),
    (
        "client_account.deletion_requested",
        "auth",
        "warning",
        "{actor} pidió borrar su cuenta.",
        "{actor} asked to delete their account.",
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
