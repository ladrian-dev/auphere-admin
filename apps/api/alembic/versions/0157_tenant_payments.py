"""tenant_payments — la mensualidad de un cliente, cobrada fuera del proveedor

Un cliente puede pagar su mensualidad por transferencia, en efectivo o por
cualquier medio que no pasa por el proveedor de pagos. Hasta ahora ese pago no
quedaba en ningún sitio: el equipo no tenía cómo anotar quién pagó qué mes.

Una fila es **constancia**, y nada más. No concede nivel, no carga saldo y no
cambia el estado de nadie: registrar un pago no toca el servicio.

Una mensualidad viva por cliente y mes (índice único parcial). Un pago anotado
por error no se borra: se anula, y el mes queda libre para anotarlo bien.

RLS como ``invoices`` (0073): ENABLE con policy por tenant y **sin FORCE**.
El runtime (``nexus_app``) solo ve los pagos de su cliente; el camino de
plataforma los ve todos, que es lo que necesita la vista del mes entre
clientes. ``ON DELETE RESTRICT`` por lo mismo que allí — un cliente con pagos
anotados no se borra en silencio.

Revision ID: 0157_tenant_payments
Revises: 0156_repair_double_cap_debit
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0157_tenant_payments"
down_revision: str | Sequence[str] | None = "0156_repair_double_cap_debit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "tenant_payment.recorded",
        "billing",
        "info",
        "{actor} anotó el pago de una mensualidad de {client}.",
        "{actor} recorded a monthly payment from {client}.",
    ),
    (
        "tenant_payment.voided",
        "billing",
        "warning",
        "{actor} anuló un pago anotado de {client}.",
        "{actor} voided a recorded payment from {client}.",
    ),
)


def upgrade() -> None:
    op.create_table(
        "tenant_payments",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_year", sa.Integer, nullable=False),
        sa.Column("period_month", sa.Integer, nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("paid_on", sa.Date, nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("recorded_by", sa.String(120), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_tenant_payments_period_month"),
        sa.CheckConstraint("amount_cents > 0", name="ck_tenant_payments_amount_positive"),
        sa.CheckConstraint(
            "method IN ('transfer', 'cash', 'zelle', 'paypal', 'crypto', 'other')",
            name="ck_tenant_payments_method",
        ),
    )
    op.create_index(
        "uq_tenant_payments_tenant_period_live",
        "tenant_payments",
        ["tenant_id", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("voided_at IS NULL"),
    )
    op.create_index("ix_tenant_payments_period", "tenant_payments", ["period_year", "period_month"])
    op.execute("GRANT SELECT, INSERT, UPDATE ON tenant_payments TO nexus_app")
    op.execute("ALTER TABLE tenant_payments ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_payments_tenant_isolation ON tenant_payments "
        "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
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
    op.execute("DROP POLICY IF EXISTS tenant_payments_tenant_isolation ON tenant_payments")
    op.execute("REVOKE ALL ON tenant_payments FROM nexus_app")
    op.drop_table("tenant_payments")
