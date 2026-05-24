# syntax=docker/dockerfile:1.7
#
# Multi-package monorepo image for the FastAPI backend.
#
# Build context MUST be the project root (``docker-compose.yml`` already
# sets ``context: .`` and ``dockerfile: apps/api/Dockerfile``; Railway
# uses the same root via ``railway.toml``).
#
# Block F made ``apps/api`` depend on ``apps/channels`` for the YCloud
# webhook adapter. Block I bundles ``apps/admin/drizzle/*.sql`` so the
# Railway release command can apply the auth-schema migration alongside
# Alembic without needing the admin image to be reachable.

# ──────────────────────────────────────────────────────────────────────
# Stage 1 — builder
#   Installs uv + project sources + resolves the editable path sources
#   into ``/install``. Layers are ordered so dependency-only changes
#   invalidate as little as possible.
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Copy each package's pyproject + src so uv can resolve the editable
# path sources. Dependency order:
#  - leaf packages first (nexus-channels, nexus-ucm-schema, nexus-mcp,
#    nexus-worker — these have no inter-deps on nexus-api),
#  - then nexus-api itself which path-depends on the four above.
COPY apps/channels/pyproject.toml /build/apps/channels/pyproject.toml
COPY apps/channels/src /build/apps/channels/src

# ADR-020 Fase 5 closure: the QA Playground runs the agent graph
# in-process from nexus-api, so the worker / mcp / ucm-schema packages
# need to land in the production image too (they were dev-only before).
COPY packages/ucm-schema/py /build/packages/ucm-schema/py
COPY apps/mcp/pyproject.toml /build/apps/mcp/pyproject.toml
COPY apps/mcp/src /build/apps/mcp/src
COPY apps/worker/pyproject.toml /build/apps/worker/pyproject.toml
COPY apps/worker/src /build/apps/worker/src
# The admin's ``/admin/skills/available`` endpoint reads SKILL.md
# frontmatter from this directory at request time so the operator's
# skill picker shows real metadata (name, description, version) for
# each bundled skill. Without this layer the endpoint returns ``[]``
# and the picker renders "No hay Anthropic Skills bundleadas en este
# deploy" even though the skills exist in Anthropic's workspace.
COPY apps/worker/skills /build/apps/worker/skills

COPY apps/api/pyproject.toml /build/apps/api/pyproject.toml
COPY apps/api/src /build/apps/api/src
COPY apps/api/alembic.ini /build/apps/api/alembic.ini
COPY apps/api/alembic /build/apps/api/alembic
COPY apps/api/scripts /build/apps/api/scripts

# Drizzle SQL migrations live alongside the API image so the Railway
# release command can run them. Block G owns the schema; the API
# release command applies them after Alembic head.
COPY apps/admin/drizzle /build/apps/admin/drizzle

WORKDIR /build/apps/api
# ``--no-editable`` forces the path-source deps (nexus-worker, nexus-mcp,
# nexus-ucm-schema, nexus-channels) to be installed as regular wheels
# into ``site-packages``, NOT as ``.pth`` pointers back to /build/...
# Otherwise the runtime stage can't find them after stripping /build.
RUN uv pip install --system --no-cache-dir --no-editable .

# ──────────────────────────────────────────────────────────────────────
# Stage 2 — runtime
#   Slim image, non-root user, ``psql`` for release commands.
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NEXUS_ENVIRONMENT=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 nexus \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /usr/sbin/nologin nexus

# Copy installed site-packages + console scripts from the builder.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Application source — the package is installed via ``uv pip install``
# above, but Alembic + scripts read paths off ``apps/api`` directly.
# ucm-schema lives outside /apps; the editable install in the builder
# stage points at /build/packages, so we must mirror that path in the
# runtime stage or the import fails at first use.
COPY --from=builder /build/apps /app/apps
COPY --from=builder /build/packages /app/packages

WORKDIR /app/apps/api

ENV PYTHONPATH=/app/apps/api/src:/app/apps/channels/src:/app/apps/worker/src:/app/apps/mcp/src:/app/packages/ucm-schema/py/src
ENV PATH=/usr/local/bin:$PATH

USER nexus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --silent --fail http://127.0.0.1:8000/health/live || exit 1

CMD ["uvicorn", "nexus_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
