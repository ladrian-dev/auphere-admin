"""agent_configs runtime flags — per-config booleans for memory / grader / mcp.

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-23

Moves the per-tenant feature flags out of env vars
(``NEXUS_MEMORY_TOOL_ENABLED_TENANTS``, ``NEXUS_OUTCOME_GRADER_ENABLED_TENANTS``,
``NEXUS_MCP_CONNECTOR_ENABLED_TENANTS``) into columns on ``agent_configs``.

Why:
- Feature flags per-tenant belong with the config itself, not in a
  CSV the operator has to keep in sync with the DB.
- The STAGED → ACTIVE flow already governs config changes; activating
  a feature should ride the same atomic promotion path (rollback comes
  for free).
- ``audit_log`` records every UPDATE on agent_configs, so we keep a
  history of who/when each feature was turned on for a given config.
- Admin UI gets three obvious toggles instead of a Railway env editor.

Default ``false`` on every existing row → backward compatible: a tenant
whose ACTIVE config predates this migration sees zero behavioural
change. To activate a feature the operator stages a new config with
the flag set and promotes.

The Fase A context-editing flag (``NEXUS_CONTEXT_EDITING_ENABLED``) stays
in env because it's a GLOBAL kill switch on the provider, not a
per-tenant choice. Same for the Langfuse credentials.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column(
            "runtime_memory_tool",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "runtime_outcome_grader",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "runtime_mcp_connector",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "runtime_mcp_connector")
    op.drop_column("agent_configs", "runtime_outcome_grader")
    op.drop_column("agent_configs", "runtime_memory_tool")
