"""WhatsApp identity (BSUID), marketing opt-outs and account health — spec 050, iteration 1

Revision ID: 0206_whatsapp_identity_health
Revises: 0205_meta_social_channels
Create Date: 2026-10-29

- ``customers`` gains ``bsuid`` (Meta's business-scoped user id, unique per
  tenant when set), ``phone`` (E.164 digits) and ``username``. ``identifier``
  keeps its meaning and its value: the phone when the person had one at
  creation, the BSUID otherwise. ``phone`` is backfilled from ``identifier``
  where the identifier is digits.
- ``whatsapp_opt_outs`` gains ``customer_id``, ``scope`` (``marketing`` |
  ``all``), ``source`` (``meta`` | ``keyword`` | ``operator``) and
  ``lifted_by``. Existing rows stay ``scope='all'``: a consent already given
  is not loosened. ``recipient_phone`` becomes nullable (a BSUID-only person
  has none).
- ``whatsapp_template_status`` gains ``previous_category``,
  ``pending_category`` and ``quality``. ``tenant_id`` is backfilled from the
  WABA's channels where exactly one tenant owns it.
- ``channels.problem_reason`` also admits ``account_review`` and
  ``account_alert``.
- ``resolve_waba_tenants(waba_id)``: SECURITY DEFINER, returns only tenant
  ids — account and template events that carry no phone number are applied
  under each owner's RLS.
- Audit vocabulary for the new actions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0206_whatsapp_identity_health"
down_revision: str | Sequence[str] | None = "0205_meta_social_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "customer.opt_out.recorded",
        "channels",
        "info",
        "Una persona se dio de baja de los mensajes de marketing de {phone} en {client}.",
        "A person opted out of marketing messages from {phone} for {client}.",
    ),
    (
        "customer.opt_out.lifted",
        "channels",
        "warning",
        "{actor} levantó una baja de marketing de {phone} en {client}: {reason}.",
        "{actor} lifted a marketing opt-out on {phone} for {client}: {reason}.",
    ),
    (
        "channel.whatsapp.pin_rotated",
        "channels",
        "warning",
        "{actor} cambió el PIN de dos pasos de {phone} en {client}.",
        "{actor} changed the two-step PIN of {phone} for {client}.",
    ),
    (
        "channel.whatsapp.template_state",
        "channels",
        "warning",
        "Meta cambió el estado de la plantilla {template} de {client}: {reason}.",
        "Meta changed the state of the template {template} of {client}: {reason}.",
    ),
    (
        "channel.whatsapp.account_state",
        "channels",
        "warning",
        "Meta cambió el estado de la cuenta de WhatsApp de {phone} en {client}: {reason}.",
        "Meta changed the WhatsApp account state of {phone} for {client}: {reason}.",
    ),
    (
        "channel.whatsapp.name_decision",
        "channels",
        "info",
        "Meta resolvió el nombre visible de {phone} en {client}: {reason}.",
        "Meta decided on the display name of {phone} for {client}: {reason}.",
    ),
)


def upgrade() -> None:
    # ── customers ────────────────────────────────────────────────────────
    op.add_column("customers", sa.Column("bsuid", sa.String(160), nullable=True))
    op.add_column("customers", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column("customers", sa.Column("username", sa.String(64), nullable=True))
    op.create_index(
        "uq_customers_tenant_bsuid",
        "customers",
        ["tenant_id", "bsuid"],
        unique=True,
        postgresql_where=sa.text("bsuid IS NOT NULL"),
    )
    op.create_index("ix_customers_tenant_phone", "customers", ["tenant_id", "phone"])
    op.execute(
        "UPDATE customers SET phone = identifier "
        "WHERE phone IS NULL AND identifier ~ '^[0-9]{6,20}$'"
    )

    # ── whatsapp_opt_outs ────────────────────────────────────────────────
    op.add_column(
        "whatsapp_opt_outs",
        sa.Column("customer_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Garantía 1: between client tables the key carries ``tenant_id``. A
    # customer the retention deletes lets go of the column only: the opt-out
    # stays, by phone, because a consent withdrawn is not forgotten.
    op.execute(
        "ALTER TABLE whatsapp_opt_outs ADD CONSTRAINT fk_optout_customer "
        "FOREIGN KEY (tenant_id, customer_id) REFERENCES customers (tenant_id, id) "
        "ON DELETE SET NULL (customer_id)"
    )
    op.add_column(
        "whatsapp_opt_outs",
        sa.Column("scope", sa.String(12), nullable=False, server_default="all"),
    )
    op.add_column(
        "whatsapp_opt_outs",
        sa.Column("source", sa.String(12), nullable=False, server_default="keyword"),
    )
    op.add_column("whatsapp_opt_outs", sa.Column("lifted_by", sa.String(255), nullable=True))
    op.alter_column("whatsapp_opt_outs", "recipient_phone", nullable=True)
    op.create_check_constraint(
        "ck_optout_scope", "whatsapp_opt_outs", "scope IN ('marketing', 'all')"
    )
    op.create_check_constraint(
        "ck_optout_source", "whatsapp_opt_outs", "source IN ('meta', 'keyword', 'operator')"
    )
    op.create_index(
        "uq_optout_tenant_channel_customer_active",
        "whatsapp_opt_outs",
        ["tenant_id", "channel_id", "customer_id"],
        unique=True,
        postgresql_where=sa.text("opted_in_at IS NULL AND customer_id IS NOT NULL"),
    )
    op.execute(
        """
        UPDATE whatsapp_opt_outs o
           SET customer_id = c.id
          FROM customers c
         WHERE o.customer_id IS NULL
           AND c.tenant_id = o.tenant_id
           AND c.phone = regexp_replace(o.recipient_phone, '[^0-9]', '', 'g')
        """
    )

    # ── whatsapp_template_status ─────────────────────────────────────────
    op.add_column(
        "whatsapp_template_status", sa.Column("previous_category", sa.String(40), nullable=True)
    )
    op.add_column(
        "whatsapp_template_status", sa.Column("pending_category", sa.String(40), nullable=True)
    )
    op.add_column("whatsapp_template_status", sa.Column("quality", sa.String(12), nullable=True))
    op.execute(
        """
        UPDATE whatsapp_template_status t
           SET tenant_id = owners.tenant_id
          FROM (
                SELECT config->>'waba_id' AS waba_id, min(tenant_id::text)::uuid AS tenant_id
                  FROM channels
                 WHERE provider = 'meta' AND config->>'waba_id' IS NOT NULL
                 GROUP BY config->>'waba_id'
                HAVING count(DISTINCT tenant_id) = 1
               ) owners
         WHERE t.tenant_id IS NULL AND t.waba_id = owners.waba_id
        """
    )

    # ── channels.problem_reason ──────────────────────────────────────────
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS ck_channels_problem_reason")
    op.execute(
        """
        ALTER TABLE channels ADD CONSTRAINT ck_channels_problem_reason CHECK (
            problem_reason IS NULL
            OR problem_reason IN ('quality', 'auth_expired', 'coexistence_inactive',
                                  'meta_error', 'account_review', 'account_alert')
        )
        """
    )

    # ── WABA → tenants, for events that carry no phone number ────────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_waba_tenants(p_waba_id text)
        RETURNS SETOF uuid
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET row_security = off
        AS $$
            SELECT DISTINCT tenant_id
              FROM channels
             WHERE provider = 'meta'
               AND config->>'waba_id' = p_waba_id
               AND status <> 'disconnected'
        $$;
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION resolve_waba_tenants(text) TO nexus_app")

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
    op.execute("DROP FUNCTION IF EXISTS resolve_waba_tenants(text)")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS ck_channels_problem_reason")
    op.execute(
        """
        UPDATE channels SET problem_reason = 'meta_error'
         WHERE problem_reason IN ('account_review', 'account_alert')
        """
    )
    op.execute(
        """
        ALTER TABLE channels ADD CONSTRAINT ck_channels_problem_reason CHECK (
            problem_reason IS NULL
            OR problem_reason IN ('quality', 'auth_expired', 'coexistence_inactive', 'meta_error')
        )
        """
    )
    op.drop_column("whatsapp_template_status", "quality")
    op.drop_column("whatsapp_template_status", "pending_category")
    op.drop_column("whatsapp_template_status", "previous_category")
    op.drop_index("uq_optout_tenant_channel_customer_active", table_name="whatsapp_opt_outs")
    op.drop_constraint("ck_optout_source", "whatsapp_opt_outs", type_="check")
    op.drop_constraint("ck_optout_scope", "whatsapp_opt_outs", type_="check")
    op.execute("DELETE FROM whatsapp_opt_outs WHERE recipient_phone IS NULL")
    op.alter_column("whatsapp_opt_outs", "recipient_phone", nullable=False)
    op.drop_column("whatsapp_opt_outs", "lifted_by")
    op.drop_column("whatsapp_opt_outs", "source")
    op.drop_column("whatsapp_opt_outs", "scope")
    op.execute("ALTER TABLE whatsapp_opt_outs DROP CONSTRAINT IF EXISTS fk_optout_customer")
    op.drop_column("whatsapp_opt_outs", "customer_id")
    op.drop_index("ix_customers_tenant_phone", table_name="customers")
    op.drop_index("uq_customers_tenant_bsuid", table_name="customers")
    op.drop_column("customers", "username")
    op.drop_column("customers", "phone")
    op.drop_column("customers", "bsuid")
