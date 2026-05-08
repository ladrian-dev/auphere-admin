# Railway production deployment

Project: `auphere-nexus`. Services configured (block I):

- `nexus-api` (Docker, builds from `apps/api/Dockerfile`)
- `nexus-worker` (Docker, builds from `apps/worker/Dockerfile`)
- `postgres` (managed; pgvector + Apache AGE via custom image — see Phase 0 risk validation in `BUILD-PLAN-v2`)
- `redis` (managed)

Secrets sourced from Doppler (`auphere/production`). Domain: `api.auphere.com` via Cloudflare proxy.

Branch policy: `main` auto-deploys via GitHub Actions; `develop` does not deploy.
