"""La bolsa de cada cliente, el libro de doble entrada y el tope por agente —
spec 047, T155 (requisitos 43, 44, 45 y 46; ``data-model.md`` §7, research
D25 a D29).

Unidades: cien milésimas de la moneda (las de los créditos de hoy), con signo
en los asientos y nunca por debajo de cero en una bolsa.

- ``partner_wallets.currency``: la moneda de la cuenta (USD para los de hoy).
- ``client_wallets``: la bolsa del cliente (dinero apartado), con su moneda, su
  saldo, el mes en curso con su base y su gasto, el relleno y la deduplicación de
  los avisos. RLS por partner, como ``partner_allocations``.
- ``client_wallet_entries``: el lado del cliente de cada asiento.
- ``wallet_transfers``: cada traspaso entre la cuenta y las bolsas, con su clave de
  idempotencia y el cambio del BCE que usó.
- ``usage_ledger``: los kinds de los traspasos (``bag_assign`` saca de la cuenta,
  ``bag_return`` devuelve).
- ``agent_monthly_spend``: el gasto del mes de cada agente, para su tope.
- ``fx_rates`` (plataforma): el cambio de referencia del BCE.
- ``balance_requests``: «Pedir saldo», una al día por cliente.
- ``partner_build_budget`` y ``build_budget_requests``: la partida «Construcción y
  pruebas», con ``partners.build_budget_default_micros`` (50 en la moneda de la
  cuenta).
- ``wallet_migration_proposals``: «Repartir tu saldo en bolsas»; hasta confirmarla,
  el partner sigue con ``partner_allocations``.

Revision ID: 0195_client_wallets
Revises: 0194_connector_activations
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0195_client_wallets"
down_revision: str | Sequence[str] | None = "0194_connector_activations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"
_TENANT = "(NULLIF(current_setting('app.tenant_id', true), ''))::uuid"

OLD_KINDS = (
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
)
NEW_KINDS = (*OLD_KINDS, "bag_assign", "bag_return")
ENTRY_KINDS = (
    "assign",
    "lower",
    "move_in",
    "move_out",
    "refill",
    "debit_turn",
    "currency_change",
    "migration",
)
TRANSFER_KINDS = ("assign", "lower", "move", "refill", "currency_change", "migration")


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


STATEMENTS = (
    """
    ALTER TABLE partner_wallets
        ADD COLUMN currency char(3) NOT NULL DEFAULT 'USD',
        ADD CONSTRAINT ck_partner_wallets_currency CHECK (currency IN ('EUR', 'USD'))
    """,
    "ALTER TABLE partners ADD COLUMN build_budget_default_micros bigint NOT NULL DEFAULT 5000000",
    """
    CREATE TABLE client_wallets (
        tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
        partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
        currency char(3) NOT NULL,
        balance_micros bigint NOT NULL DEFAULT 0,
        month date NOT NULL,
        month_base_micros bigint NOT NULL DEFAULT 0,
        month_spent_micros bigint NOT NULL DEFAULT 0,
        refill_up_to_micros bigint,
        alert_low_enabled boolean NOT NULL DEFAULT true,
        low_alerted_month date,
        not_enough_alerted_month date,
        empty_alerted_on date,
        revision integer NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_client_wallets_currency CHECK (currency IN ('EUR', 'USD')),
        CONSTRAINT ck_client_wallets_balance CHECK (balance_micros >= 0),
        CONSTRAINT ck_client_wallets_refill CHECK (
            refill_up_to_micros IS NULL OR refill_up_to_micros > 0
        )
    )
    """,
    "CREATE INDEX ix_client_wallets_partner ON client_wallets (partner_id)",
    f"""
    CREATE TABLE wallet_transfers (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
        kind varchar(20) NOT NULL,
        from_tenant_id uuid,
        to_tenant_id uuid,
        partner_amount_micros bigint NOT NULL DEFAULT 0,
        partner_currency char(3) NOT NULL,
        client_amount_micros bigint NOT NULL DEFAULT 0,
        client_currency char(3) NOT NULL,
        fx_rate numeric(18, 8) NOT NULL DEFAULT 1,
        fx_date date,
        idempotency_key text NOT NULL,
        actor_id varchar(160) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_wallet_transfers_idempotency UNIQUE (partner_id, idempotency_key),
        CONSTRAINT ck_wallet_transfers_kind CHECK (kind IN ({_in(TRANSFER_KINDS)}))
    )
    """,
    f"""
    CREATE TABLE client_wallet_entries (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
        transfer_id uuid REFERENCES wallet_transfers(id) ON DELETE SET NULL,
        kind varchar(20) NOT NULL,
        amount_micros bigint NOT NULL,
        balance_after_micros bigint NOT NULL,
        currency char(3) NOT NULL,
        usage_ref text,
        agent_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_client_wallet_entries_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_client_wallet_entries_wallet FOREIGN KEY (tenant_id)
            REFERENCES client_wallets (tenant_id) ON DELETE CASCADE,
        CONSTRAINT ck_client_wallet_entries_kind CHECK (kind IN ({_in(ENTRY_KINDS)})),
        CONSTRAINT ck_client_wallet_entries_after CHECK (balance_after_micros >= 0)
    )
    """,
    "CREATE INDEX ix_client_wallet_entries_tenant ON client_wallet_entries (tenant_id, created_at DESC)",
    "CREATE UNIQUE INDEX uq_client_wallet_entries_usage ON client_wallet_entries (usage_ref) "
    "WHERE usage_ref IS NOT NULL",
    """
    CREATE TABLE agent_monthly_spend (
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid NOT NULL,
        month date NOT NULL,
        spent_micros bigint NOT NULL DEFAULT 0,
        warned_at timestamptz,
        reached_at timestamptz,
        PRIMARY KEY (tenant_id, agent_id, month),
        CONSTRAINT fk_agent_monthly_spend_agent FOREIGN KEY (tenant_id, agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE fx_rates (
        date date NOT NULL,
        base char(3) NOT NULL,
        quote char(3) NOT NULL,
        rate numeric(18, 8) NOT NULL,
        fetched_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (date, base, quote),
        CONSTRAINT ck_fx_rates_rate CHECK (rate > 0)
    )
    """,
    """
    CREATE TABLE balance_requests (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
        requested_by varchar(160) NOT NULL,
        note varchar(280),
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_balance_requests_tenant_id UNIQUE (tenant_id, id)
    )
    """,
    "CREATE UNIQUE INDEX uq_balance_requests_daily ON balance_requests "
    "(tenant_id, ((created_at AT TIME ZONE 'UTC')::date))",
    """
    CREATE TABLE partner_build_budget (
        partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
        month date NOT NULL,
        cap_micros bigint NOT NULL,
        spent_micros bigint NOT NULL DEFAULT 0,
        warned_at timestamptz,
        exhausted_at timestamptz,
        PRIMARY KEY (partner_id, month),
        CONSTRAINT ck_partner_build_budget_cap CHECK (cap_micros >= 0)
    )
    """,
    """
    CREATE TABLE build_budget_requests (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
        requested_by varchar(160) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX uq_build_budget_requests_daily ON build_budget_requests "
    "(partner_id, ((created_at AT TIME ZONE 'UTC')::date))",
    """
    CREATE TABLE wallet_migration_proposals (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
        proposal jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        confirmed_at timestamptz,
        confirmed_by varchar(160)
    )
    """,
)
#: Del partner (``data-model.md`` §7): RLS FORCE por ``partner_id``.
PARTNER_TABLES = (
    "wallet_transfers",
    "partner_build_budget",
    "build_budget_requests",
    "wallet_migration_proposals",
)
#: Del cliente (garantía 1): RLS FORCE con la política de cliente canónica. El
#: partner las toca poniendo, dentro de su transacción, el ``app.tenant_id`` del
#: cliente (``services/wallet/bags.as_client``).
TENANT_TABLES = (
    "client_wallets",
    "client_wallet_entries",
    "balance_requests",
    "agent_monthly_spend",
)


def upgrade() -> None:
    op.drop_constraint("ck_usage_ledger_kind", "usage_ledger", type_="check")
    op.create_check_constraint(
        "ck_usage_ledger_kind", "usage_ledger", f"kind IN ({_in(NEW_KINDS)})"
    )
    for statement in STATEMENTS:
        op.execute(statement)
    for table in PARTNER_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_partner_isolation ON {table} "
            f"USING (partner_id = {_PARTNER}) WITH CHECK (partner_id = {_PARTNER})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON fx_rates TO nexus_app")


def downgrade() -> None:
    for table in (
        "wallet_migration_proposals",
        "build_budget_requests",
        "partner_build_budget",
        "balance_requests",
        "fx_rates",
        "agent_monthly_spend",
        "client_wallet_entries",
        "wallet_transfers",
        "client_wallets",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("ALTER TABLE partners DROP COLUMN IF EXISTS build_budget_default_micros")
    op.execute(
        "ALTER TABLE partner_wallets DROP CONSTRAINT IF EXISTS ck_partner_wallets_currency, "
        "DROP COLUMN IF EXISTS currency"
    )
    op.execute("DELETE FROM usage_ledger WHERE kind IN ('bag_assign', 'bag_return')")
    op.drop_constraint("ck_usage_ledger_kind", "usage_ledger", type_="check")
    op.create_check_constraint(
        "ck_usage_ledger_kind", "usage_ledger", f"kind IN ({_in(OLD_KINDS)})"
    )
