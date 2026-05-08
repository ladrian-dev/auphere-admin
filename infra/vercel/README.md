# Vercel production deployment

Project: `auphere-admin`. Deploys `apps/admin/` (Next.js 15 App Router).

- Production domain: `admin.auphere.com`
- Preview deployments per PR.
- Env vars sourced from Doppler integration (`auphere/production` for `main`, `auphere/dev` for previews if applicable).

Configured in block I.
