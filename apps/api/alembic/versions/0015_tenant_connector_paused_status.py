"""tenant_connector status: add 'paused' to the CHECK constraint

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-13

Block M.6 — operator control plane adds a ``Pause`` action on each
installed connector. Pause keeps the upstream tokens and config intact
but skips the connector in the runtime tool dispatch loop. Disconnect
already exists for a one-way revoke.

The status column uses ``String(20)`` + a ``CHECK`` constraint (the
schema chose CHECK over a native enum in 0013 deliberately, so the
migration here is a drop + recreate of the constraint — no ``ALTER
TYPE`` and no ``BYPASSRLS`` dance is needed).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


_NEW_CHECK = (
    "status IN ('pending', 'connected', 'partial', 'needs_reauth', "
    "'paused', 'disconnected', 'error')"
)

_OLD_CHECK = (
    "status IN ('pending', 'connected', 'partial', 'needs_reauth', "
    "'disconnected', 'error')"
)


def upgrade() -> None:
    op.drop_constraint("ck_tc_status", "tenant_connectors", type_="check")
    op.create_check_constraint("ck_tc_status", "tenant_connectors", _NEW_CHECK)


def downgrade() -> None:
    # If any rows have status='paused' at the time of downgrade the
    # CREATE CHECK below will fail. Operator must transition them to
    # 'connected' or 'disconnected' first. We do NOT auto-coerce because
    # the choice is semantic (resume vs revoke).
    op.drop_constraint("ck_tc_status", "tenant_connectors", type_="check")
    op.create_check_constraint("ck_tc_status", "tenant_connectors", _OLD_CHECK)
