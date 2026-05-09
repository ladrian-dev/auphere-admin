#!/usr/bin/env bash
#
# Railway release command for the ``nexus-api`` service.
#
# Runs once per deploy, BEFORE the web service rolls. A non-zero exit
# aborts the cutover — the previous revision keeps serving traffic. So
# this script must be safe to re-run on the same database (idempotent)
# and fail loudly on real problems.
#
# Steps:
#   1. ``alembic upgrade head`` — owns the application's ``public``
#      schema and creates the ``auth`` namespace (migration 0011).
#   2. Apply each ``apps/admin/drizzle/*.sql`` file, tracked by
#      ``auth.__drizzle_applied(version)``. drizzle-kit doesn't
#      generate a migration tracker of its own; this is the smallest
#      thing that gives us idempotent re-runs without parsing the SQL.
#
# Env vars:
#   NEXUS_DATABASE_URL  — read by Alembic via ``nexus_api.config``.
#                         Accepts postgresql:// or postgresql+asyncpg://
#                         forms (config.py normalises).
#   DATABASE_URL        — read by psql for the Drizzle step. Railway's
#                         Postgres add-on exposes this directly.
#
# Block I delivery. See apps/api/RUNBOOK.md for failure handling.

set -euo pipefail

cd /app/apps/api

echo "release: alembic upgrade head"
alembic upgrade head

if [ -z "${DATABASE_URL:-}" ]; then
  echo "release: DATABASE_URL is not set — skipping Drizzle stage"
  echo "release: ERROR — Vercel/Railway must inject DATABASE_URL for psql"
  exit 1
fi

DRIZZLE_DIR="/app/apps/admin/drizzle"

echo "release: ensuring auth.__drizzle_applied marker table"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c "
  CREATE TABLE IF NOT EXISTS auth.__drizzle_applied (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
  );
"

# ``shopt -s nullglob`` so an empty drizzle/ directory is a no-op
# instead of literally trying to apply ``*.sql``.
shopt -s nullglob
for sql in "$DRIZZLE_DIR"/*.sql; do
  version="$(basename "$sql" .sql)"
  applied="$(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc \
    "SELECT 1 FROM auth.__drizzle_applied WHERE version = '${version}'")"
  if [ "$applied" = "1" ]; then
    echo "release: drizzle ${version} — already applied"
    continue
  fi
  echo "release: drizzle ${version} — applying"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$sql"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
    "INSERT INTO auth.__drizzle_applied (version) VALUES ('${version}');"
done

echo "release: done"
