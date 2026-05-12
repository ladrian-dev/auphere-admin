"""drop seeded OAuth connector rows (calendly, google_calendar, notion)

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-12

Composio becomes the single source of truth for OAuth connectors. The
``GET /admin/connectors`` endpoint now merges:

- ``connectors`` rows whose ``auth_kind`` is NOT ``oauth_composio`` —
  ``whatsapp_ycloud`` and ``agendapro`` (custom, seeded from local YAMLs)
- a dynamic list pulled from ``composio.auth_configs.list()`` — whatever
  toolkits the operator has registered in the Composio dashboard

Rows for the three seed YAMLs we used to ship for OAuth (``calendly``,
``google_calendar``, ``notion``) are stale: they no longer reflect the
real catalog (Composio is authoritative), and the slug ``google_calendar``
doesn't even match what Composio returns (``googlecalendar``). Strip them
plus any ``tenant_connectors`` rows that pointed at them. Phase 1
production has no tenant connected to these three connectors yet (only
the canary tenant exists, with zero installs), so the cascade is empty
in practice — the defensive cleanup is here for safety.

Downgrade is intentionally a no-op: the seed YAMLs were deleted in the
same commit, so we can't reconstitute the rows. If the change rolls
back, the operator must restore the seeds and re-run seed_connectors.py.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop any tenant_connectors pointing at the soon-to-be-removed
    # connector rows (FK ondelete=RESTRICT on tenant_connectors.connector_id
    # forces us to clear children first). The migration role bypasses RLS
    # via BYPASSRLS so the DELETE is unscoped — safe because the rows are
    # in a known-empty state in Phase 1 production.
    op.execute(
        """
        DELETE FROM tenant_connectors
        WHERE connector_id IN (
            SELECT id FROM connectors
            WHERE slug IN ('calendly', 'google_calendar', 'notion')
        )
        """
    )
    # Same precaution for tool overrides — these reference connector tools,
    # but the FK chain goes via tool_catalog.connector_id (nullable, SET NULL
    # on delete), so they survive automatically when the connector is gone.
    # No explicit cleanup needed here.
    op.execute(
        """
        DELETE FROM connectors
        WHERE slug IN ('calendly', 'google_calendar', 'notion')
        """
    )


def downgrade() -> None:
    """Intentional no-op — see module docstring."""
