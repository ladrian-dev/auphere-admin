"""F5 — admin_impersonation_sessions (admin scope + audit, not a partner session).

Impersonation is an operator overlay: admin token + operator principal.
Never a partner JWT and never a console cookie. FORCE RLS via
``app.is_admin`` (same extra policy shape as F4, no partner isolation,
no BYPASSRLS). Without the GUC, nexus_app sees zero rows.

Revision ID: 0100_impersonation
Revises: 0099_support_tickets
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0100_impersonation"
down_revision: str | Sequence[str] | None = "0099_support_tickets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "admin_impersonation_sessions"
_ADMIN = "current_setting('app.is_admin', true) = 'true'"

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "impersonate.start",
        "admin",
        "warning",
        "{actor} empezó impersonación del partner {partner}",
        "{actor} started impersonation of partner {partner}",
    ),
    (
        "impersonate.revoke",
        "admin",
        "info",
        "{actor} revocó la impersonación del partner {partner}",
        "{actor} revoked impersonation of partner {partner}",
    ),
)


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "operator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "operator_auth.principals.id",
                ondelete="CASCADE",
                name="fk_admin_impersonation_operator",
            ),
            nullable=False,
        ),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE", name="fk_admin_impersonation_partner"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="900"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("char_length(reason) >= 8", name="ck_admin_impersonation_reason_len"),
        sa.CheckConstraint(
            "ttl_seconds BETWEEN 60 AND 3600",
            name="ck_admin_impersonation_ttl",
        ),
    )
    op.create_index("ix_admin_impersonation_operator_id", _TABLE, ["operator_id"])
    op.create_index("ix_admin_impersonation_partner_id", _TABLE, ["partner_id"])
    op.create_index("ix_admin_impersonation_expires_at", _TABLE, ["expires_at"])

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_admin_unscoped ON {_TABLE}
        USING ({_ADMIN})
        WITH CHECK ({_ADMIN})
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {_TABLE} TO nexus_app")

    for action, category, severity, es, en in VOCABULARY:
        es_q = es.replace("'", "''")
        en_q = en.replace("'", "''")
        op.execute(
            "INSERT INTO console_audit_vocabulary "
            "(action, category, severity, summary_es, summary_en) "
            f"VALUES ('{action}', '{category}', '{severity}', '{es_q}', '{en_q}') "
            "ON CONFLICT (action) DO UPDATE SET category = EXCLUDED.category, "
            "severity = EXCLUDED.severity, summary_es = EXCLUDED.summary_es, "
            "summary_en = EXCLUDED.summary_en, updated_at = now()"
        )


def downgrade() -> None:
    for action, *_rest in VOCABULARY:
        op.execute(f"DELETE FROM console_audit_vocabulary WHERE action = '{action}'")
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_admin_unscoped ON {_TABLE}")
    op.execute(f"ALTER TABLE IF EXISTS {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE IF EXISTS {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_admin_impersonation_expires_at", table_name=_TABLE)
    op.drop_index("ix_admin_impersonation_partner_id", table_name=_TABLE)
    op.drop_index("ix_admin_impersonation_operator_id", table_name=_TABLE)
    op.drop_table(_TABLE)
