"""Avisos para el cliente y la auditoría del acceso — spec 030 (R1.8, R15).

Dos cosas pequeñas que la iteración 1 necesita:

* ``console_notifications.audience`` — ``partner`` (lo de siempre) o
  ``client``. La campana del partner lista solo ``partner``; la de la persona
  de un cliente, solo ``client`` y de su cliente. Una columna y no una tabla
  nueva porque el aviso es el mismo objeto con otro destinatario: lo que
  cambia es quién lo ve, no qué es (plan D20).
* El vocabulario de las acciones del acceso, que escribe el admin con la
  identidad del operador. Sin frase, la Auditoría del partner pintaría
  «Auphere · client_access.updated · …».

Revision ID: 0148_client_audience_vocab
Revises: 0147_client_access
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0148_client_audience_vocab"
down_revision: str | Sequence[str] | None = "0147_client_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "client_access.updated",
        "clients",
        "info",
        "Auphere cambió el acceso de {client} a su consola.",
        "Auphere changed {client}'s access to its console.",
    ),
    (
        "client_member.invited",
        "clients",
        "info",
        "Auphere invitó a una persona de {client} a su consola.",
        "Auphere invited a person from {client} to its console.",
    ),
    (
        "client_member.resent",
        "clients",
        "info",
        "Auphere reenvió una invitación de {client}.",
        "Auphere resent an invitation for {client}.",
    ),
    (
        "client_member.revoked",
        "clients",
        "warning",
        "Auphere retiró el acceso de una persona de {client}.",
        "Auphere removed a person's access for {client}.",
    ),
    (
        "client_member.joined",
        "clients",
        "info",
        "{actor} entró por primera vez en la consola de {client}.",
        "{actor} signed in to {client}'s console for the first time.",
    ),
)


def upgrade() -> None:
    op.add_column(
        "console_notifications",
        sa.Column("audience", sa.String(10), nullable=False, server_default="partner"),
    )
    op.create_check_constraint(
        "ck_console_notifications_audience",
        "console_notifications",
        "audience IN ('partner', 'client')",
    )
    op.create_index(
        "ix_console_notifications_audience",
        "console_notifications",
        ["partner_id", "audience", "external_client_ref", "created_at"],
    )
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
    op.drop_index("ix_console_notifications_audience", table_name="console_notifications")
    op.drop_constraint("ck_console_notifications_audience", "console_notifications", type_="check")
    op.drop_column("console_notifications", "audience")
