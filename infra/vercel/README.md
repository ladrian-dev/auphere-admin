# Vercel production deployment

Project: **`auphere-admin`**. Hosts `apps/admin/` (Next.js 16 App
Router + Better Auth + Drizzle).

## Project setup

In the Vercel dashboard:

1. **Import Git repository** — `auphere/nexus` (or whatever the
   GitHub org/repo name resolves to).
2. **Framework preset**: Next.js (auto-detected).
3. **Root Directory**: `apps/admin`. ← Critical. Without this Vercel
   tries to build the monorepo root and fails.
4. **Install Command**: leave default (`pnpm install --frozen-lockfile`
   is what `vercel.json` declares).
5. **Build Command**: leave default (`pnpm build`).
6. **Output Directory**: leave default (`.next`).
7. **Custom Domain**: `admin.auphere.com`. Vercel will show a CNAME
   target (`cname.vercel-dns.com`) — apply it in your DNS provider.
   Cert provisions automatically.

`apps/admin/vercel.json` ships with the SSE-friendly headers for
`/api/conversations/stream` so Vercel doesn't buffer the upstream
event stream.

## Env vars (sourced from Doppler)

Wire the **Doppler ↔ Vercel integration** to sync
`auphere/nexus/production` into the project's environment. Scope the
sync to **Production** only; Doppler `dev` should not bleed into
preview deployments.

Mandatory:

| Variable | Source / how to set |
|---|---|
| `NEXUS_BACKEND_URL` | `https://api.auphere.com` |
| `NEXUS_ADMIN_TOKEN` | Doppler (same value as Railway) |
| `BETTER_AUTH_SECRET` | Doppler — `openssl rand -hex 32` |
| `BETTER_AUTH_URL` | `https://admin.auphere.com` |
| `DATABASE_URL` | Railway Postgres external URL (postgres.js handles `?sslmode=require` natively) |
| `NEXUS_ADMIN_DATABASE_URL` | same value as `DATABASE_URL` (alias accepted by `drizzle.config.ts`) |
| `NEXUS_BOOTSTRAP_ADMIN_EMAIL` | `lee@auphere.com` (or whichever) |
| `NEXUS_BOOTSTRAP_ADMIN_PASSWORD` | Doppler — change after first login via Better Auth |
| `NEXUS_BOOTSTRAP_ADMIN_NAME` | `Lee` |

Note: `BETTER_AUTH_SECRET` and `NEXUS_ADMIN_TOKEN` MUST match the
values on the Railway side. Doppler is the single source-of-truth so
the sync handles this naturally.

## Bootstrap admin user

After the first successful production deploy, the `auth.user` table
is empty. To create the first admin:

```bash
# From your laptop, with the production DATABASE_URL exported from
# Doppler (one-shot):
cd apps/admin
doppler run --project nexus --config production -- pnpm seed:admin
```

The script (`apps/admin/scripts/seed-admin.ts`) is idempotent — re-runs
recognise the existing email and exit. Phase 2 replaces this with an
invitation flow.

## Branch policy

Phase 1: deploys are **manual** via GitHub Actions `deploy` workflow.
Disable Vercel's GitHub auto-deploy: Project Settings → Git → Production
Branch left as `main`, but switch off "Auto-deploy on push" if Vercel
exposes a toggle (otherwise the manual flow simply takes precedence
because both produce immutable deployments).

Preview deployments per PR are fine and useful — Vercel only treats
them as previews, not as production cutovers.

## SSE / Vercel runtime caveat

The admin's `/api/conversations/stream` route runs on the Node runtime
(not Edge). Vercel **Hobby** caps streaming responses at 5 minutes;
the `LiveIndicator` degrades to polling automatically when the stream
ends. If Auphere is on Vercel **Pro**, the cap is higher; configure
`maxDuration` in the route segment config if you want to push it.

## Vercel CLI from laptop (manual deploy)

```bash
cd apps/admin
vercel pull --environment=production
vercel build --prod
vercel deploy --prebuilt --prod
```

The `deploy.yml` workflow does the same with `VERCEL_TOKEN` /
`VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` repo secrets.
