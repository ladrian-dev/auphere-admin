# Instalación y ejecución

## Requisitos
- Node 22 (probado con 22.11). Node 22.11 no soporta `require()` de ESM, por eso `jsdom` está fijado en 26.
- pnpm 10.15. Si el shim de Corepack falla (`Cannot find matching keyid`): `corepack disable && npm i -g pnpm@10.15.0`.
- Sin Docker, sin base de datos, sin cuentas para desarrollar.

## Arrancar
```bash
cd apps/amacrux-event
cp .env.example .env.local      # por defecto: modo demo + analítica por consola
pnpm install
pnpm dev                        # http://localhost:3120
```

## Verificar
```bash
pnpm check     # lint + typecheck + tests + comprobación de secretos/acoplamiento
pnpm build     # build de producción
pnpm start     # sirve el build en :3120
```

## Estructura
Ver `docs/DECISIONS.md` y `specs/009-diagnostico-evento-amacrux/plan.md` (raíz del repo).

## Workspace
Esta app tiene su propio `pnpm-workspace.yaml` y `pnpm-lock.yaml` (patrón `apps/admin`): no entra en el lockfile ni en el CI raíz del monorepo. Ejecuta siempre `pnpm` desde `apps/amacrux-event`.
