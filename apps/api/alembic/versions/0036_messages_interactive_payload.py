"""messages.interactive_payload + seed response.send_interactive tool

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-24

Closes the WhatsApp-native-components gap (see ``Auphere/nexus/sessions/
2026-05-24-whatsapp-interactive-components.md``). Two changes:

- ``messages.interactive_payload`` — new JSONB column, nullable. Carries
  the validated args of a ``response.send_interactive`` tool call
  (body / header / footer / one of buttons / list / cta_url). The
  outbound dispatcher routes any row with a non-NULL payload through
  ``adapter.send_interactive`` instead of ``send_text``. The column is
  nullable + defaults to NULL — every existing row keeps working
  exactly as before. No index: lookups go via ``status = 'pending'``
  and that index already exists.

- ``tool_catalog`` seed for ``response.send_interactive`` — registers
  the new MCP tool so the operator panel can show it in the
  whitelist editor and the runtime can dispatch it. The tool lives in
  ``notification-server`` (same package as ``send_image`` &c.) so it
  shares the 24h-window enforcement and the ``sends_message`` side
  effect tag. Idempotent on the tool name.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TOOL_DESCRIPTION = (
    "Emit a native WhatsApp interactive component (reply buttons, list, "
    "or CTA URL) as the response to the user. Exactly ONE of buttons "
    "(1–3 reply buttons), list (1–10 selectable items), or cta_url "
    "(single URL-opening button) must be set. Terminal action of the "
    "turn — the agent does not call more tools after this one. If the "
    "agent ALSO produces a preceding text answer in the same response, "
    "both are sent in order (text first, then the interactive). The "
    "24h customer-service window is enforced server-side; outside the "
    "window use notification.send_template instead. See the "
    "whatsapp-native-components skill for when to use which component "
    "vs plain text."
)


def upgrade() -> None:
    # ── messages.interactive_payload ──────────────────────────────────
    op.add_column(
        "messages",
        sa.Column(
            "interactive_payload",
            postgresql.JSONB,
            nullable=True,
        ),
    )

    # ── tool_catalog seed ────────────────────────────────────────────
    # Idempotent INSERT. ``mcp_server`` matches the existing notification
    # tools so the registry resolves it via the same import path.
    op.execute(
        f"""
        INSERT INTO tool_catalog (
            name, description, mcp_server,
            input_schema, output_schema,
            side_effects, capability_tags, cost_estimate,
            read_only, destructive, requires_consent, default_mode,
            status
        ) VALUES (
            'response.send_interactive',
            '{_TOOL_DESCRIPTION.replace("'", "''")}',
            'notification-server',
            '{{}}'::jsonb,
            '{{}}'::jsonb,
            ARRAY['sends_message']::varchar[],
            ARRAY['whatsapp', 'outbound', 'interactive']::varchar[],
            '{{}}'::jsonb,
            false,
            true,
            false,
            'always',
            'active'
        )
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM tool_catalog WHERE name = 'response.send_interactive'"
    )
    op.drop_column("messages", "interactive_payload")
