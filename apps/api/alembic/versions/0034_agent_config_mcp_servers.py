"""agent_configs.runtime_mcp_servers — per-tenant Anthropic MCP connector config.

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-23

Fase E of [[claude-platform-integration]]. Each agent_config can carry
a list of MCP servers the runtime should attach via Anthropic's MCP
connector beta (``mcp-client-2025-11-20``). This is the *exploratory*
phase of the plan — Composio remains the SoT for OAuth credentials,
and this column lets the runtime consume them via MCP nativo on a
per-config basis to compare against the Composio runtime proxy.

Shape (one element per server):

    {
        "name": "linear",                      # short, lowercase, used as id
        "url": "https://mcp.linear.app/mcp",   # MCP endpoint URL
        "allowed_tools": ["list_issues",       # whitelist of tool names
                          "create_issue"],
        "credential_key": "linear_oauth"       # row in tenant_credentials
    }                                          # (resolved per turn)

NULL = "no MCP servers attached" — the runtime skips the ``mcp_servers``
kwarg + the beta header entirely. The handler can then run faster (one
fewer Anthropic-side resolution per turn) and the call shape is
identical to pre-Fase E.

Tabla NOT changed otherwise — agent_configs already has RLS (migration
0002) and FK cascade to tenants (migration 0030).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column(
            "runtime_mcp_servers",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "runtime_mcp_servers")
