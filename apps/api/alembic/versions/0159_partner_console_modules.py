"""partners.console_modules — spec 032

Which views and services of the console a partner has, chosen by Auphere from
the operator panel. The nav modules are the sidebar's (panel, clients, usage,
audit, knowledge, workstation, team, billing, keys); ``companion`` is the
assistant bubble.

A column of ``partners`` and not a table: ``partners`` is the row the console
gate already reads on every request (before any RLS scope exists), and a
partner-scoped table would have to be read before its own GUC can be set.
``updated_by`` is the platform audit row naming the operator.

Backfill: every partner keeps every view it has today, and ``companion`` where
``companion_enabled`` is on — nothing changes for anyone on deploy.

Revision ID: 0159_partner_console_modules
Revises: 0158_ledger_kind_and_monthly_cap
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision: str = "0159_partner_console_modules"
down_revision: str | Sequence[str] | None = "0158_ledger_kind_and_monthly_cap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAV = ("panel", "clients", "usage", "audit", "knowledge", "workstation", "team", "billing", "keys")
ALL = (*NAV, "companion")


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{v}'" for v in values) + "]::varchar[]"


def upgrade() -> None:
    op.add_column(
        "partners",
        sa.Column(
            "console_modules",
            ARRAY(sa.String(16)),
            nullable=False,
            server_default=sa.text(_array(NAV)),
        ),
    )
    op.execute(
        "UPDATE partners SET console_modules = console_modules || ARRAY['companion']::varchar[] "
        "WHERE companion_enabled"
    )
    op.create_check_constraint(
        "ck_partners_console_modules", "partners", f"console_modules <@ {_array(ALL)}"
    )
    # The operator's change reads in words in the partner's audit too.
    op.execute(
        "INSERT INTO console_audit_vocabulary "
        "(action, category, severity, summary_es, summary_en) VALUES "
        "('partner_access.updated', 'team', 'info', "
        "'Auphere cambió las secciones de tu consola.', "
        "'Auphere changed the sections of your console.') "
        "ON CONFLICT (action) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM console_audit_vocabulary WHERE action = 'partner_access.updated'")
    op.drop_constraint("ck_partners_console_modules", "partners", type_="check")
    op.drop_column("partners", "console_modules")
