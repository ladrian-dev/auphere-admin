# Nexus — Auphere Agent Factory

> Internal platform that the Auphere team operates to deliver bespoke, isolated AI agents to other businesses as a managed service. Each client gets their own channel, prompt, tools and KG — runtime isolation is a hard requirement, not a feature.

**Knowledge Base (canonical specs and plans):** `/Users/lmatos/Work/Auphere/nexus/`

- Entry point: [PLAN-DE-ACCION](../../Work/Auphere/nexus/PLAN-DE-ACCION.md)
- Active plan: [BUILD-PLAN-v2](../../Work/Auphere/nexus/BUILD-PLAN-v2.md)
- Current state: [nexus-state](../../Work/Auphere/nexus/nexus-state.md)
- Architecture: `architecture/agent-isolation.md`, `architecture/channel-adapters.md`, `architecture/tool-catalog.md`, `architecture/agent-assembly.md`, `architecture/deployment.md`
- First client: [clients/cultor-barber](../../Work/Auphere/nexus/clients/cultor-barber.md)

## Working agreements

- **Spanish for documentation, English for code.** Conventional commits in English.
- **Isolation first.** Any change that could weaken any of the 7 isolation guarantees in `architecture/agent-isolation.md` requires explicit reasoning and a corresponding test in `tests/isolation/`. A red isolation test blocks merge.
- **Bespoke per client.** Verticals (e.g. `barbershop_v1`) are SEED templates, not runtime. Source-of-truth in runtime is `agent_configs.system_prompt_rendered` per tenant.
- **Tool whitelist is exhaustive.** The LangGraph runtime never sees tools outside the active tenant's `agent_config.tools`. No globals.
- **Tenant scoping is automatic.** Repos and tools never accept `tenant_id` from the caller — they pull it from the request context (`SET LOCAL app.tenant_id`).

## Repo layout

```
apps/
  api/             FastAPI backend (Python 3.11, uv)
  worker/          Dramatiq workers (placeholder until block D)
  admin/           Next.js 15 operator panel (placeholder until block G)
  mcp/servers/     One package per MCP server in the catalog
  channels/        ChannelAdapter implementations (whatsapp_ycloud, etc.)
packages/
  shared-types/    Codegen Pydantic → TS
  shared-ui/       shadcn theme + Auphere brand tokens
infra/
  postgres/        Custom Postgres image (AGE + pgvector) for dev
  railway/         Railway service definitions for production
  vercel/          Vercel project config for production
.claude/           Agent definitions, skills, rules
docker-compose.yml Local dev stack
```

## Local development

```bash
# Bring up Postgres + Redis + Mailhog + API
docker compose up -d

# Verify health
curl -s http://localhost:8000/health
# → {"status":"ok"}

# Tail API logs
docker compose logs -f api
```

To work on the API outside Docker:
```bash
cd apps/api
uv sync
uv run uvicorn nexus_api.main:app --reload
```

## Test commands

```bash
# Unit tests (fast)
cd apps/api && uv run pytest tests/unit/ -x

# Isolation suite (blocking on PRs to main)
cd apps/api && uv run pytest tests/isolation/ -x

# Integration tests (need Docker)
cd apps/api && uv run pytest tests/integration/
```

## Branches and deploys

- `main` → production (Railway + Vercel auto-deploy via GitHub Actions).
- `develop` → integration; CI runs but no auto-deploy.
- Feature branches → preview in Vercel.

No `staging` environment in Phase 1. Two environments: dev local + production.

## Status

Phase 1, block A (repo + dev env). See `nexus-state` in the KB for current progress.
