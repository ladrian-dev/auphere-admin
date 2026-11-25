"""Spec 077 — clientes de solo envío y membresía que corta.

- ``tenants.send_only``: el cliente no tiene agente y solo envía por la API.
  Apagado por defecto: todo cliente que ya existe sigue como estaba.
- ``service_memberships``: la membresía mensual de un cliente, la pague él por
  Stripe o el partner de su saldo. Es del cliente: FORCE RLS por ``tenant_id``
  con la política canónica (garantía 1). Una viva por cliente; quitarla la
  archiva, nunca la borra (constitución §IV).
- ``usage_ledger.kind`` gana ``fixed_fee``: el cargo fijo mensual al saldo del
  partner. Va aparte de ``debit`` para que no cuente como consumo de
  conversaciones ni como gasto de un agente.
- Las frases de ``console_audit_vocabulary`` de lo que el panel deja en la
  auditoría: claves de un cliente, su membresía y la marca de solo envío.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0242_service_memberships"
down_revision: str | Sequence[str] | None = "0241_ad_conversions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

#: Los kinds del libro tal como los dejó la 0195, más el nuevo.
_KINDS_BEFORE = (
    "debit",
    "credit_admin",
    "credit_stripe",
    "expiry",
    "allocation_legacy",
    "opening_credit",
    "opening_debit",
    "credit_manual",
    "credit_reversal",
    "absorbed",
    "bag_assign",
    "bag_return",
)
_KINDS_AFTER = (*_KINDS_BEFORE, "fixed_fee")


def _in(kinds: tuple[str, ...]) -> str:
    return ", ".join(f"'{k}'" for k in kinds)


#: (action, category, severity, es, en): how the console's audit says each
#: action the operator leaves on a client (spec 029: never a code).
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "tenant_key.create",
        "keys",
        "warning",
        "Auphere creó una clave de envío por API para {client}.",
        "Auphere created an API sending key for {client}.",
    ),
    (
        "tenant_key.rotate",
        "keys",
        "warning",
        "Auphere rotó una clave de envío por API de {client}.",
        "Auphere rotated an API sending key of {client}.",
    ),
    (
        "tenant_key.revoke",
        "keys",
        "critical",
        "Auphere revocó una clave de envío por API de {client}.",
        "Auphere revoked an API sending key of {client}.",
    ),
    (
        "tenant.send_only_changed",
        "clients",
        "warning",
        "Auphere cambió si {client} es de solo envío por API.",
        "Auphere changed whether {client} only sends through the API.",
    ),
    (
        "tenant.billing_updated",
        "billing",
        "info",
        "Auphere cambió el partner o el plan de cobro de {client}.",
        "Auphere changed the partner or the billing plan of {client}.",
    ),
    (
        "membership.configure",
        "billing",
        "info",
        "Auphere configuró la membresía mensual de {client}.",
        "Auphere set up the monthly membership of {client}.",
    ),
    (
        "membership.checkout_link",
        "billing",
        "info",
        "Auphere creó un enlace de pago de la membresía de {client}.",
        "Auphere created a payment link for the membership of {client}.",
    ),
    (
        "membership.invoice_link",
        "billing",
        "info",
        "Auphere envió la factura pendiente de la membresía de {client}.",
        "Auphere sent the unpaid invoice of the membership of {client}.",
    ),
    (
        "membership.charge_now",
        "billing",
        "info",
        "Auphere cobró del saldo la membresía de {client}.",
        "Auphere charged the membership of {client} to the balance.",
    ),
    (
        "membership.cancel",
        "billing",
        "warning",
        "Auphere canceló la membresía de {client}: sus envíos se cortan.",
        "Auphere cancelled the membership of {client}: its sends stop.",
    ),
    (
        "membership.archive",
        "billing",
        "info",
        "Auphere dejó de exigir una membresía a {client}.",
        "Auphere stopped requiring a membership from {client}.",
    ),
)


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("send_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.execute(
        """
        CREATE TABLE service_memberships (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            payer text NOT NULL,
            amount_cents integer NOT NULL,
            pending_amount_cents integer,
            status text NOT NULL DEFAULT 'pending',
            current_period_start timestamptz,
            current_period_end timestamptz,
            next_period_start timestamptz,
            billing_email text,
            stripe_customer_id text,
            stripe_subscription_id text,
            stripe_checkout_session_id text,
            checkout_url text,
            checkout_expires_at timestamptz,
            last_synced_at timestamptz,
            last_failure text,
            archived_at timestamptz,
            archived_by text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_service_memberships_payer
                CHECK (payer IN ('stripe', 'partner_wallet')),
            CONSTRAINT ck_service_memberships_status
                CHECK (status IN ('pending', 'active', 'past_due', 'canceled')),
            CONSTRAINT ck_service_memberships_amount CHECK (amount_cents > 0),
            CONSTRAINT ck_service_memberships_pending_amount
                CHECK (pending_amount_cents IS NULL OR pending_amount_cents > 0),
            CONSTRAINT uq_service_memberships_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT fk_service_memberships_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.create_index(
        "uq_service_memberships_live",
        "service_memberships",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "uq_service_memberships_subscription",
        "service_memberships",
        ["stripe_subscription_id"],
        unique=True,
        postgresql_where=sa.text("stripe_subscription_id IS NOT NULL"),
    )
    op.create_index("ix_service_memberships_tenant_id", "service_memberships", ["tenant_id"])
    op.execute("ALTER TABLE service_memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE service_memberships FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY service_memberships_tenant_isolation ON service_memberships "
        f"USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON service_memberships TO nexus_app")

    op.drop_constraint("ck_usage_ledger_kind", "usage_ledger", type_="check")
    op.create_check_constraint(
        "ck_usage_ledger_kind", "usage_ledger", f"kind IN ({_in(_KINDS_AFTER)})"
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
    # Give back what the fixed charges took before their entries go, so no
    # partner's balance is left lower than its book.
    op.execute(
        """
        UPDATE partner_wallets w
           SET purchased_remaining = w.purchased_remaining + f.total
          FROM (SELECT partner_id, SUM(qty) AS total
                  FROM usage_ledger WHERE kind = 'fixed_fee'
                 GROUP BY partner_id) f
         WHERE w.partner_id = f.partner_id
        """
    )
    op.execute("DELETE FROM usage_ledger WHERE kind = 'fixed_fee'")
    op.drop_constraint("ck_usage_ledger_kind", "usage_ledger", type_="check")
    op.create_check_constraint(
        "ck_usage_ledger_kind", "usage_ledger", f"kind IN ({_in(_KINDS_BEFORE)})"
    )
    op.execute("DROP TABLE IF EXISTS service_memberships")
    op.drop_column("tenants", "send_only")
