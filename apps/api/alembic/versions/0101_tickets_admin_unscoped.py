"""F4 follow-up — tickets/ticket_events admin unscoped (app.is_admin).

0099 FORCE only has ``{table}_partner_isolation`` (partner_id = GUC).
``apply_admin_to_session`` clears ``app.partner_id``. Without this extra
policy, GET /admin/tickets is zero rows under FORCE. Same shape as
0100 ``admin_impersonation_sessions_admin_unscoped``. No BYPASSRLS,
partner isolation stays, FORCE stays.

Revision ID: 0101_tickets_admin_unscoped
Revises: 0100_impersonation
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0101_tickets_admin_unscoped"
down_revision: str | Sequence[str] | None = "0100_impersonation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES: tuple[str, ...] = ("tickets", "ticket_events")
_ADMIN = "current_setting('app.is_admin', true) = 'true'"


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            CREATE POLICY {table}_admin_unscoped ON {table}
            USING ({_ADMIN})
            WITH CHECK ({_ADMIN})
            """
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_admin_unscoped ON {table}")
