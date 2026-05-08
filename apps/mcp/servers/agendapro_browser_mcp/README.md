# agendapro_browser_mcp

Subprocess MCP server (stdio JSON-RPC) que respalda las 6 internal tools
`agendapro.*` definidas en
`apps/mcp/src/nexus_mcp/servers/agendapro_browser/`. Stack: Node 20+ +
Stagehand v3 + Browserbase Contexts.

Es el **único subprocess MCP server de Phase 1** — los otros 6 servers
del catálogo corren in-process en Python (Bloque D). Decisión
arquitectónica documentada en
[`architecture/mcp-registry.md`](../../../../../Work/Auphere/nexus/architecture/mcp-registry.md).

## Layout

```
src/
  server.ts                 — entry point, MCP stdio loop
  config.ts                 — env vars
  logging.ts                — pino → stderr (gotcha #4)
  schemas.ts                — Zod schemas (espejo de Pydantic Python)
  cache.ts                  — Redis 5min cache (check_availability)
  idempotency.ts            — auphere_<tenant>_<intent_hash>
  screenshot-store.ts       — LocalDisk default; R2 stub para Bloque H
  skyvern_fallback.ts       — TODO Phase 3+
  stagehand/
    session.ts              — BrowserSession abstracción + Browserbase
    login.ts                — login + re-login flow (Stagehand act)
  tools/
    check-availability.ts
    create-appointment.ts
    modify-appointment.ts
    cancel-appointment.ts
    get-today-appointments.ts
    scrape-no-shows.ts
    bootstrap-session.ts    — operator-only
    health-check.ts         — operator-only, re-login auto
tests/                       — vitest
```

## Ciclo dev

```bash
# Install deps (pnpm-lock.yaml committed)
pnpm install

# Dev mode (tsx, no build)
NEXUS_TENANT_ID=<uuid> ./dev.sh

# Build for prod
pnpm run build
node dist/server.js

# Lint + type-check
pnpm run typecheck
pnpm run lint

# Tests (vitest)
pnpm test
```

## Cómo lo invoca el worker Python

El worker Python carga `nexus_mcp.servers.agendapro_browser.transport.build_default_pool_from_env`
al startup. Esto crea un `SubprocessPool` con un `StdioMCPClientFactory`
configurado vía env vars:

```
NEXUS_AGENDAPRO_NODE_CMD     — default: "node apps/mcp/servers/agendapro_browser_mcp/dist/server.js"
NEXUS_AGENDAPRO_NODE_CWD     — opcional
NEXUS_AGENDAPRO_IDLE_S       — idle timeout per-tenant proceso (default 1800s)
```

El pool spawnea un proceso por tenant (lazy), maneja idle eviction y
cierra graceful en SIGTERM.

## Tests

Los tests Python usan un `FakeAgendaProTransport` que matchea la
interfaz `SubprocessTransport` sin spawnear nada. Los tests Node usan
`vitest` con un `BrowserSession` mock — no tocan Stagehand real.

Para validación end-to-end contra una cuenta de pruebas AgendaPro real
(no se corre en CI), ver `tests/integration/agendapro/` con marker
`requires_browserbase`.

## Aislamiento

- **Per-tenant proceso**: 1 proceso Node por tenant. Browserbase context
  es per-tenant; no se comparte. `asyncio.Lock` per-tenant en el adapter
  Python serializa calls del mismo tenant (gotcha context_id).
- **No DB**: el server NO toca Postgres. Todo el side-effect persistente
  (audit_log, tenant_credentials updates) lo hace el adapter Python con
  el contextvar correcto. Ver gotcha "Postgres SET LOCAL ROLE" en
  Bloque E del KB.
- **Stdout exclusive para protocolo**: pino → stderr; Stagehand logs →
  stderr. Cualquier `console.log` rompe el protocolo (lint rule lo
  bloquea).
- **Credentials**: el server NUNCA persiste login/password. Los recibe
  como args en `_bootstrap_session` y `_health_check`, los usa en
  memoria, los descarta al finalizar el call. La persistencia
  encriptada vive en `tenant_credentials.encrypted_payload` (Fernet)
  manejada por el adapter Python.
