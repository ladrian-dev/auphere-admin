"""F2 admin — partner_model_allowlist (closed catalog techo).

FORCE RLS by ``app.partner_id`` (0094/0097). Seed/backfill the three G1
ids. On partner create, insert those three.

Revision ID: 0098_partner_model_allowlist
Revises: 0097_workflow_packs
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0098_partner_model_allowlist"
down_revision: str | Sequence[str] | None = "0097_workflow_packs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "partner_model_allowlist"
_POLICY = f"{_TABLE}_partner_isolation"
_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"

_G1 = (
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
)
_VALUES = ", ".join(f"('{mid}')" for mid in _G1)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE {_TABLE} (
            partner_id  uuid  NOT NULL
                          REFERENCES partners(id) ON DELETE CASCADE,
            model_id    text  NOT NULL,
            PRIMARY KEY (partner_id, model_id)
        )
        """
    )
    op.execute(f"CREATE INDEX ix_{_TABLE}_partner_id ON {_TABLE} (partner_id)")

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE}
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {_TABLE} TO nexus_app")

    op.execute(
        f"""
        INSERT INTO {_TABLE} (partner_id, model_id)
        SELECT p.id, m.model_id
          FROM partners p
          CROSS JOIN (VALUES {_VALUES}) AS m(model_id)
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION partner_model_allowlist_on_partner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM set_config('app.partner_id', NEW.id::text, true);
            INSERT INTO {_TABLE} (partner_id, model_id)
            VALUES
                (NEW.id, 'openai/gpt-5.6-sol'),
                (NEW.id, 'openai/gpt-5.6-terra'),
                (NEW.id, 'openai/gpt-5.6-luna')
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_partners_seed_model_allowlist
        AFTER INSERT ON partners
        FOR EACH ROW EXECUTE FUNCTION partner_model_allowlist_on_partner()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_partners_seed_model_allowlist ON partners")
    op.execute("DROP FUNCTION IF EXISTS partner_model_allowlist_on_partner()")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"ALTER TABLE IF EXISTS {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE IF EXISTS {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")
