"""Spec 050 (D5): the template status CHECK takes Meta's fourteen states.

``ck_tplstatus_status`` (0019) allowed seven lowercase values, while Meta
sends ``event`` in uppercase and with fourteen states (``PENDING_DELETION``,
``ARCHIVED``, ``LOCKED``…). Every ``message_template_status_update`` failed
its insert. The new CHECK compares ``upper(status)``, so the rows written in
lowercase before stay valid and every reader keeps comparing without case.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0207_template_status_check"
down_revision: str | Sequence[str] | None = "0206_whatsapp_identity_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = (
    "APPROVED",
    "REJECTED",
    "PENDING",
    "PAUSED",
    "DISABLED",
    "PENDING_DELETION",
    "DELETED",
    "ARCHIVED",
    "UNARCHIVED",
    "FLAGGED",
    "IN_APPEAL",
    "LIMIT_EXCEEDED",
    "LOCKED",
    "REINSTATED",
    "UNKNOWN",
)


def upgrade() -> None:
    op.execute("ALTER TABLE whatsapp_template_status DROP CONSTRAINT IF EXISTS ck_tplstatus_status")
    allowed = ", ".join(f"'{s}'" for s in STATES)
    op.execute(
        "ALTER TABLE whatsapp_template_status ADD CONSTRAINT ck_tplstatus_status "
        f"CHECK (upper(status) IN ({allowed}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE whatsapp_template_status DROP CONSTRAINT IF EXISTS ck_tplstatus_status")
    op.execute(
        "ALTER TABLE whatsapp_template_status ADD CONSTRAINT ck_tplstatus_status "
        "CHECK (status IN ('approved', 'pending', 'rejected', 'flagged', 'paused', 'disabled', 'unknown'))"
    )
