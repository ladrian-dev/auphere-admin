# syntax=docker/dockerfile:1.7
#
# Multi-package monorepo image for the LangGraph runtime worker.
#
# Build context MUST be the project root.
#
# Python only. Spec 048 removed the Node stage (a browser MCP for a third-party
# booking page, driven over stdio) together with the server it compiled.

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
    && pip install --no-cache-dir uv==0.13.4

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

# ADR-020 Fase 2 introduced ``nexus-ucm-schema`` as a path dep of
# nexus-worker (the ``ucm_formatter`` node lives in the worker pipeline).
# The package source lives OUTSIDE apps/, so it needs an explicit COPY —
# missing it manifests as ``Distribution not found at:
# file:///py-build/packages/ucm-schema/py`` at uv pip install time.
COPY packages/ucm-schema/py /py-build/packages/ucm-schema/py

COPY apps/worker/pyproject.toml /py-build/apps/worker/pyproject.toml
COPY apps/worker/uv.lock /py-build/apps/worker/uv.lock
COPY apps/worker/src /py-build/apps/worker/src

WORKDIR /py-build/apps/worker
# ``--no-editable`` forces path-source deps (nexus-api, nexus-mcp,
# nexus-channels, nexus-ucm-schema) to install as regular wheels in
# site-packages instead of ``.pth`` pointers back to /py-build/...
# Otherwise the runtime stage can't find them after we strip /py-build.
# Same pattern as ``apps/api/Dockerfile``.
# Versions come from ``uv.lock``, not from a fresh resolution — see the
# same step in ``apps/api/Dockerfile`` for why.
RUN uv export --locked --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
    && uv pip install --system --no-cache-dir --no-editable -r /tmp/requirements.txt \
    && uv pip install --system --no-cache-dir --no-editable --no-deps .
# Fail the build if the LiteLLM installed crashes on any call with tools
# (1.106.0 did, needing ``mcp``, and every agent turn died). Local call to
# a closed port.
RUN python -m nexus_api.core.litellm_smoke

# ──────────────────────────────────────────────────────────────────────
# Stage 2 — runtime
#   Slim Python runtime + non-root user.
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
# ucm-schema lives outside /apps; the editable install was forced to
# wheel via --no-editable above, but mirror /packages here as a
# safety net so any direct path import still resolves at runtime.
COPY --from=python-build /py-build/packages /app/packages

WORKDIR /app

ENV PYTHONPATH=/app/apps/api/src:/app/apps/channels/src:/app/apps/mcp/src:/app/apps/worker/src:/app/packages/ucm-schema/py/src

USER nexus

# No HTTP healthcheck — the worker is a daemon. Railway monitors process
# liveness via boot stability ("successful boot for N seconds"). Add a
# CMD process check here if a different orchestrator needs one.

CMD ["nexus-worker"]
