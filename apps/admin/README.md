# `@auphere/nexus-admin`

Next.js 16 operator panel for the Auphere agent factory. Internal-only;
no client-facing UI.

## Stack

- Next.js 16.2 (App Router, Turbopack)
- React 19.2 + TypeScript strict
- Tailwind 4 with `@theme` reading the brand-system tokens
- shadcn/ui v4 (Base UI variant)
- Sin base de datos: la identidad vive en la API (`/admin/auth/*`, ADR-034)
- React Hook Form + Zod
- pnpm

## Local development

```bash
# 1. Bring up Postgres + Redis
docker compose up -d postgres redis

# 2. Run Alembic migrations (from apps/api)
(cd ../api && uv run alembic upgrade head)

# 3. Alta del primer operador (en la API — aquí ya no hay base de datos)
(cd ../api && python scripts/seed_operator.py \
   --email contacto@auphere.com --display-name "Auphere" --role admin)

# 4. Start the panel
pnpm dev
# → http://localhost:3000
```

The backend (`apps/api`) must be reachable at `NEXUS_BACKEND_URL`
(default `http://localhost:8000`).

## Scripts

| Command          | Notes                                            |
|------------------|--------------------------------------------------|
| `pnpm dev`       | Next dev server with Turbopack hot reload        |
| `pnpm build`     | Production build                                 |
| `pnpm typecheck` | `tsc --noEmit`                                   |
| `pnpm lint`      | ESLint                                           |
| `pnpm test`      | Vitest (jsdom)                                   |
| `pnpm check:no-database` | ADR-034 — falla si el panel recupera una dependencia de Postgres |

## Layout

```
src/
  app/
    (auth)/login/             public — login contra /admin/auth/*
    (dashboard)/              gated by middleware
      layout.tsx              sidebar shell + session check
      tenants/                list
      tenants/[id]/           overview · agent · conversations · integrations · isolation
      tool-catalog/           global read of the tool registry
  components/
    brand/                    Eyebrow · StatusDot · PageHeader · Wordmark
    shell/                    AppSidebar
    ui/                       shadcn primitives
  lib/                        auth · session · backend client · format helpers
```

## Brand

The panel inherits everything from
`Work/Auphere/brand/brand-system.md` with one panel-only override:
`--primary` is **Mountain Meadow** (`#2CC295`) instead of Caribbean
Green. Caribbean is reserved for `--primary-bright` (P1 alerts).

Single radius scale: `0 / 4 / 8 / 999`. Editorial shadows. No
gradients. `prefers-reduced-motion` respected globally.
