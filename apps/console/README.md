# apps/console — consola de partners (PLAN-CONSOLE-V1)

Next.js 16 (App Router) · `@nexus/ui` · better-auth (esquema `console_auth`) · BFF sin credenciales estáticas.

## Cómo autentica contra la API

```
navegador ── cookie de sesión (__Host-…, HttpOnly, SameSite=Lax)
   ▼
BFF (Server Components / Actions)
   1. auth.api.getSession()                     lib/session.ts
   2. partner_id + rol desde partner_memberships lib/principal.ts
   3. autoriza contra el rol                    can(role, permission)
   4. acuña un JWT EdDSA de 60 s por llamada    lib/jwt.ts → lib/backend.ts
   ▼
API  /console/*  (require_console_principal: firma, caducidad, jti, membership, rol de la BD)
```

No existe el token estático del admin (`NEXUS_ADMIN_…`) en esta app: `pnpm check:no-admin-token` lo verifica en CI.

## Arranque local

```bash
pnpm install                    # en la raíz del monorepo
cd apps/console
cp .env.example .env.local
pnpm keys:generate              # pega la privada aquí y la pública en apps/api/.env
pnpm db:push                    # crea el esquema console_auth
NEXUS_SEED_PARTNER_SLUG=facelad NEXUS_SEED_OWNER_EMAIL=... NEXUS_SEED_OWNER_PASSWORD=... pnpm seed:owner
pnpm dev                        # http://localhost:3110
```

El partner tiene que tener `console_enabled=true` (`partners`, migración 0080) y la API `NEXUS_CONSOLE_ENABLED=true`.

## Rol de base de datos

`NEXUS_CONSOLE_DATABASE_URL` debería usar un rol con: `ALL` sobre el esquema `console_auth`; `SELECT` sobre `public.partner_memberships` y `public.partners`. Nada más — todo lo demás pasa por la API.

## Comprobaciones

```bash
pnpm typecheck && pnpm lint && pnpm test && pnpm check:no-admin-token
```
