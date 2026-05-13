"""drop AgendaPro admin/credential flow — adopt public-link only (ADR-017)

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-13

Per the post-Phase-1 decision: AgendaPro will only be consumed via its
public booking link (e.g. ``cultorbarber.site.agendapro.com``). The
admin/credential-based browser automation is gone — the agent never
logs into the AgendaPro admin panel again. Cancel / modify / get
appointments are out-of-scope for the public flow and get escalated to
the owner via the backchannel (ADR-018).

Three changes here:

1. Drop the six ``agendapro.*`` internal rows from ``tool_catalog`` that
   the old browser MCP exposed (search_clients, check_availability,
   create_appointment, modify_appointment, cancel_appointment,
   get_appointments). Migration 0009 added them under
   ``status='internal'``; with the MCP server gone they have no
   backing implementation.

2. Delete the ``tenant_credentials`` rows that held the AgendaPro admin
   email + password + browser context. Per the user, no production
   tenants are using this flow. Other integrations (composio toolkits)
   are untouched.

3. Add ``tenants.agendapro_public_url`` (TEXT NULL) so the admin can
   configure the tenant's public AgendaPro link. The new browser MCP
   (future session) reads this when invoking ``booking.check_availability``
   and ``booking.create_appointment``.

Downgrade is best-effort: the tool_catalog rows can be re-seeded by
running migration 0009 again; the credential blobs are gone forever.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_AGENDAPRO_TOOL_NAMES = (
    "agendapro.search_clients",
    "agendapro.check_availability",
    "agendapro.create_appointment",
    "agendapro.modify_appointment",
    "agendapro.cancel_appointment",
    "agendapro.get_appointments",
)


def upgrade() -> None:
    # ── tenants.agendapro_public_url ────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column("agendapro_public_url", sa.Text(), nullable=True),
    )

    # ── drop admin-flow credential rows ─────────────────────────────────────
    op.execute("DELETE FROM tenant_credentials WHERE integration = 'agendapro'")

    # ── drop the 6 internal tool_catalog rows ───────────────────────────────
    # Using parameterized DELETE via raw SQL is fine; the names are literals.
    in_clause = ",".join(f"'{n}'" for n in _AGENDAPRO_TOOL_NAMES)
    op.execute(f"DELETE FROM tool_catalog WHERE name IN ({in_clause})")


def downgrade() -> None:
    op.drop_column("tenants", "agendapro_public_url")
    # The tool_catalog rows are NOT re-seeded here — migration 0009 owns
    # that responsibility. The credential blobs are gone forever; a
    # downgrade can't restore them.
