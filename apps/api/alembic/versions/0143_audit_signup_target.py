"""The partner's own sign-up in its audit trail.

``partner.signup.completed`` was written with the bare partner uuid as its
target, and the partner's trail only reads platform rows whose target is
``partner:<id>`` — so nobody saw that the account was created. The writer
now uses ``partner:<id>``; this rewrites the rows already written. They are
platform rows (``tenant_id IS NULL``), which the table owner sees without
lifting RLS.

Revision ID: 0143_audit_signup_target
Revises: 0142_audit_vocab_everything
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0143_audit_signup_target"
down_revision: str | Sequence[str] | None = "0142_audit_vocab_everything"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE audit_log SET target = 'partner:' || target "
        "WHERE action = 'partner.signup.completed' AND tenant_id IS NULL "
        "AND target NOT LIKE 'partner:%'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE audit_log SET target = substr(target, 9) "
        "WHERE action = 'partner.signup.completed' AND tenant_id IS NULL "
        "AND target LIKE 'partner:%'"
    )
