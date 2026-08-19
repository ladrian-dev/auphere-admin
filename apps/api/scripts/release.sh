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
#   2. Sembrar el catálogo de conectores (idempotente).
#
# Env vars:
#   NEXUS_DATABASE_URL  — read by Alembic via ``nexus_api.config``.
#                         Accepts postgresql:// or postgresql+asyncpg://
#                         forms (config.py normalises).
#
# Block I delivery. See apps/api/RUNBOOK.md for failure handling.

set -euo pipefail

cd /app/apps/api

echo "release: alembic upgrade head"
alembic upgrade head

# ADR-034: aquí iba la etapa de Drizzle (aplicar ``apps/admin/drizzle/*.sql``
# y llevar la cuenta en ``auth.__drizzle_applied``). Se ha ido con Better
# Auth: la identidad del panel vive ahora en ``operator_auth``, que es una
# migración de Alembic como cualquier otra. El esquema ``auth`` y su tabla
# de marcas se quedan donde están —no estorban y son el registro de qué
# hubo— pero ya no los toca nadie.

echo "release: seeding connectors catalog"
# Block L — apply Connector seed YAMLs. Idempotent. Reads NEXUS_DATABASE_URL.
python /app/apps/api/scripts/seed_connectors.py

echo "release: done"
