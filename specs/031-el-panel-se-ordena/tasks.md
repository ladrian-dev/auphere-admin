---
description: "Tareas de la spec 031 — el panel de Auphere se ordena"
---

# Tasks: el panel de Auphere se ordena

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md)

**Tests**: no son opcionales (constitución §VII).

## Reglas

- Cada tarea termina con `_Requisitos: N.m_`.
- Test primero. Trabajo en local → `develop` (staging). Producción cuando el owner promueve.

## Phase 1: Workspace y sistema de diseño (US2)

- [X] T001 Añadir `apps/admin` y `apps/admin/packages/*` al `pnpm-workspace.yaml` raíz (con `msw` en builds permitidos); borrar `apps/admin/pnpm-workspace.yaml`, `apps/admin/pnpm-lock.yaml` y los `pnpm-workspace.yaml`/`pnpm-lock.yaml` de `apps/admin/packages/ucm-*`; `pnpm install` en raíz; actualizar el comentario del raíz. _Requisitos: 1.5_
- [X] T002 `apps/admin/package.json`: `@nexus/ui: workspace:*`, `@base-ui/react ^1.5.0`, `next`/`eslint-config-next` 16.2.11, fuera `@radix-ui/react-slot` y `shadcn`; `next.config.ts` con `transpilePackages: ["@nexus/ui"]`; scripts `admin:*` en el `package.json` raíz. _Requisitos: 1.1, 1.5_
- [X] T003 CI `.github/workflows/ci.yml` (`test-admin`): instalar desde raíz con `cache-dependency-path: pnpm-lock.yaml`. _Requisitos: 1.5_
- [X] T004 `globals.css` = el de la consola; `layout.tsx` con Inter (`--font-inter`), `ThemeProvider`, `UiCopyProvider` en español, `Toaster` de `@nexus/ui`, `themeColor` oklch. _Requisitos: 1.3, 1.4_
- [X] T005 Reescribir imports `@/components/ui/*` → `@nexus/ui`; borrar `src/components/ui/`, `src/hooks/use-mobile.ts`, `components.json`; arreglar `FormControl` de varios hijos. _Requisitos: 1.1_
- [X] T006 Borrar duplicados de marca (`eyebrow`, `status-dot`, `page-header`, `wordmark` y sus tests) y usar los de `@nexus/ui` (tono explícito en `StatusDot`). _Requisitos: 1.1_
- [X] T007 Colores: `[color:var(--…)]`, estilos inline, paleta Tailwind y hex → utilidades de token; medios pasos → pasos enteros. _Requisitos: 1.2_
- [X] T008 `eslint.config.mjs` con `@nexus/ui/eslint` recommended y `--max-warnings 0`; cero avisos. _Requisitos: 1.2_

## Phase 2: Shell (US1, US5)

- [X] T010 [P] Test vitest `src/components/shell/__tests__/nav.test.ts`: orden de grupos y entradas, `isActive` con rutas hijas. _Requisitos: 2.1, 2.2_
- [X] T011 `src/components/shell/nav.ts` + `app-sidebar.tsx` (marca que se pliega, grupos, contador de tickets) + `user-menu.tsx` (tema claro/oscuro/sistema, cerrar sesión). _Requisitos: 2.1–2.3, 2.5, 1.3_
- [X] T012 `(dashboard)/layout.tsx` con el shell fijo de la consola (barra con `SidebarTrigger` y paleta). _Requisitos: 2.3_
- [X] T013 Paleta ⌘K (`command-palette.tsx` + server action de búsqueda). _Requisitos: 2.4_

## Phase 3: API (US1, US3)

- [X] T020 [P] Tests en rojo `apps/api/tests/unit/test_admin_overview.py` (cifras sembradas; saldo total = suma por partner con su GUC; tarjeta parcial si una lectura falla) y `test_admin_partner_members.py` (personas + invitaciones pendientes; `PartnerOut` con conteos y flags; `billing_email` editable y auditado). _Requisitos: 3.1, 3.4, 4.1, 4.4, 4.6_
- [X] T021 `api/admin/overview.py` (`GET /admin/overview`). _Requisitos: 3.1, 3.2_
- [X] T022 `PartnerOut` + `PartnerUpdateIn.billing_email` + `GET /admin/partners/{id}/members`. _Requisitos: 4.1, 4.4, 4.6_

## Phase 4: Panel y Estado (US1, US6)

- [X] T030 `(dashboard)/page.tsx` Panel: métricas, «Necesita tu atención», línea tranquila, estado parcial. _Requisitos: 3.1–3.4_
- [X] T031 `(dashboard)/status/page.tsx`. _Requisitos: 6.1, 6.2_

## Phase 5: Partners (US3)

- [X] T040 [P] Test vitest del filtro del listado de partners. _Requisitos: 4.2_
- [X] T041 Listado con `partners-table.tsx` (búsqueda, estado, columnas nuevas); fuera la copia del widget. _Requisitos: 4.1, 4.2, 4.7_
- [X] T042 Ficha: cabecera de hechos, pestañas nuevas (`page` Resumen con edición, `clients`, `team`, `money`, `settings`, `knowledge`, `audit`) y redirecciones de las antiguas. _Requisitos: 4.3–4.6, 4.8_

## Phase 6: Clientes (US4)

- [X] T050 [P] Test vitest del filtro del listado de clientes. _Requisitos: 5.2_
- [X] T051 Listado con partner enlazado, búsqueda y filtros. _Requisitos: 5.1, 5.2_
- [X] T052 Cabecera con partner, pestañas en español, borrar `integrations/`. _Requisitos: 5.3, 5.5, 5.6_
- [X] T053 Agente con sub-pestañas `?section=`. _Requisitos: 5.4_

## Phase 7: Cierre

- [X] T060 `docs/admin.md` (spec viva del panel) y enlace desde `docs/console.md`.
- [X] T062 Licencias (§VIII): `pnpm-lock.yaml` cambia respecto a `develop` porque absorbe el lockfile del panel. Comprobado el 2026-10-18 que **ningún paquete** del lockfile nuevo falta en la unión de los dos antiguos (`git show develop:pnpm-lock.yaml` ∪ `git show develop:apps/admin/pnpm-lock.yaml`): no entra ninguna dependencia de terceros. Las versiones de `@assistant-ui/{core,store,tap}` se fijan con `pnpm.overrides` a las que el panel ya usaba. _Requisitos: 1.5_
- [X] T061 `./scripts/verify.sh js` + `pnpm --filter admin typecheck lint test build`; recorrido 390/768/1440 claro y oscuro; crítica final en `evidence/`.
