"""Revoking someone's access says whose access it was.

The partner's owner now sees these rows (they are written under
``partner:<id>`` when the team decides it), and «retiró el acceso de una
persona» did not say who. The row carries the email; a row without one
reads «alguien».

Revision ID: 0144_audit_revoke_names_person
Revises: 0143_audit_signup_target
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0144_audit_revoke_names_person"
down_revision: str | Sequence[str] | None = "0143_audit_signup_target"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTION = "principal.access_revoked"
NEW = (
    "{actor} retiró el acceso de {email}: sus sesiones y sus máquinas.",
    "{actor} revoked {email}'s access: their sessions and their machines.",
)
OLD = (
    "{actor} retiró el acceso de una persona: sus sesiones y sus máquinas.",
    "{actor} revoked a person's access: their sessions and their machines.",
)


def _set(es: str, en: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE console_audit_vocabulary SET summary_es = :es, summary_en = :en "
            "WHERE action = :action"
        ),
        {"es": es, "en": en, "action": ACTION},
    )


def upgrade() -> None:
    _set(*NEW)


def downgrade() -> None:
    _set(*OLD)
