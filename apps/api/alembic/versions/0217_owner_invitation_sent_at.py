"""Cuándo aceptó el proveedor el correo de una invitación, y las tres frases de auditoría.

Spec 052. ``last_sent_at`` separa «el proveedor lo aceptó» de «no consta»: un
fallo de envío, o una caída entre crear y enviar, no se pinta como un envío. Sin
relleno ni valor por defecto: de las invitaciones que ya existen no consta nada,
y es verdad. Esta migración no escribe en ninguna otra fila ni envía nada
(R3.11): ningún partner existente recibe nada por desplegarla.

Revision ID: 0217_owner_invitation_sent_at
Revises: 0216_out_of_balance_notice_once
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0217_owner_invitation_sent_at"
down_revision: str | Sequence[str] | None = "0216_out_of_balance_notice_once"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "partner.owner_invited",
        "team",
        "info",
        "{actor} invitó a {email} como propietario de {partner}.",
        "{actor} invited {email} as owner of {partner}.",
    ),
    (
        "partner.owner_invitation_resent",
        "team",
        "info",
        "{actor} envió a {email} un enlace nuevo para ser propietario de {partner}; "
        "el anterior ya no sirve.",
        "{actor} sent {email} a new link to become owner of {partner}; "
        "the previous one no longer works.",
    ),
    (
        "partner.owner_invitation_revoked",
        "team",
        "warning",
        "{actor} revocó la invitación de {email} como propietario de {partner}.",
        "{actor} revoked the invitation of {email} as owner of {partner}.",
    ),
)


def upgrade() -> None:
    op.add_column(
        "partner_invitations",
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
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
    op.drop_column("partner_invitations", "last_sent_at")
