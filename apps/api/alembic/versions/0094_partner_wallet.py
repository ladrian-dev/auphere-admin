"""Libro de cuota del partner — Fase 3 wallet v1.

Tres tablas, RLS por ``partner_id`` (no por ``principal_id`` ni por
``tenant_id``), FORCE en las tres. Sin GUC, cero filas: el mismo
fail-closed que ``companion.*`` / ``qa.*``.

Unidad: ``quota_tokens()`` (C3). La columna ``fx`` existe y en v1
queda NULL — no hay tipo de cambio en este libro.

``included`` caduca con el mes UTC (como el tope del Companion).
``purchased`` no caduca. Se gasta included primero.

Revision ID: 0094_partner_wallet
Revises: 0093_companion_run_cache
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0094_partner_wallet"
down_revision: str | Sequence[str] | None = "0093_companion_run_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"

_TABLES: tuple[str, ...] = (
    "partner_wallets",
    "partner_allocations",
    "usage_ledger",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE partner_wallets (
            partner_id           uuid        PRIMARY KEY
                                 REFERENCES partners(id) ON DELETE CASCADE,
            included_remaining   bigint      NOT NULL DEFAULT 0,
            included_expires_at  timestamptz NULL,
            purchased_remaining  bigint      NOT NULL DEFAULT 0,
            created_at           timestamptz NOT NULL DEFAULT now(),
            updated_at           timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_partner_wallets_included_nonneg
                CHECK (included_remaining >= 0),
            CONSTRAINT ck_partner_wallets_purchased_nonneg
                CHECK (purchased_remaining >= 0)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE partner_allocations (
            id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            partner_id  uuid        NOT NULL
                            REFERENCES partners(id) ON DELETE CASCADE,
            tenant_id   uuid        NOT NULL
                            REFERENCES tenants(id) ON DELETE CASCADE,
            cap         bigint      NOT NULL,
            remaining   bigint      NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_partner_allocations_partner_tenant
                UNIQUE (partner_id, tenant_id),
            CONSTRAINT ck_partner_allocations_cap_nonneg CHECK (cap >= 0),
            CONSTRAINT ck_partner_allocations_remaining_range
                CHECK (remaining >= 0 AND remaining <= cap)
        )
        """
    )
    op.execute("CREATE INDEX ix_partner_allocations_tenant ON partner_allocations (tenant_id)")

    op.execute(
        """
        CREATE TABLE usage_ledger (
            id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            partner_id         uuid        NOT NULL
                                   REFERENCES partners(id) ON DELETE CASCADE,
            tenant_id          uuid        NULL
                                   REFERENCES tenants(id) ON DELETE SET NULL,
            qty                bigint      NOT NULL,
            bucket             text        NOT NULL,
            usage_record_id    uuid        NULL,
            companion_run_id   uuid        NULL,
            idempotency_key    text        NOT NULL,
            fx                 numeric     NULL,
            created_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_usage_ledger_idempotency UNIQUE (idempotency_key),
            CONSTRAINT ck_usage_ledger_qty_pos CHECK (qty > 0),
            CONSTRAINT ck_usage_ledger_bucket
                CHECK (bucket IN ('included', 'purchased'))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_usage_ledger_partner_created ON usage_ledger (partner_id, created_at DESC)"
    )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_partner_isolation ON {table}
            USING (partner_id = {_PARTNER})
            WITH CHECK (partner_id = {_PARTNER})
            """
        )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "partner_wallets, partner_allocations, usage_ledger TO nexus_app"
    )

    # Filas para partners que ya existen: included = tope Companion del mes,
    # para que el piloto no se quede en 409 el día que aterriza la 0094.
    # purchased empieza en 0; la recarga manual suma a ese cubo.
    op.execute(
        """
        INSERT INTO partner_wallets (
            partner_id, included_remaining, included_expires_at, purchased_remaining
        )
        SELECT
            id,
            companion_monthly_token_cap,
            (date_trunc('month', timezone('UTC', now())) + interval '1 month')
                AT TIME ZONE 'UTC',
            0
        FROM partners
        ON CONFLICT (partner_id) DO NOTHING
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION partner_wallets_on_partner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO partner_wallets (
                partner_id, included_remaining, included_expires_at, purchased_remaining
            )
            VALUES (
                NEW.id,
                NEW.companion_monthly_token_cap,
                (date_trunc('month', timezone('UTC', now())) + interval '1 month')
                    AT TIME ZONE 'UTC',
                0
            )
            ON CONFLICT (partner_id) DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_partners_seed_wallet
        AFTER INSERT ON partners
        FOR EACH ROW EXECUTE FUNCTION partner_wallets_on_partner()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_partners_seed_wallet ON partners")
    op.execute("DROP FUNCTION IF EXISTS partner_wallets_on_partner()")
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_partner_isolation ON {table}")
        op.execute(f"ALTER TABLE IF EXISTS {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS usage_ledger")
    op.execute("DROP TABLE IF EXISTS partner_allocations")
    op.execute("DROP TABLE IF EXISTS partner_wallets")
