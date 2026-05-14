# syntax=docker/dockerfile:1.7
#
# Multi-package monorepo image for the LangGraph runtime worker.
#
# Build context MUST be the project root.
#
# Block O (ADR-017): re-introduces a Node stage that compiles the
# ``agendapro_public_mcp`` server. The worker's Python booking facade
# + async_booking_cron spawn it via stdio JSON-RPC to drive the
# AgendaPro public link wizard. Node + the compiled dist + production
# node_modules ship inside the runtime image.

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
# Stage 2 — node-build
#   Compiles the agendapro_public_mcp TypeScript server and prunes
#   to production-only node_modules.
#
#   Cache strategy: COPY package.json first, install, THEN COPY src.
#   When only src changes (most common case while iterating on the
#   wizard flows), npm install hits cache and only ``tsc`` re-runs.
# ──────────────────────────────────────────────────────────────────────
FROM node:22-slim AS node-build

WORKDIR /node-build

COPY apps/mcp/servers/agendapro_public_mcp/package.json ./package.json
COPY apps/mcp/servers/agendapro_public_mcp/tsconfig.json ./tsconfig.json
# Copy lockfile when present (post-first-build); not strictly required
# for the COPY to succeed because Docker fails only on missing required
# files, but the conditional shape keeps repeat builds reproducible.
COPY apps/mcp/servers/agendapro_public_mcp/package-loc[k].json ./

# Install ALL deps (incl. devDeps for tsc / @types/node). ``npm ci`` is
# preferred when a lockfile exists; falls back to ``npm install``
# automatically if there isn't one (npm's default behaviour).
RUN if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund; \
    else \
        npm install --no-audit --no-fund; \
    fi

# Now bring the source over and compile.
COPY apps/mcp/servers/agendapro_public_mcp/src ./src
RUN npx tsc -p tsconfig.json \
    && ls -la dist/

# Prune devDeps so only what the runtime needs ships forward.
RUN npm prune --omit=dev

# ──────────────────────────────────────────────────────────────────────
# Stage 3 — runtime
#   Slim Python runtime + Node 22 binary + non-root user.
#   Stagehand uses Browserbase remote browsers (``env=BROWSERBASE``) so
#   no local Chromium/Playwright deps are needed — keeps the image
#   reasonable (~400MB vs ~1.2GB if we shipped Playwright).
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NEXUS_ENVIRONMENT=production

# Bring just the Node binary (no npm — the production image doesn't
# install packages at runtime; node_modules is baked in already).
COPY --from=node-build /usr/local/bin/node /usr/local/bin/node
# Node ships with ICU/SSL libs already statically built into the binary
# on the official images, so no extra apt deps needed for the basic
# stagehand+http use case.

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

# Compiled MCP server + production node_modules at the path the
# Python transport defaults to: ``node apps/mcp/servers/agendapro_public_mcp/dist/server.js``.
# Override via NEXUS_AGENDAPRO_PUBLIC_NODE_CMD if needed.
COPY --from=node-build /node-build/dist /app/apps/mcp/servers/agendapro_public_mcp/dist
COPY --from=node-build /node-build/node_modules /app/apps/mcp/servers/agendapro_public_mcp/node_modules
COPY --from=node-build /node-build/package.json /app/apps/mcp/servers/agendapro_public_mcp/package.json

# Ownership for the non-root user.
RUN chown -R nexus:nexus /app/apps/mcp/servers/agendapro_public_mcp

WORKDIR /app

ENV PYTHONPATH=/app/apps/api/src:/app/apps/channels/src:/app/apps/mcp/src:/app/apps/worker/src
# The Python transport spawns ``node /app/apps/mcp/servers/agendapro_public_mcp/dist/server.js``
# — keep cwd consistent so relative ``import`` paths resolve.
ENV NEXUS_AGENDAPRO_PUBLIC_NODE_CMD="node /app/apps/mcp/servers/agendapro_public_mcp/dist/server.js"
ENV NEXUS_AGENDAPRO_PUBLIC_NODE_CWD="/app/apps/mcp/servers/agendapro_public_mcp"

USER nexus

# No HTTP healthcheck — the worker is a daemon. Railway monitors process
# liveness via boot stability ("successful boot for N seconds"). Add a
# CMD process check here if a different orchestrator needs one.

CMD ["nexus-worker"]
