"""agent_configs.runtime_skills — per-tenant assignment of Anthropic Skills.

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-23

Fase D of [[claude-platform-integration]]. Each agent_config can now
carry a list of Anthropic Skills (uploaded via the ``/v1/skills`` API)
the runtime should attach to LLM calls. The column is JSONB so we don't
need a separate join table for a v1 with at most a handful of skills
per tenant.

Shape (one element per skill):

    {
        "skill_id": "skill_abc...",   # returned by the upload API
        "version": "latest"           # or a pinned version string
    }

NULL means "no skills attached" — the runtime then skips the
``container`` field and the code_execution tool entirely, behaving
exactly like a pre-Fase D config.

Why JSONB and not a join table:
- Small N per tenant (≤ 5 skills v1).
- Read-once per turn from ``AgentBundle``; no aggregate queries that
  would benefit from a relational layout.
- Versioning lives at the agent_config row level (STAGED→ACTIVE), so
  the skill list is part of the immutable promotion record — pinning
  is by-construction.

No RLS change needed: ``agent_configs`` is already tenant-scoped
(migration 0002) and this is just a new column on the existing table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column(
            "runtime_skills",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "runtime_skills")
