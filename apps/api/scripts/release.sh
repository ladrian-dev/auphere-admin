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
#   NEXUS_DATABASE_URL_DIRECT — la base REAL, y la que usa todo lo que corre
#                         aquí. Esta tarea es un ``run-task`` suelto que no
#                         está inscrito en el namespace de Service Connect, así
#                         que el nombre del pooler NO le resuelve. Lo aprendimos
#                         el 2026-10-03 abortando todos los despliegues del día.
#   NEXUS_DATABASE_URL  — tráfico de la aplicación; con PgBouncer delante
#                         apunta al pooler. Aquí solo sirve de respaldo, para
#                         los entornos sin pooler (dev, tests).
#                         Ambas aceptan las formas postgresql:// y
#                         postgresql+asyncpg:// (config.py normaliza).
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
# Block L — apply Connector seed YAMLs. Idempotente. Va a la base DIRECTA,
# igual que Alembic: aquí el nombre del pooler no resuelve.
python /app/apps/api/scripts/seed_connectors.py

echo "release: done"
