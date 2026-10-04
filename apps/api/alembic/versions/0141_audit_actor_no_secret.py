"""The admin secret out of the audit trail.

``PATCH`` of a channel's role (``admin/tenants.py``) stored the actor as
``require_admin_token`` returns it: the whole admin bearer, in a row of the
client's trail, which the partner reads in the console and in the CSV. The
writer now stores ``admin:<first 8>`` like every other admin writer, and
``AuditLog`` refuses the secret whatever the writer does. This rewrites the
rows already written to that same form.

``audit_log`` forces RLS, so without ``app.tenant_id`` the owner only sees
platform rows: the migration lifts FORCE inside its own transaction and puts
it back before committing.

Revision ID: 0141_audit_actor_no_secret
Revises: 0140_password_reset_requests
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0141_audit_actor_no_secret"
down_revision: str | Sequence[str] | None = "0140_password_reset_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_log NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE audit_log SET actor = 'admin:' || left(actor, 8) "
        "WHERE action = 'channel.role_changed' AND actor NOT LIKE '%:%'"
    )
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # The secret is gone on purpose: there is nothing to put back.
    pass
