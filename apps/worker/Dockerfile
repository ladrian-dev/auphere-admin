# syntax=docker/dockerfile:1.7
#
# Multi-package monorepo image for the LangGraph runtime worker.
#
# Build context MUST be the project root.
#
# The worker spawns the Stagehand-driven AgendaPro server as a Node
# subprocess (per-tenant, lazy). The Node bundle therefore has to live
# inside this image at
#   /app/apps/mcp/servers/agendapro_browser_mcp/dist/server.js
# with its runtime ``node_modules`` next to it (Stagehand + Browserbase
# SDK + MCP SDK + ioredis + pino). The default spawn command in
# ``nexus_mcp.servers.agendapro_browser.transport`` is
#   ``node apps/mcp/servers/agendapro_browser_mcp/dist/server.js``
# resolved from the worker's WORKDIR (``/app``).

# ──────────────────────────────────────────────────────────────────────
# Stage 1 — node-build
#   Compiles the AgendaPro MCP server (TS → dist) and installs production
#   node_modules. Built off node:22 because pnpm 11.0.9 requires Node
#   v22.13+ when activated via corepack (pnpm/action-setup@v4 in CI is
#   more lenient, but corepack here is strict — see Railway deploy log
#   "ERR_UNKNOWN_BUILTIN_MODULE node:sqlite" before the bump).
# ──────────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS node-build

ENV PNPM_HOME=/usr/local/pnpm \
    PATH=/usr/local/pnpm:$PATH

RUN corepack enable && corepack prepare pnpm@11.0.9 --activate

WORKDIR /node-build

COPY apps/mcp/servers/agendapro_browser_mcp/package.json /node-build/package.json
COPY apps/mcp/servers/agendapro_browser_mcp/pnpm-lock.yaml /node-build/pnpm-lock.yaml
COPY apps/mcp/servers/agendapro_browser_mcp/tsconfig.json /node-build/tsconfig.json
COPY apps/mcp/servers/agendapro_browser_mcp/src /node-build/src

# Full install with build-script approval (Stagehand pulls esbuild +
# protobufjs which require post-install scripts to materialise their
# binaries). Block I locks the approved list in package.json under
# ``pnpm.onlyBuiltDependencies``.
RUN pnpm install --frozen-lockfile --config.confirmModulesPurge=false \
    && ./node_modules/.bin/tsc \
    && pnpm prune --prod

# ──────────────────────────────────────────────────────────────────────
# Stage 2 — python-build
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
# Stage 3 — runtime
#   Slim Python + Node runtime + non-root user. No build tooling.
# ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    NEXUS_ENVIRONMENT=production

# Pull just the Node binary from the official slim image — keeps us off
# Debian's old Node and avoids pulling npm/yarn/etc. into the runtime.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node

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

# Node runtime artefacts: dist/ + production node_modules + package.json
# under the path the SubprocessPool defaults expect.
COPY --from=node-build /node-build/dist \
     /app/apps/mcp/servers/agendapro_browser_mcp/dist
COPY --from=node-build /node-build/node_modules \
     /app/apps/mcp/servers/agendapro_browser_mcp/node_modules
COPY --from=node-build /node-build/package.json \
     /app/apps/mcp/servers/agendapro_browser_mcp/package.json

WORKDIR /app

ENV PYTHONPATH=/app/apps/api/src:/app/apps/channels/src:/app/apps/mcp/src:/app/apps/worker/src

USER nexus

# No HTTP healthcheck — the worker is a daemon. Railway monitors process
# liveness via boot stability ("successful boot for N seconds"). Add a
# CMD process check here if a different orchestrator needs one.

CMD ["nexus-worker"]
