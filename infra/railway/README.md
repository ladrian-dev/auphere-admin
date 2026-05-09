# Railway production deployment

Project: **`auphere-nexus`**. Region: `us-east` (closest to CL with
acceptable RTT — see `architecture/deployment.md`).

## Services

The Railway project hosts four services. The first time you set up the
project, create them in this order so the env-var references resolve
cleanly:

1. **`postgres`** — Railway managed Postgres 16. Enable the `pgvector`
   extension from the dashboard (`Database` tab → `Extensions`).
   Apache AGE is **not** available on managed Postgres; the KG is
   modelled relationally per Block B and the migration to AGE is
   deferred to Phase 3+ (per ADR / `PLAN-DE-ACCION.md`).
2. **`redis`** — Railway managed Redis 7.
3. **`nexus-api`** — Docker service. In the service settings:
   - **Source**: GitHub repo, branch `main`.
   - **Root Directory**: repo root (the Dockerfile context is `.`).
   - **Config Path**: `infra/railway/api.toml`.
   - **Custom Domain**: `api.auphere.com` (CNAME target shown by
     Railway after you add the domain).
4. **`nexus-worker`** — Docker service. In the service settings:
   - **Source**: same GitHub repo, branch `main`.
   - **Root Directory**: repo root.
   - **Config Path**: `infra/railway/worker.toml`.
   - **Custom Domain**: none (no HTTP surface).

## Env vars (sourced from Doppler)

Both `nexus-api` and `nexus-worker` need the variables below. The
recommended path is the **Doppler ↔ Railway integration**: Doppler
syncs the `auphere/nexus/production` config into each service's
`Variables` panel automatically; rotating a secret in Doppler triggers
a redeploy.

Mandatory:

| Variable | Source / how to set |
|---|---|
| `NEXUS_ENVIRONMENT` | hardcode `production` |
| `NEXUS_DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (the API's `config.py` normalises `postgresql://` → `postgresql+asyncpg://`) |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (used by `release.sh` + the admin's Drizzle/postgres.js driver) |
| `NEXUS_REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `NEXUS_ADMIN_TOKEN` | Doppler — `openssl rand -hex 32` |
| `NEXUS_WEBHOOK_HMAC_SECRET` | Doppler — `openssl rand -hex 32` |
| `NEXUS_FERNET_KEY` | Doppler — `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` |
| `NEXUS_YCLOUD_API_KEY` | Doppler — copy from YCloud dashboard |
| `NEXUS_YCLOUD_WEBHOOK_SECRET` | Doppler — generate, paste into YCloud dashboard at cutover |
| `NEXUS_OPERATOR_FALLBACK_PHONE` | Doppler — Lee's E.164 |

Worker-only (also accepted by API):

| Variable | Default |
|---|---|
| `NEXUS_LANGFUSE_PUBLIC_KEY` | empty → noop |
| `NEXUS_LANGFUSE_SECRET_KEY` | empty → noop |
| `NEXUS_LANGFUSE_HOST` | `https://cloud.langfuse.com` |
| `NEXUS_LANGFUSE_ENVIRONMENT` | `production` |
| `BROWSERBASE_API_KEY` | empty Phase 1; populated Phase J when the Cultor Barber bootstrap runs |
| `BROWSERBASE_PROJECT_ID` | same |
| `NEXUS_AGENDAPRO_NODE_CMD` | leave default; image bundles `dist/server.js` at the path the Python adapter expects |

## Release command

`infra/railway/api.toml` declares:

```toml
[deploy]
preDeployCommand = "/app/apps/api/scripts/release.sh"
```

That script runs `alembic upgrade head` then applies any new
`apps/admin/drizzle/*.sql` files via psql, tracked by an
`auth.__drizzle_applied(version)` marker table. A non-zero exit
aborts the cutover — the previous revision keeps serving.

## DNS

After creating the `nexus-api` service, add `api.auphere.com` as a
custom domain. Railway shows the CNAME target (something like
`xxx.up.railway.app`). Apply that CNAME in your DNS provider. Cert
provisions automatically (Let's Encrypt) once propagation hits.

## Cost (Phase 1 estimate)

Pro plan + 1× nexus-api (0.5 vCPU / 1 GB) + 1× nexus-worker (1 vCPU /
2 GB) + 1× Postgres + 1× Redis ≈ USD 30–60/month. See
`architecture/deployment.md` for the full table including LLM and
Langfuse spend.

## Branch policy

`main` is the production branch. Phase 1 deploys are **manual** via
the GitHub Actions `deploy` workflow (`workflow_dispatch`). Disable
auto-deploy in each Railway service's settings (`Service Settings →
Source → Auto Deploy: off`). Phase 2 flips this back on once a
second client is onboarded and we have soak time to trust auto.
