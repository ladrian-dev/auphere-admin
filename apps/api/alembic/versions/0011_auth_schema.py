"""Reserve the ``auth`` Postgres schema for Better Auth.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-09

Block G's operator panel uses Better Auth (Drizzle ORM) for sessions and
credentials. Better Auth's tables (user, session, account, verification)
live in a dedicated ``auth`` schema; this migration creates the schema as
an empty namespace, and Drizzle Kit applies the actual table DDL via
``pnpm --filter admin db:generate`` + ``db:push``.

Why two toolchains for one database:

- The application surface (tenants, agent_configs, channels, messages,
  …) is owned by Alembic and lives under ``public``. RLS policies +
  ``nexus_app`` role apply only there.
- The auth surface evolves with Better Auth releases; coupling Alembic
  numbering to its schema would be a coordination tax. Dedicated schema
  keeps the contracts disjoint.
- The single Postgres connection used by FastAPI cannot leak across
  schemas because the application code never references ``auth.*``.

The downgrade drops the schema; if Drizzle has already populated tables
they will be dropped with it (CASCADE), which is the intended teardown
behaviour for a full rollback.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS auth CASCADE")
