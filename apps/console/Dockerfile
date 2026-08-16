# syntax=docker/dockerfile:1.7
#
# Partner console (apps/console) — Next.js 16 standalone image (CP-33).
#
# Build context MUST be the monorepo root (the console lives in the ROOT
# pnpm workspace together with packages/ui):
#
#   docker build -f apps/console/Dockerfile -t nexus-console .
#   docker run -p 3110:3110 --env-file apps/console/.env.local nexus-console
#
# Runtime env (the private key via SSM/Secrets Manager, never baked in):
#   NEXUS_CONSOLE_JWT_PRIVATE_KEY
#   NEXUS_BACKEND_URL  NEXUS_CONSOLE_ORIGIN  (+ NEXUS_META_* optional)
# Health: GET /healthz → {"status":"ok","app":"console"}.
# No database: since ADR-032 identity lives in the API (console_auth.*,
# Alembic 0088). This image opens no Postgres connection and runs no
# migrations of its own.

FROM node:22-alpine AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH NEXT_TELEMETRY_DISABLED=1
RUN corepack enable

# ── deps ────────────────────────────────────────────────────────────────
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/console/package.json apps/console/package.json
COPY packages/ui/package.json packages/ui/package.json
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

# ── build ───────────────────────────────────────────────────────────────
FROM deps AS build
COPY packages/ui packages/ui
COPY apps/console apps/console
# Build-time placeholders: env() is validated lazily at request time, but
# ``next build`` may evaluate route modules that import it.
ENV NEXUS_CONSOLE_JWT_PRIVATE_KEY=build
RUN pnpm --filter console build

# ── runtime ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS runner
ENV NODE_ENV=production PORT=3110 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN addgroup -S nextjs && adduser -S nextjs -G nextjs
COPY --from=build --chown=nextjs:nextjs /repo/apps/console/.next/standalone ./
COPY --from=build --chown=nextjs:nextjs /repo/apps/console/.next/static ./apps/console/.next/static
USER nextjs
EXPOSE 3110
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s CMD wget -qO- http://127.0.0.1:3110/healthz || exit 1
CMD ["node", "apps/console/server.js"]
