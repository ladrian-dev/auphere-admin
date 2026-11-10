"""Spec 055: la categoría de un servicio, y las frases de Auditoría de lo nuevo.

- **Categoría** (requisito 7): un texto del propio servicio, de hasta 40
  caracteres; ``NULL`` es «sin categoría». La tabla ya es de tenant con su RLS, y
  esto no la toca. Los servicios que ya existen quedan sin categoría.
- **Auditoría**: cambiar la moneda de los precios, que mueve los servicios con
  ella (requisito 8.6), y reenviar una invitación sin aceptar al pedir
  «recuperar» (requisito 1.8).

Revision ID: 0220_service_category
Revises: 0219_partner_starts_without_pool
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0220_service_category"
down_revision: str | Sequence[str] | None = "0219_partner_starts_without_pool"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "business.price_currency_changed",
        "clients",
        "info",
        "{actor} cambió la moneda de los precios de {client}, y sus servicios con ella.",
        "{actor} changed the price currency of {client}, and its services with it.",
    ),
    (
        "console.member.invite_resent",
        "team",
        "info",
        "{email} pidió recuperar el acceso sin haber aceptado su invitación a {partner}: "
        "recibió un enlace nuevo, y el anterior ya no sirve.",
        "{email} asked to recover access without having accepted their invitation to "
        "{partner}: they got a new link, and the previous one no longer works.",
    ),
)


def upgrade() -> None:
    op.execute("ALTER TABLE reservation_services ADD COLUMN category VARCHAR(40)")
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
    op.execute("ALTER TABLE reservation_services DROP COLUMN category")
