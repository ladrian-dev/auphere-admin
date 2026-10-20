# Implementation Plan: el panel de Auphere se ordena

**Branch**: `031-el-panel-se-ordena` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: `specs/031-el-panel-se-ordena/spec.md` · línea base de diseño en [research.md](research.md) · referencia Chatwoot (`/Users/matos/workspace/chatwoot`)

## Summary

El panel de operador (`apps/admin`) deja sus copias de shadcn y sus tokens hex y pasa a
consumir `@nexus/ui` como la consola: entra al workspace raíz de pnpm, importa
`@nexus/ui/tokens.css`, monta `ThemeProvider` + `UiCopyProvider` y usa Inter. Sobre esa
base se reconstruye el shell (sidebar agrupado a la Chatwoot, barra con paleta ⌘K y menú
con tema), se añade un **Panel** de inicio y una vista de **Estado**, y se rehacen los
listados y las fichas de partner y cliente con cabecera de hechos y pestañas ordenadas.
La API gana tres lecturas (`/admin/overview`, `/admin/partners/{id}/members`, conteos y
flags en `PartnerOut`) y una escritura (`billing_email` en `PartnerUpdateIn`).

Orden, para que cada diff sea revisable y la app funcione después de cada paso:

1. **Workspace** — el panel entra al workspace raíz sin tocar código (verde en build).
2. **Tokens** — `globals.css` de la consola, fuente Inter, providers.
3. **Primitivas** — imports a `@nexus/ui`, se borran las copias.
4. **Colores y medios pasos** — utilidades de token, lint `@nexus/ui/eslint`.
5. **Shell** — nav agrupado, barra superior, menú con tema, paleta.
6. **API** — overview, members, `PartnerOut` ampliado, `billing_email` editable.
7. **Panel y Estado**.
8. **Partners** — listado + ficha con pestañas nuevas y redirecciones de las antiguas.
9. **Clientes** — listado con partner y filtros, cabecera, sub-pestañas de Agente.

## Technical Context

**Language/Version**: Python 3.14 (API) · TypeScript 5 / Next.js 16.2 / React 19.2
**Primary Dependencies**: FastAPI · SQLAlchemy async (ya instalados) · `@nexus/ui` (workspace, ya existe) — **ninguna dependencia nueva de terceros**
**Storage**: Postgres; sin migraciones (todo son lecturas de columnas existentes)
**Testing**: pytest (`apps/api/tests/unit`) · vitest (`apps/admin`)
**Target Platform**: Vercel (panel) · ECS (API)
**Constraints**: lint `@nexus/ui/eslint` sin avisos · español · claro/oscuro · 390 px sin desbordes
**Scale/Scope**: decenas de partners, cientos de clientes

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto | ☑ | Ninguna ruta nueva acepta `tenant_id`/`partner_id` en el cuerpo. Las lecturas de tablas FORCE por partner (`partner_wallets`, `partner_allocations`) fijan el GUC del partner que se está leyendo, uno por uno (`apply_partner_to_session`), igual que `api/admin/partner_wallet.py`. `partner_memberships`/`partner_invitations` no llevan RLS (plataforma, ver `tests/isolation/test_21…`). Test: `unit/test_admin_overview.py` comprueba que el saldo total es la suma de cada partner leído con su GUC |
| II | Corte por superficie | ☑ | Superficie `0`, ya abierta |
| III | Lo leído es dato | ☑ | No hay agente ni contenido leído en esta spec |
| IV | Acción `mutates` auditada con persona | ☑ | La única escritura nueva (`billing_email`) pasa por `PATCH /admin/partners/{id}`, que ya escribe auditoría con antes/después. Actor: hoy `admin:<token8>`; nombrar a la persona es la spec 032 (`require_operator`) |
| V | Estados honestos; la ausencia se diseña | ☑ | Panel con estado parcial por tarjeta; `EmptyState`/`ErrorState` en cada vista; sin columna de tier ni pestaña Módulos mientras no existan |
| VI | Por API, nunca navegando la consola | ☑ | N/A — no hay agente |
| VII | Test primero | ☑ | Tests API en rojo antes de los endpoints; vitest del nav y de los filtros |
| VIII | Licencias | ☑ | Sin dependencias nuevas de terceros. `@nexus/ui` es del repo |
| IX | KB dueña del porqué | ☑ | `[[ADR-042-el-panel-de-auphere-se-ordena]]` |

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | Ninguna garantía nueva; lecturas por partner con su GUC | T020 |
| **Licencias** | Ninguna dependencia de terceros nueva | — |
| **Medidor** | Nada gasta | — |

## Decisiones de diseño

- **Workspace raíz**, no `link:` desde el workspace propio del panel: con `link:` las
  dependencias de `packages/ui` nunca se instalarían en Vercel. Se borran
  `apps/admin/pnpm-workspace.yaml`, `apps/admin/pnpm-lock.yaml` y los anidados de
  `apps/admin/packages/ucm-*` (un `pnpm-workspace.yaml` anidado es la trampa que el
  comentario del raíz documenta para `apps/desktop`).
- **Escala de espaciado**: no se conserva la del panel. Los pasos 1–4 son iguales; 5–9
  eran el defecto. Los componentes de `@nexus/ui` se diseñaron con el multiplicador
  estándar.
- **Fuente**: Inter vía `next/font` como `--font-inter` (lo único que leen los tokens).
- **Sidebar**: `nav.ts` declarativo (`NavGroup[]`) como la consola; el contador de
  tickets se lee en el layout del servidor y se pasa al sidebar.
- **Paleta ⌘K**: `CommandPalette` de `@nexus/ui` alimentado por una server action que
  busca en `/admin/partners`, `/admin/tenants` y `/admin/tickets` (sin endpoint nuevo).
- **Ficha de partner**: las pestañas antiguas se agrupan; sus rutas siguen existiendo
  como redirecciones (`keys`→`settings`, `tenants`/`usage`→`clients`,
  `limits`/`models`→`settings`, `wallet`/`receipts`→`money`).
- **Agente**: sub-pestañas por `?section=` con `NavTabs` de `@nexus/ui`; los
  componentes existentes no cambian, solo se reparten.

## Project Structure

```text
apps/admin/
├── package.json · next.config.ts · eslint.config.mjs        (deps, transpile, lint)
├── src/app/
│   ├── globals.css · layout.tsx                              (tokens, Inter, providers)
│   ├── (dashboard)/layout.tsx                                (shell fijo como la consola)
│   ├── (dashboard)/page.tsx                                  (Panel — nuevo)
│   ├── (dashboard)/status/page.tsx                           (Estado — nuevo)
│   ├── (dashboard)/partners/{page.tsx, partners-table.tsx}
│   ├── (dashboard)/partners/[id]/{layout,page,tabs}.tsx + clients/ team/ money/ settings/
│   └── (dashboard)/tenants/{page.tsx, tenants-table.tsx} + [id]/{layout,tabs}.tsx, agent/
├── src/components/shell/{nav.ts, app-sidebar.tsx, user-menu.tsx, command-palette.tsx}
└── src/components/ui/                                        (BORRADO)

apps/api/src/nexus_api/
├── api/admin/overview.py                                     (nuevo)
├── api/admin/partners.py                                     (members, PartnerOut ampliado)
└── schemas/partner.py
```

## Riesgos

- Vercel sin «Include source files outside of the Root Directory» no resuelve
  `workspace:*` → se prueba con un preview antes de fusionar. Es un cambio de panel en
  Vercel, se anota en el PR.
- `FormControl` de `@nexus/ui` admite un solo hijo.
- `StatusDot` de `@nexus/ui` tiene `muted` por defecto (el del panel, `positive`).
- El modo oscuro pasa a ser alcanzable: cada ruta se revisa en oscuro.
- `tw-animate-css` empieza a animar diálogos y hojas.
