"""usage_ledger.kind y partner_allocations.period_month — spec 033

Dos columnas para que el dinero se pueda contar sin adivinar.

``usage_ledger.kind`` dice qué es cada asiento: ``debit`` (gasto), ``credit_admin``
(recarga de Auphere), ``credit_stripe`` (compra por el proveedor), ``expiry``
(caducidad del saldo comprado) o ``allocation_legacy`` (los asientos del doble
descuento del tope, 2026-09-02 → 2026-10-10, que no eran dinero). Hasta ahora el tipo
se deducía del prefijo de la clave y los lectores de gasto contaban **todo** lo que
no acabara en ``:allocation``: una recarga del admin aparecía como gasto.

El relleno lee la clave una vez, aquí, y a partir de esta revisión todo escritor
declara el tipo (sin valor por defecto: un asiento sin tipo no entra).

``partner_allocations.period_month`` es el mes de calendario (UTC) al que
corresponde el ``remaining`` del tope. La reposición pasa a ser mensual: el cron
repone cuando el mes cambia, y la columna hace la operación idempotente.

El relleno corre partner a partner con ``app.partner_id`` fijado: las dos tablas
tienen RLS forzada y la migración no puede depender de que su rol la salte.

Revision ID: 0158_ledger_kind_and_monthly_cap
Revises: 0157_tenant_payments
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0158_ledger_kind_and_monthly_cap"
down_revision: str | Sequence[str] | None = "0157_tenant_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "debit",
    "credit_admin",
    "credit_stripe",
    "expiry",
    "allocation_legacy",
    "opening_credit",
    "opening_debit",
)

# ``\:`` keeps SQLAlchemy from reading ``:allocation`` as a bind parameter.
BACKFILL = r"""
DO $$
DECLARE p uuid;
BEGIN
  FOR p IN SELECT id FROM partners LOOP
    PERFORM set_config('app.partner_id', p::text, true);
    UPDATE usage_ledger SET kind = 'credit_admin'
     WHERE partner_id = p AND idempotency_key LIKE 'admin_purchased\:%';
    UPDATE usage_ledger SET kind = 'expiry'
     WHERE partner_id = p AND idempotency_key LIKE 'credit_expired\:%';
    UPDATE usage_ledger SET kind = 'allocation_legacy'
     WHERE partner_id = p AND idempotency_key LIKE '%\:allocation';
  END LOOP;
  PERFORM set_config('app.partner_id', '', true);
END $$;
"""

# The opening entry. Purchased balance was written by hand in the database
# before the admin top-up existed (2026-09-08) and Stripe purchases never wrote
# an entry, so the stored balance and the book disagree from the start. The
# difference is written ONCE per partner as ``opening_credit`` /
# ``opening_debit`` and the book balances from this revision on: the history
# is not hidden, it is named.
OPENING = r"""
DO $$
DECLARE p uuid; stored bigint; expected bigint; diff bigint;
BEGIN
  FOR p IN SELECT id FROM partners LOOP
    PERFORM set_config('app.partner_id', p::text, true);
    SELECT purchased_remaining INTO stored FROM partner_wallets WHERE partner_id = p;
    IF stored IS NULL THEN CONTINUE; END IF;
    SELECT COALESCE(SUM(CASE
             WHEN kind IN ('credit_admin', 'credit_stripe') THEN qty
             WHEN kind = 'debit' AND bucket = 'purchased' THEN -qty
             WHEN kind = 'expiry' THEN -qty
             ELSE 0 END), 0)
      INTO expected FROM usage_ledger WHERE partner_id = p;
    diff := stored - expected;
    IF diff > 0 THEN
      INSERT INTO usage_ledger (id, partner_id, qty, bucket, kind, idempotency_key)
      VALUES (gen_random_uuid(), p, diff, 'purchased', 'opening_credit', 'opening:' || p::text);
    ELSIF diff < 0 THEN
      INSERT INTO usage_ledger (id, partner_id, qty, bucket, kind, idempotency_key)
      VALUES (gen_random_uuid(), p, -diff, 'purchased', 'opening_debit', 'opening:' || p::text);
    END IF;
  END LOOP;
  PERFORM set_config('app.partner_id', '', true);
END $$;
"""


def upgrade() -> None:
    op.add_column(
        "usage_ledger",
        sa.Column("kind", sa.String(24), nullable=False, server_default="debit"),
    )
    op.get_bind().execute(sa.text(BACKFILL))
    op.alter_column("usage_ledger", "kind", server_default=None)
    op.create_check_constraint(
        "ck_usage_ledger_kind",
        "usage_ledger",
        "kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")",
    )
    op.create_index("ix_usage_ledger_partner_kind", "usage_ledger", ["partner_id", "kind"])
    op.get_bind().execute(sa.text(OPENING))

    # R7.3: setting a client's cap is audited; the partner reads it in words.
    op.get_bind().execute(
        sa.text(
            "INSERT INTO console_audit_vocabulary "
            "(action, category, severity, summary_es, summary_en) VALUES "
            "('console.allocation.set', 'usage', 'info', "
            "'{actor} fijó el tope mensual de {to} en {amount}.', "
            "'{actor} set {to}''s monthly cap to {amount}.') "
            "ON CONFLICT (action) DO NOTHING"
        )
    )

    op.add_column(
        "partner_allocations",
        sa.Column(
            "period_month",
            sa.Date(),
            nullable=False,
            server_default=sa.text("(date_trunc('month', timezone('UTC', now())))::date"),
        ),
    )


DROP_OPENING = r"""
DO $$
DECLARE p uuid;
BEGIN
  FOR p IN SELECT id FROM partners LOOP
    PERFORM set_config('app.partner_id', p::text, true);
    DELETE FROM usage_ledger
     WHERE partner_id = p AND kind IN ('opening_credit', 'opening_debit');
  END LOOP;
  PERFORM set_config('app.partner_id', '', true);
END $$;
"""


def downgrade() -> None:
    # The opening entries exist only to make this revision's book balance;
    # before it, every entry with a NULL tenant counted as spend.
    op.get_bind().execute(sa.text(DROP_OPENING))
    op.get_bind().execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = 'console.allocation.set'")
    )
    op.drop_column("partner_allocations", "period_month")
    op.drop_index("ix_usage_ledger_partner_kind", table_name="usage_ledger")
    op.drop_constraint("ck_usage_ledger_kind", "usage_ledger", type_="check")
    op.drop_column("usage_ledger", "kind")
