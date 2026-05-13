# syntax=docker/dockerfile:1.7
#
# Multi-package monorepo image for the LangGraph runtime worker.
#
# Build context MUST be the project root.
#
# ADR-017 / migration 0021 removed the AgendaPro admin browser MCP that
# used to live as a Node subprocess inside this image. The worker is
# now pure Python — no Node, no Stagehand bundle. When the new
# public-link AgendaPro MCP lands, a node-build stage will be added
# back; until then the image is one stage simpler and noticeably smaller.

# ──────────────────────────────────────────────────────────────────────
# Stage 1 — python-build
#   Resolves the four Python packages (api → channels → mcp → worker)
#   via uv path sources into the system site-packages.
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS python-build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /py-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Order matters: api / channels / mcp don't depend on worker; worker
# depends on all three. Copy each package fully then ``uv pip install``
# the worker, which transitively installs the other three from the
# editable path sources declared in ``apps/worker/pyproject.toml``.
COPY apps/api/pyproject.toml /py-build/apps/api/pyproject.toml
COPY apps/api/src /py-build/apps/api/src
COPY apps/api/alembic.ini /py-build/apps/api/alembic.ini
COPY apps/api/alembic /py-build/apps/api/alembic

COPY apps/channels/pyproject.toml /py-build/apps/channels/pyproject.toml
COPY apps/channels/src /py-build/apps/channels/src

COPY apps/mcp/pyproject.toml /py-build/apps/mcp/pyproject.toml
COPY apps/mcp/src /py-build/apps/mcp/src

COPY apps/worker/pyproject.toml /py-build/apps/worker/pyproject.toml
COPY apps/worker/src /py-build/apps/worker/src

WORKDIR /py-build/apps/worker
RUN uv pip install --system --no-cache-dir .

# ──────────────────────────────────────────────────────────────────────
# Stage 2 — runtime
#   Slim Python runtime + non-root user. No build tooling, no Node.
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NEXUS_ENVIRONMENT=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 nexus \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /usr/sbin/nologin nexus

# Python deps + console scripts.
COPY --from=python-build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-build /usr/local/bin /usr/local/bin

# Python source layout — Alembic + scripts read off ``apps/api`` paths.
COPY --from=python-build /py-build/apps /app/apps

WORKDIR /app

ENV PYTHONPATH=/app/apps/api/src:/app/apps/channels/src:/app/apps/mcp/src:/app/apps/worker/src

USER nexus

# No HTTP healthcheck — the worker is a daemon. Railway monitors process
# liveness via boot stability ("successful boot for N seconds"). Add a
# CMD process check here if a different orchestrator needs one.

CMD ["nexus-worker"]
