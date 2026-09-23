# apps/console — consola de partners (PLAN-CONSOLE-V1)

Next.js 16 (App Router) · `@nexus/ui` · **BFF sin base de datos y sin credenciales estáticas**.

## La consola no habla con Postgres

Hasta ADR-032 esta app tenía su propia base: better-auth + Drizzle sobre el
esquema `console_auth`, y `lib/principal.ts` consultaba
`public.partner_memberships` por SQL. Eso obligaba a que Vercel alcanzara la
Postgres, y la Aurora de producción es privada
(`infra/terraform/10-data/aurora.tf`).

Ahora la identidad —usuarios, contraseñas y sesiones— vive en la API
(`console_auth.principals`, migración `0088`) y aquí solo queda una cookie
con un **token opaco**. Esta app no tiene ninguna variable de conexión a
Postgres, y ese es exactamente el punto.

## Cómo autentica contra la API

```
navegador ── cookie nexus-console.session (HttpOnly, SameSite=Lax, 7 días)
   ▼
BFF (Server Components / Actions)
   1. POST /console/auth/session {token}         lib/session.ts + lib/principal.ts
      → principal: partner, rol, permisos, access
   2. autoriza contra el rol                     can(role, permission)
   3. acuña un JWT EdDSA de 60 s por llamada     lib/jwt.ts → lib/backend.ts
   ▼
API  /console/*  (require_console_principal: firma, caducidad, jti, membership, rol de la BD)
```

Las tres llamadas pre-sesión (`/console/auth/login`, `/console/auth/session`,
`/console/auth/logout`) y las dos de invitación van con el **token de
servicio** del BFF (`svc: "console"`). El navegador nunca las llama.

No existe el token estático del admin (`NEXUS_ADMIN_…`) en esta app:
`pnpm check:no-admin-token` lo verifica en CI.

## Arranque local

```bash
pnpm install                    # en la raíz del monorepo
cd apps/console
cp .env.example .env.local
pnpm keys:generate              # pega la privada aquí y la pública en apps/api/.env
pnpm dev                        # http://localhost:3110
```

Para tener con quién entrar, siembra el owner **desde la API**:

```bash
cd ../api
NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus \
  uv run python scripts/seed_console_memberships.py \
  --partner-slug demo --owner-email owner@demo.test \
  --enable-console --set-password 'una-contraseña-de-12+'
```

El partner tiene que tener `console_enabled=true` (`partners`, migración
0080) y la API `NEXUS_CONSOLE_ENABLED=true`.

## Alta de un partner piloto

`apps/api/scripts/seed_console_memberships.py --partner-slug <slug>
--owner-email <correo> --enable-console` emite la invitación de owner e
imprime el enlace `/invite/<token>`; quien lo abre elige contraseña y entra
(runbook: `apps/api/RUNBOOK.md` → "Consola: alta de partner piloto").
`--set-password` salta la invitación y crea la cuenta directamente — solo
para desarrollo y para el piloto.

## Despliegue

`apps/console/Dockerfile` (Next `output: "standalone"`, puerto 3110, health
`GET /healthz`). Secreto único: `NEXUS_CONSOLE_JWT_PRIVATE_KEY`. Config:
`NEXUS_BACKEND_URL`, `NEXUS_CONSOLE_ORIGIN`, y los `NEXUS_META_*` de
Embedded Signup. Ver `infra/README-console.md`.

## Comprobaciones

```bash
pnpm typecheck && pnpm lint && pnpm test && pnpm check:no-admin-token
pnpm build
# accesibilidad + responsive sobre la app real (API y consola arriba)
pnpm exec playwright install chromium        # una vez por máquina
E2E_EMAIL=... E2E_PASSWORD=... pnpm test:e2e
```

Vite 8 / rolldown exigen **Node ≥ 22.12** (`require(esm)`). Con un Node 22.11
`pnpm test` arranca con `NODE_OPTIONS=--experimental-require-module`; mejor
subir Node. En macOS no existe `timeout`: no lo uses en scripts locales.

### Probar una acción de servidor

Cada acción hace tres cosas: resuelve el principal, comprueba el rol y llama
al backend. El arnés `src/test/actions.ts` finge la primera y la tercera para
que el test afirme la segunda — el «no puedes» de la consola, no el 403 de la
API — y lo que se le pidió al backend:

```ts
const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);
const { saveAllocationAction } = await import("../actions");

h.setRole("analyst");
expect(await saveAllocationAction({ client_ref: "a", cap: 1 })).toEqual(h.denied());
expect(h.backend.setAllocation).not.toHaveBeenCalled();
```

`h.backend.<método>` es un `vi.fn` que existe sin declararlo y resuelve `{}`;
`h.fail("método", 422, "detalle", "código")` hace fallar la siguiente llamada
como la vería `run()`. Un fichero `__tests__/actions.test.ts` por carpeta de
acciones (spec 016, R8).

La suite `companion.spec.ts` se **salta** (no falla) si el partner de prueba
no tiene `companion_enabled`; la `a11y.spec.ts` exige un cliente ya creado.
