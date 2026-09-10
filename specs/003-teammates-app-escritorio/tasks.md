---
description: "Task list for feature implementation"
---

# Tasks: los teammates viven en la aplicación de escritorio

**Input**: documentos de diseño en `/specs/003-teammates-app-escritorio/`

**Prerequisites**: [`plan.md`](./plan.md) · [`spec.md`](./spec.md) ·
[`research.md`](./research.md) · [`data-model.md`](./data-model.md) ·
[`contracts/`](./contracts) · [`quickstart.md`](./quickstart.md)

**Tests**: **no son opcionales.** §VII — cada criterio de aceptación nace como
test, se ve en rojo, y solo entonces se implementa. Un `skip` puntúa como
aprobado y por tanto no cubre nada.

**Organization**: por historia de usuario, para que cada una se implemente y se
pruebe sola.

## Cobertura por capacidad, no por cita

Al final hay una tabla que responde, por cada requisito, **qué se puede hacer
que antes no** y **qué test lo vio en rojo**. Un requisito que solo aparece
citado en tareas que no lo construyen **no está cubierto**.

## Orden de las historias, y por qué

Tres P1 y dos P2. El orden lo fija la dependencia: **US1** (roster e hilo) es la
pantalla; **US2** (la tarea que espera) es lo que hace que la pantalla no mienta
al cerrarla; **US3** (ejecutar en mi máquina) es lo que hace que un teammate
sea distinto de un chat, y es la pieza que la 001 dejó vacía. **US4** (crear
teammate) va después porque un roster sembrado ya deja probar todo lo anterior;
**US5** (consumo) al final porque es lectura. El MVP es **US1 + US2 + US3**.

---

## Phase 0: La puerta del renderer

**Propósito**: la única capacidad no probada del plan. Un renderer React
construido con Vite, cargado desde `file://` en una `WebContentsView` con
`preload` CJS, recibiendo un *stream* reenviado por IPC desde el proceso
principal. Si no funciona así, D9 y D10 cambian antes de construir encima.

- [x] T001 Spike con display en `apps/desktop/`: `vite.app.config.ts` (`base: "./"`,
      salida `dist/app/`) con un `App.tsx` mínimo que usa un componente de `@nexus/ui`;
      tercera `WebContentsView` en partición `auphere-app` con `app-preload.cjs` que
      expone `ping()` y `onEvent()`; el principal abre `GET /api/companion/runs/{id}/stream`
      del BFF con `session.fromPartition("persist:auphere-console").fetch`, parsea SSE y
      reenvía por `webContents.send`. Comprobar (a) el renderer pinta con tokens, (b)
      `typeof window.auphere` sigue `undefined` en la vista de la consola, (c) tres
      eventos llegan al renderer con < 300 ms de retraso, (d) `assertPartitionsAreSeparate`
      con **cuatro** particiones. Evidencia en `evidence/T001/`. _Requisitos: 12.1, 12.3, 3.2_

---

## Phase 1: Setup

- [x] T002 [P] Añadir `apps/desktop` a `pnpm-workspace.yaml` raíz; en `apps/desktop/package.json`
      añadir `react@19.2`, `react-dom@19.2`, `vite@7.3`, `@vitejs/plugin-react`,
      `@nexus/ui: workspace:*`, `@nexus/companion-ui: workspace:*`; script `build` →
      `copy-tokens && tsc -p tsconfig.build.json && vite build -c vite.app.config.ts && node scripts/copy-preloads.mjs`;
      `scripts/copy-preloads.mjs` generaliza `copy-bar.mjs` para `bar-preload` y `app-preload`. _
      **PASA (2026-09-10).** `evidence/T001/result.json`: el renderer pinta con tokens OKLCH (`bodyBg oklch(0.971 …)`, botón `oklch(0.727 0.138 167.3)`), `window.auphere` es `object` en la app y **`undefined`** en la vista de la consola (que cargó `http://localhost:3110/login`), y tres eventos SSE leídos con `session.fromPartition(...).fetch` (primer byte a los 67 ms) llegaron al renderer por IPC con **1–6 ms** de latencia. `assertPartitionsAreSeparate` con cuatro particiones en verde (174 tests). D9 y D10 confirmados.Requisitos: 12.1_
- [x] T003 [P] **Puerta de licencias (§VIII)**: `docs/licenses/desktop-renderer.md` con
      `react`, `react-dom`, `vite`, `@vitejs/plugin-react` — versión, licencia MIT y el
      párrafo citado; anotar que de KiroCrew no entra ningún fichero. _Requisitos: §VIII_
- [x] T004 [P] Esqueleto de `packages/companion-ui/` (`package.json` `@nexus/companion-ui`,
      `tsconfig`, `vitest.config` con jsdom, `src/index.ts` vacío, `exports`); añadirlo
      al workspace raíz y a `transpilePackages` de `apps/console/next.config.ts`. _
      **HECHO.** `docs/licenses/desktop-renderer.md`: react/react-dom 19.2.4, vite 8.2.1, plugin-react 6.0.5, tailwindcss 4.3.3, tw-animate-css 1.4.0 — MIT, párrafo citado del fichero leído.
      **HECHO.** `apps/desktop` y `packages/companion-ui` en `pnpm-workspace.yaml` (con `electron` en `allowBuilds`); React 19.2, Vite 8.2, `@vitejs/plugin-react` 6, Tailwind 4.3 por Vite; `vite.app.config.ts`, `tsconfig.app.json`, `copy-preloads.mjs` (barra + app). `pnpm build` dentro de `apps/desktop` tropieza con el *deps check* de pnpm; los pasos se ejecutan por sus binarios y funciona.Requisitos: 12.5_
- [x] T005 [P] Ajustes nuevos en `apps/api/src/nexus_api/config.py`: `teammate_run_max_seconds`
      (1800), `local_exec_wait_seconds` (900), `teammate_task_ttl_days` (7); documentados en
      `apps/api/.env.example`. _Requisitos: 3.2, 6.1_
- [x] T006 [P] `docs/companion/CONTRACT-V3.md` a partir de `contracts/teammates-events.md`:
      los 4 eventos nuevos, `hitl.requested` con `level`/`task_
      **HECHO.** `teammate_run_max_seconds=1800`, `local_exec_wait_seconds=900`, `teammate_task_ttl_days=7` en `config.py`, documentados en `.env.example`.
      **HECHO.** Paquete con `package.json`, `tsconfig`, `vitest.config` (jsdom + jest-dom), `src/index.ts`; en el workspace raíz y en `transpilePackages` de la consola.id`/`expires_at` nulo,
      `run.completed` con `waiting`; enlace desde V2 §8. _Requisitos: 3.4, 5.3, 7.1_

---

## Phase 2: Foundational — el eje teammate en la plataforma

**Propósito**: sin roster, hilo con dos ejes y catálogo por teammate no hay
historia que probar. Los tests de aislamiento van **primero** y en rojo.

### Tests de la Phase 2 ⚠️

- [x] T007 [P] `apps/api/tests/isolation/test_
      **HECHO.** `docs/companion/CONTRACT-V3.md`: 4 eventos nuevos, `hitl.requested` y `run.completed` ampliados, reglas que no cambian, garantía con test.31_teammate_roster_scope.py`: dos partners con
      teammates; con `app.partner_id` de uno, `SELECT`/`UPDATE` no alcanza los del otro;
      `analyst` y `billing` no pueden crear (`teammates:use`); nunca `DELETE`. _Requisitos: 1.1, 1.2, 2.2_
- [x] T008 [P] `apps/api/tests/isolation/test_
      **HECHO (rojo → verde).** 5 tests: roster completo para cualquier miembro, nada sin GUC, `UPDATE` ajeno toca 0 filas, `DELETE` denegado a `nexus_app` (la migración lo revoca), permisos por rol.32_teammate_thread_two_axes.py`: dos personas
      del mismo partner, mismo teammate: cada una ve solo su hilo; `teammate_tasks` hereda
      por `EXISTS` sobre el hilo; la bandeja de una no lista acciones de la otra. _Requisitos: 3.1, 5.1_
- [x] T009 [P] `apps/api/tests/isolation/test_
      **HECHO (rojo → verde).** Hilos y acciones por persona con el mismo teammate; `POST /threads` con un `teammate_id` de otro partner → 404 opaco. La parte de `teammate_tasks` (hereda por `EXISTS`) se afirma en T042, cuando exista la tabla.33_teammate_catalog_is_subset.py`: el catálogo
      que recibe `CompanionToolbelt` para un teammate de finanzas no contiene herramientas
      de desarrollo ni `shell_local` sin `local_exec`; `tool_names ⊄ ALL_TOOLS` → 422;
      cambiar el oficio cambia el catálogo en el siguiente run. _Requisitos: 4.1, 4.2, 4.3, 2.3, 2.4_
- [x] T010 [P] `apps/api/tests/unit/test_
      **HECHO (rojo → verde).** 6 tests sobre `for_teammate` + `CompanionToolbelt.specs()`: solo lecturas sin `write`, nunca `shell_local` sin `local_exec`, `consult` manda, nombre fuera del catálogo rechazado, cambiar permisos cambia el siguiente turno, el toolbelt no publica lo no dado (y `call` lo rechaza en el motor).teammate_audit_vocab.py`: las ocho filas nuevas
      existen y ninguna admite al teammate como `{actor}`. _Requisitos: 13.1, 13.2_
- [x] T011 [P] `apps/api/tests/integration/test_
      **HECHO.** En `tests/integration/` (lee la base, no una constante): ocho filas, categoría `teammates`, `{actor}` = persona.contract_v3_catalog.py`: el catálogo de
      `companion_streaming` tiene **24** eventos; `publish` rechaza `task.state` con `state`
      fuera del enum; `hitl.requested` acepta `expires_at=None` solo con `task_id`. _Requisitos: 3.4, 6.1, 7.1_

### Implementación de la Phase 2

- [x] T012 Migración `apps/api/alembic/versions/0109_
      **HECHO (rojo → verde).** 24 eventos; `task.state` valida `state` y **`cause`** (no `reason`: la guarda C8 `test_companion_no_customer_bodies` prohíbe esa clave — CONTRACT-V3 y los contratos se corrigieron); `hitl.requested` con `expires_at` nulo solo con `task_id`; `exec.completed` sin salida.teammates.py`: tabla `teammates` con
      las columnas de `data-model.md` (`name text ≤ 80`, `job ≤ 80`, `model`, `tool_names text[]`,
      `permissions jsonb`, `local_exec bool`, `status active|archived`, `created_by`,
      `archived_at`; CHECK `archived_at IS NOT NULL ⇔ status='archived'`), RLS por
      `app.partner_id` (política como `partner_devices_owner` sin filtro de principal);
      `threads.teammate_id uuid FK NULL` + índice `(principal_id, teammate_id)`;
      `runs.teammate_id uuid NULL`. _Requisitos: 1.1, 1.4, 3.1_
- [x] T013 Migración `0112_
      **HECHO.** `0109_teammates.py`: tabla, CHECKs, índice, RLS FORCE por `app.partner_id`, `REVOKE DELETE … FROM nexus_app`, `threads.teammate_id` (FK RESTRICT + índice `(principal_id, teammate_id)`), `runs.teammate_id`.teammate_audit_vocab.py`: las ocho filas de `data-model.md`
      §Vocabulario, con CASTs como 0108. _Requisitos: 13.1_
- [x] T014 [P] Modelo `apps/api/src/nexus_
      **HECHO como `0110_teammate_audit_vocab.py`** (renumerada: Alembic es lineal y las de US2/US3 irán detrás como 0111/0112). Ocho filas con CASTs como 0108.api/db/models/teammate.py` (`Teammate`,
      `TEAMMATE_STATUSES`, `JOB_SEED` de ocho oficios) exportado en `db/models/__init__.py`;
      columnas nuevas en `companion.py` (`CompanionThread.teammate_id`, `CompanionRun.teammate_id`). _Requisitos: 1.1_
- [x] T015 [P] Permisos en `apps/api/src/nexus_
      **HECHO.** `db/models/teammate.py` (`Teammate`, `TEAMMATE_STATUSES`, `JOB_SEED`, `PERMISSION_KEYS`) exportado; `CompanionThread.teammate_id`, `CompanionRun.teammate_id`.api/core/console_auth.py`: `teammates:use`
      = {owner, admin, builder}; `teammates:policy` = {owner, admin}; y en
      `apps/console/src/lib/permissions.ts` con su test. _Requisitos: 2.2, 10.1_
- [x] T016 `apps/api/src/nexus_
      **HECHO.** `teammates:use` = {owner, admin, builder}, `teammates:policy` = {owner, admin} en `console_auth.py`, `permissions.ts` y su snapshot de test.api/repositories/teammates.py`: `TeammateRepository`
      (`list_active`, `get`, `create`, `update`, `archive`) — siempre bajo
      `apply_partner_to_session`; nunca `delete`. _Requisitos: 1.1, 2.6_
- [x] T017 `apps/api/src/nexus_
      **HECHO.** `repositories/teammates.py`: `list_active`, `get`, `get_active`, `create`, `update`, `archive`; sin `delete` a propósito.api/services/teammate_catalog.py`: `permissions_to_tool_names`
      (los cinco interruptores → nombres de `ALL_TOOLS`), `for_teammate(teammate, mode,
      machine_present)` = filtro sobre `ALL_TOOLS` ∩ modo, + `shell_local` solo con
      `local_exec` y máquina presente; `validate_tool_names` (⊆ `ALL_TOOLS`, 422
      `tool_not_in_catalog`); `system_prompt_for(teammate)` con nombre y oficio. _Requisitos: 4.1, 4.2, 2.3_
- [x] T018 Eje teammate en `apps/api/src/nexus_
      **HECHO.** `services/teammate_catalog.py`: los cinco interruptores → nombres (`read` lecturas · `write` propuestas+prueba+apply sin publicar/invitar/gastar · `publish` · `spend` asignación y modelo · `contact` invitar y soporte), `validate_tool_names` (422 `tool_not_in_catalog` en la API de US4), `for_teammate` (modo manda; `shell_local` solo con `local_exec` + máquina + catálogo), `system_prompt_for`.api/api/console/companion.py`: `POST /threads`
      acepta `teammate_id`; `GET /threads?teammate_id=` filtra y **sin** parámetro excluye
      los que lo tienen; `start_run` copia `teammate_id` al run, usa `for_teammate` en el
      toolbelt y el prompt del teammate; `hitl.requested` emite `level`; T009 en verde. _Requisitos: 3.1, 4.1, 14.3_
- [x] T019 Eventos V3 en `apps/api/src/nexus_
      **HECHO.** `POST /threads` acepta `teammate_id` (404 opaco si no es del partner, `_require_teammate` bajo `app.partner_id`); `GET /threads?teammate_id=` filtra y sin él excluye; `start_run` copia `teammate_id` al run, pasa `allowed_tools` al toolbelt y la identidad como mensaje de sistema fuera del prefijo cacheado. `hitl.requested` con `level` se emite en T049 (la columna llega en 0111). Companion: 68 tests en verde.api/api/companion_streaming.py`: `task.state`,
      `exec.dispatched`, `exec.completed`, `inbox.changed`; `hitl.requested` con
      `level`/`task_id`/`expires_at` nulo; `run.completed` con `waiting`; T011 en verde. _Requisitos: 3.4, 7.1_
- [x] T020 `apps/api/tests/isolation/test_
      **HECHO.** `task.state`, `exec.dispatched`, `exec.completed`, `inbox.changed`; `hitl.requested` + `level`/`task_id`; `InvalidCompanionEvent` y `_check_v3` en `sanitise_payload`.console_scope.py`: `_fill` conoce `{teammate_id}`,
      `{task_id}`, `{action_id}`; la ruta nueva `/console/teammates/*` entra sola en la
      cobertura. _Requisitos: 14.1_

---

## Phase 2b: El paquete compartido — la consola sigue en verde

**Propósito**: mover el Companion a `@nexus/companion-ui` **antes** de que el
escritorio lo use, con la consola consumiéndolo y sus 12 tests intactos.

- [x] T021 Mover a `packages/companion-ui/src/`: `state.ts`, `types.ts`, `use-companion.ts`,
      `i18n.ts` (como `CompanionMessagesProvider` + `useCompanionText`), y los componentes
      `timeline`, `confirm-card`, `composer`, `meters`, `thinking`, `verify-table`,
      `intake-card`, `plan-card`, `tool-card`, `support`; sus tests a `packages/companion-ui/tests/`.
      Ningún `next/*`; enlaces como callbacks (`onOpenClient`). _
      **HECHO.** `_fill` conoce `{teammate_id}`, `{task_id}`, `{action_id}`; `test_21` registra `teammates` como tabla de partner. Suite de aislamiento: 782 en verde.Requisitos: 12.5, 12.6_
- [x] T022 `packages/companion-ui/src/transport.ts` con la interfaz `Transport`
      (`request`, `openStream`) y `use-companion.ts` sobre ella; `messages/{es,en}.ts` con las
      claves que hoy están en `apps/console/src/i18n/lanes/companion.ts`. _Requisitos: 12.5_
- [x] T023 La consola consume el paquete: `apps/console/src/components/companion/client.ts`
      pasa a implementar `Transport` con `fetch` + `EventSource`; `drawer`, `companion-launcher`,
      `trial-panel`, `page-context` importan de `@nexus/companion-ui`; `lanes/companion.ts`
      re-exporta las claves del paquete; `pnpm -F @nexus/console test typecheck lint` en verde. _
      **HECHO.** `transport.ts`: `Transport { request, stream }`, `createFetchTransport(base)` (el `fetch` + `SseParser` de la consola) y `makeCompanionClient(transport)`; `useCompanion(transport)` con el bucle de reconexión intacto. Los textos van en `messages.ts` (un fichero con `es`/`en` por clave, como las lanes de la consola) y `formatMessage`.
      **HECHO.** `packages/companion-ui/src/`: `types`, `state`, `sse`, `wire` (DTOs con un solo dueño, + `teammate_id`), `storage` (caché de runs), `messages` (la lane entera + `common.retry`), `i18n.tsx` (`CompanionLocaleProvider` con `renderLink`), y 11 componentes en `components/` (incluido `trial-panel`, cuyo `next/link` pasó a `renderLink`). 8 ficheros de test movidos (135 tests en verde). Lint con las reglas de `@nexus/ui`.Requisitos: 12.6, 14.1_

---

## Phase 2c: Las puertas de la constitución

- [x] T024 [P] **Puerta de aislamiento**: T007, T008, T009 en rojo antes de T012 y en verde
      después; `test_34` (US3) y `no-credentials-over-ipc` (US1) en sus fases. Anotar aquí
      las cuatro garantías (1, 2, 3, 6) con su test. _Requisitos: 14.1_
- [x] T025 [P] **Puerta del medidor**: `apps/api/tests/integration/test_
      **Puerta de aislamiento — anotada.** Garantía 1: `test_31` (roster por partner) y `test_32` (hilo con dos ejes); garantía 2: `test_33` (catálogo por teammate) y `test_34` (US3, la política no amplía); garantía 3: `test_34` + `test_local_dispatch` (la salida es dato); garantía 6: `test_teammate_audit_vocab` + T070. En el escritorio: `no-credentials-over-ipc` (US1). Los tres primeros se vieron en rojo antes de 0109.
      **HECHO.** La consola: `client.ts` = transporte + cliente + ancho/modo; `drawer` y `companion-launcher` importan del paquete y el lanzador monta `CompanionLocaleProvider` con `next/link`; `lanes/companion.ts`, `playground/sse.ts` y `lib/backend/companion.ts` re-exportan. Consola: 180 tests (315 − 135 movidos), `tsc` y `eslint` limpios.teammates_single_meter.py`:
      un run de teammate pasa por `llm_proxy_partner_scope` y debita la misma wallet; `GET
      /console/teammates/usage.budget` == `GET /console/companion/budget` byte a byte; no
      existe tabla ni evento de consumo nuevo (`usage_events` no gana filas por teammate). _Requisitos: 9.1, 9.2, 8.1_

---

## Phase 3: User Story 1 — Mi equipo, y mi hilo con cada uno (P1) 🎯

**Goal**: abrir la app y ver el roster del partner y hablar con cada teammate en un
hilo propio, con el catálogo de su oficio.

**Independent Test**: con dos teammates sembrados (`scripts/seed_
      **HECHO (verde).** `test_teammates_single_meter.py`: el turno de un teammate debita `partner_wallets` por el mismo camino, `runs.teammate_id` queda puesto, `usage_events` no gana filas, `/companion/budget` lo cuenta, y la lista de hilos de la consola nunca lo muestra. La igualdad `usage.budget == companion/budget` se afirma en T075 cuando exista la ruta.teammates_dev.py`)
y dos personas, cada una ve los dos, escribe a uno, ninguna ve el hilo de la otra
(T008), y el modelo recibe solo el catálogo del oficio (T009).

### Tests de la US1 ⚠️

- [x] T026 [P] [US1] `apps/api/tests/integration/test_teammates_roster.py`: `GET /console/teammates`
      devuelve `my_state`/`my_unread`/`last_done` derivados del hilo de la persona; archivados
      fuera salvo `include_archived`; `analyst` → 403. _Requisitos: 1.2, 1.3, 1.5_
- [x] T027 [P] [US1] `apps/desktop/tests/app-ipc.test.ts`: la lista de `app-ipc.ts` coincide
      con `contracts/desktop-app-ipc.md` (nombres y formas); el `preload` expone exactamente
      esos nombres y ninguno más. _
      **HECHO (rojo → verde).** `test_teammates_roster.py`: estado derivado por persona (`en_marcha`/`en_espera`/`my_unread`), el hilo de otra persona no colorea el mío, archivados fuera salvo `include_archived`, `analyst` → 403, y `/jobs` con los ocho oficios y los modelos del allowlist.Requisitos: 12.1_
- [x] T028 [P] [US1] `apps/desktop/tests/no-credentials-over-ipc.test.ts`: para cada canal,
      con un `PlatformClient` falso que devuelve cuerpos con `session`, `cookie`, `token`,
      `credential`, `authorization` a varias profundidades, la respuesta al renderer **no**
      contiene esas claves; el preload no expone `ipcRenderer`. _Requisitos: 12.2_
- [x] T029 [P] [US1] `apps/desktop/tests/platform-client.test.ts`: usa `session.fromPartition`
      inyectado, nunca `fetch` global; 401 → `GateDecision stop`; 403 `no_
      **HECHO (rojo → verde).** `no-credentials-over-ipc.test.ts`: cuerpos envenenados con `session`, `cookie`, `token`, `Authorization`, `credential` a tres profundidades salen limpios en éxito y en error; el cliente no manda cabeceras de sesión por su cuenta; y el fuente del `preload` no expone `ipcRenderer` ni toca `document.cookie`.
      **HECHO (rojo → verde).** `app-ipc.test.ts`: los 22 canales de invocación y los 6 de empuje son exactamente el contrato; el puente expone una función por canal y `on`, y **no** `invoke`, `ipcRenderer` ni `send`; la validación rechaza canal desconocido, uuid mal formado, decisión inventada y `path` que no sea una ruta de la consola.membership` → `sin
      sesión`; nunca lee `document.cookie`. _Requisitos: 12.2, 12.3_
- [x] T030 [P] [US1] `apps/desktop/tests/sse.test.ts`: parser SSE puro (eventos multilínea,
      `id`, reconexión con `since_
      **HECHO (rojo → verde).** `platform-client.test.ts`: usa el `fetch` inyectado (el de la partición humana), 401/302/307 y una página HTML son `SessionLost`, 403 `no_membership` trae su motivo, otro 403 es error normal, sin red devuelve resultado y no excepción.seq`, chunks partidos). _Requisitos: 3.2_
- [x] T031 [P] [US1] `apps/desktop/tests/app-state.test.ts`: el estado del hilo deriva
      `normal · cargando · vacío · error · reconectando · parcial · esperandote ·
      en_
      **HECHO (rojo → verde).** `sse.test.ts`: trozos partidos, CRLF, comentarios, `id`, bloque sin `data`, `data` no-JSON como `raw`, y `readSse` hasta EOF.pausa_por_tope · maquina_ausente`; ninguno se pinta como error; `reconectando`
      retoma desde el último `seq` sin duplicar. _Requisitos: 3.4, 3.5, 3.7_
- [x] T032 [P] [US1] `apps/desktop/tests/session-isolation.test.ts` extendido: cuatro
      particiones distintas; `auphere-app` no persiste; `appWebPreferences(preload)` con
      `sandbox`, `contextIsolation`, sin `nodeIntegration`; la consola sigue sin `preload`. _
      **HECHO (rojo → verde).** `app-state.test.ts`: los nueve estados nombrados, las precedencias (tope > espera > máquina ausente), `isFailure` solo para `error`, y `task.state`/`inbox.changed` moviendo roster y bandeja sin recargar.Requisitos: 12.1, 12.3, 14.2_

### Implementación de la US1

- [x] T033 [US1] `apps/api/src/nexus_api/api/console/teammates.py` + `schemas_teammates.py`:
      `GET /console/teammates` (`last_done` = título de la última tarea terminada de la persona con
      ese teammate, o `null`), `GET /console/teammates/jobs`; router montado en `main.py`;
      `scripts/seed_teammates_dev.py` (dos teammates de ejemplo). _Requisitos: 1.2, 1.3, 1.5_
- [x] T034 [P] [US1] Proxies BFF en `apps/console/src/app/api/teammates/{route.ts, jobs/route.ts}`
      y `apps/console/src/lib/backend/teammates.ts` (`teammatesApi`) — solo `teammates:use`;
      sin página. _
      **HECHO.** `api/console/teammates.py` (+`schemas_teammates.py`) con `GET /console/teammates` y `/jobs`, montado en el router de consola; `scripts/seed_teammates_dev.py` (Sofía · Atención al cliente, Nilo · Desarrollo), ejecutado contra la base local.
      **HECHO (rojo → verde).** `session-isolation.test.ts` extendido: cuatro particiones, `auphere-app` sin `persist:`, `appWebPreferences` con sandbox y sin node, la consola sigue sin `preload`, y la pantalla no ve la cookie de la persona.Requisitos: 12.3, 14.3_
- [x] T035 [P] [US1] `apps/desktop/src/session-isolation.ts`: `APP_PARTITION="auphere-app"`,
      `appWebPreferences(preload)`, `assertPartitionsAreSeparate` con cuatro. _Requisitos: 12.1_
- [x] T036 [P] [US1] `apps/desktop/src/app-ipc.ts`: la lista cerrada de canales con sus formas
      (validación en runtime de entradas); `apps/desktop/src/electron/app-preload.ts` expone
      exactamente esa lista bajo `window.auphere`. _
      **HECHO.** `APP_PARTITION`, `appWebPreferences`, `assertPartitionsAreSeparate` con cuatro y `sessionCookieNames` invertido (solo la humana tiene cookies).
      **HECHO.** `lib/backend/teammates.ts` (`teammatesApi`, difundido en `backendFor`), `app/api/teammates/{route,jobs/route}.ts` y `withPermission(...)` extraído de `withCompanion` en el guard. Sin página en la consola: es plumbing. `whoami` gana `permissions` (su test lo fija, y sigue sin rol, correo ni nombre).Requisitos: 12.1, 12.2_
- [x] T037 [P] [US1] `apps/desktop/src/platform-client.ts`: `PlatformClient` sobre
      `session.fromPartition(HUMAN_PARTITION).fetch` contra `AUPHERE_CONSOLE_URL/api/...`;
      `redact()` que elimina las claves prohibidas antes de devolver; errores tipados. _Requisitos: 12.2, 12.3_
- [x] T038 [P] [US1] `apps/desktop/src/sse.ts` (parser puro) y `stream-hub.ts` (abre/cierra
      streams por `stream_
      **HECHO.** `platform-client.ts` sobre `session.fromPartition(HUMAN_PARTITION).fetch` (adaptador `partitionFetch`), con `SessionLost` y `redact` en toda salida.
      **HECHO.** `app-ipc.ts` (lista, formas, `validateInput`, `redact`, `hasForbiddenKey`), `app-bridge.ts` (`buildAppBridge`, puro y probado) y `electron/app-preload.ts`. Los `preload` pasan a empaquetarse con Vite a CJS (`vite.preload.config.ts`): desde ahora importan módulos propios y una reescritura por regex no bastaba.id`, reenvía `app:event`). _Requisitos: 3.2_
- [x] T039 [US1] `apps/desktop/src/electron/main.ts`: tercera vista `appView` por defecto,
      la consola oculta hasta `app:openConsole`; handlers `app:whoami`, `app:roster.list`,
      `app:roster.jobs`, `app:thread.open`, `app:thread.events`, `app:thread.send`,
      `app:thread.cancel`, `app:stream.open/close`, `app:openConsole`; `app:session` desde el
      `SessionGate` de 002; `app:presence` desde `runtime`. _
      **HECHO.** `sse.ts` (parser + `readSse`) y `stream-hub.ts` con su test: un stream por id, eventos con su `stream_id`, final dicho, y cerrar desde el renderer aborta **sin** emitir final ni cancelar el run.Requisitos: 3.2, 12.1, 12.3_
- [x] T040 [US1] Renderer `apps/desktop/src/app/`: `main.tsx`, `App.tsx` con tres columnas,
      `routes/roster.tsx` (lista con oficio, modelo, estado, `unread`, estado vacío «crea el
      primero»), `routes/thread.tsx` sobre `@nexus/companion-ui` con `Transport` por IPC
      (`transport-ipc.ts`), estados de T031, `styles.css` con `tokens.css`. El mapa evento→forma
      (`decir · preguntar · nota`, tipos de nota) es `TimelineItem` del paquete; `handoff` queda
      como tipo reservado sin productor. _Requisitos: 1.2, 1.3, 1.5, 3.4, 3.5, 3.6, 12.5_
- [x] T041 [US1] `apps/desktop/src/app/i18n.ts`: diccionario es/en para la pantalla +
      `CompanionMessagesProvider` del paquete; idioma por `locale` de `whoami`. _
      **HECHO y verificado con display.** `src/app/`: `App.tsx` (tres columnas, tema por `prefers-color-scheme`, sesión y presencia por empuje), `routes/roster.tsx` (cinco estados de Hurff: skeleton, error con reintento, sin permiso, vacío con CTA, ideal), `routes/thread.tsx` (paquete compartido + `deriveThreadState`), `routes/env.tsx`, `transport-ipc.ts` (rutas → canales, sin canal genérico) y `bridge.ts`. Evidencia en `evidence/US1/`: el roster real (Sofía, Nilo) leído con la sesión de la persona, el hilo abierto en `vacio`, y el aviso honesto de máquina sin emparejar. Dos correcciones §V que salieron del pase vivo: el selector de modo del `Composer` es opcional y no se pinta sin manejador, y el vacío del hilo es el de la app (el del cajón habla de modos que aquí no existen).
      **HECHO.** `main.ts`: tercera vista `appView` visible por defecto, la consola oculta hasta `app:openConsole` (menú Ver · ⌘1/⌘2), `registerAppSurface` con los handlers, `app:session` desde la puerta (que gana `refresh()`), `app:presence` desde el runtime, y la pantalla sin navegación ni ventanas. El HTML del renderer pierde el `meta` CSP: en `file://` el origen es opaco y `'self'` bloqueaba su propio bundle — la garantía es la vista (sandbox, sin node, sin navegar).Requisitos: 12.5_

---

## Phase 4: User Story 2 — El trabajo sobrevive a cerrar la aplicación (P1)

**Goal**: encargar, cerrar, volver: la tarea siguió o está `esperándote`; la
aprobación no caducó; Pendientes la lista; decidir en un sitio actualiza el otro.

**Independent Test**: tarea con aprobación en medio, app cerrada > 15 min
(`companion_action_ttl_seconds`), reabrir: `esperandote`, aviso del SO, aprobar
desde Pendientes → la tarjeta del hilo se marca en < 2 s.

### Tests de la US2 ⚠️

- [x] T042 [P] [US2] `apps/api/tests/integration/test_teammate_tasks.py`: el run de un hilo
      con teammate crea/continúa `teammate_tasks`; al `hitl.requested` el run cierra `waiting`
      y la tarea pasa a `esperandote`; `resume` abre un run nuevo en la misma tarea; una
      acción de teammate con `expires_at NULL` **no** da 409 `action_expired` tras 20 min;
      la tarea caduca por `expires_at` y cierra la acción `expired` con `task_expired`;
      archivar el teammate → `cancelada` + `teammate_archived`. _Requisitos: 3.2, 6.1, 6.2, 6.3, 2.6_
- [x] T043 [P] [US2] `apps/api/tests/integration/test_
      **HECHO (rojo → verde).** 7 tests contra la aplicación real: la tarea nace con el turno y el run le pertenece; aparcar **cierra** el run como `waiting` con `ended_at` y la tarea queda `esperandote` con su acción; la acción no caduca con `proposed_at` de hace seis horas y su `expires_at` sale `null`; decidir abre un run nuevo en la **misma** tarea; el barrido la caduca cerrando la acción con `cause=task_expired`; archivar el teammate la cancela con `teammate_archived`; y la persona puede cancelarla (409 la segunda vez).
      **HECHO.** `src/app/i18n.ts` (es/en, `LangProvider`, `useAppT`, `systemLang`) y `CompanionLocaleProvider` del paquete con `renderLink` que abre en la consola; el idioma viene de `whoami` y decae al del sistema.teammate_inbox.py`: `GET /inbox` lista
      solo acciones de hilos con teammate **de la persona**; nada del Companion sin teammate;
      `can_decide=false` cuando el permiso de la herramienta que hay detrás de la acción no está en
      `permissions_for(role)`; `GET /inbox/stream` emite
      `inbox.changed` al decidir. _Requisitos: 5.1, 5.2, 5.4, 6.4_
- [x] T044 [P] [US2] `apps/api/tests/unit/test_
      **HECHO (rojo → verde).** 5 tests: la bandeja lista lo de **esta** persona con nivel, tarea, run, teammate y `client_ref` y sin `tenant_id`; no lista lo de otra persona; **no** lista lo del Companion de la consola; un `analyst` recibe 403; y el aviso viaja por el canal de la persona.action_level.py`: `local_exec` y `risk=high` →
      `critico`; `mutates` → `aviso`; resto `informativo`. _Requisitos: 7.1_
- [x] T045 [P] [US2] `apps/desktop/tests/notifications-policy.test.ts`: `critico` → aviso del
      SO; `aviso` → badge; `informativo` → nada; al abrir con N esperando, **un** resumen;
      `silence_
      **HECHO (rojo → verde).** 5 tests sobre `level_for`. El clasificador quedó en **`core/`** y no en `services/`: `test_companion_tools_imports` prohíbe que un módulo de herramientas importe un servicio (se saltaría ámbito, RLS, cuota y auditoría), y esto es una función pura sin base de datos.aviso` no toca `critico`. _Requisitos: 7.2, 7.3, 7.5_
- [x] T046 [P] [US2] `apps/desktop/tests/inbox-sync.test.ts`: decidir por `app:inbox.decide`
      emite el cambio al hilo abierto y a la bandeja sin recargar; recibir `inbox.changed`
      del stream marca la tarjeta; **un `inbox.changed` perdido durante la reconexión** se
      recupera con el refresco de `GET /inbox` y la tarjeta queda igual de marcada. _
      **HECHO (rojo → verde).** 9 tests: `critico` interrumpe y marca, `aviso` solo marca, `informativo` ni cuenta; al abrir, **un** resumen (con una sola tarjeta, el aviso lleva a ella); silenciar `aviso` no calla lo crítico; y la preferencia es un booleano — no hay forma de subir un nivel.Requisitos: 5.3_

### Implementación de la US2

- [x] T047 [US2] Migración `0110_teammate_tasks.py`: tabla `teammate_tasks` (columnas y
      estados de `data-model.md`; RLS por `EXISTS` sobre `threads`), `runs.task_id`,
      `runs.status` + `waiting`, `actions.level text NOT NULL DEFAULT 'informativo'`,
      `actions.expires_at timestamptz NULL` con CHECK (NULL solo si el hilo tiene `teammate_id`),
      `actions.kind` + `local_exec`. _Requisitos: 6.1, 7.1_
- [x] T048 [P] [US2] Modelos y repos: `db/models/companion.py` (`RUN_
      **HECHO.** `0111_teammate_tasks.py`: `companion.teammate_tasks` con RLS por `EXISTS` sobre el hilo (patrón 0090) y CHECK de estados; `runs.task_id`; `actions.task_id` y `actions.level` con su CHECK; y el CHECK de `runs.status` ampliado con `waiting`. **Cambio sobre `data-model.md`**: en vez de `actions.expires_at` nullable —que dejaría ambiguas las filas viejas del Companion— la acción lleva `task_id`, que además es lo que `hitl.requested` necesita.
      **HECHO (rojo → verde).** 7 tests de `InboxWatcher`: la primera pasada resume, lo nuevo suena y lo ya visto no; **el aviso perdido durante la reconexión se recupera con `GET /inbox`** (el hallazgo H1 del análisis); `inbox.changed` retira la tarjeta; el bucle reconecta con espera creciente; y perder la sesión olvida la bandeja.WAITING`, `TeammateTask`,
      `TASK_STATES`), `repositories/teammate_tasks.py` (`open_or_continue`, `mark_waiting`,
      `resume`, `finish`, `cancel`, `expire_due`); `expires_at` se desplaza con cada run que
      termina y con cada decisión. _Requisitos: 6.1, 6.2_
- [x] T049 [US2] `apps/api/src/nexus_
      **HECHO.** `TeammateTask`, `RUN_WAITING`, `TASK_STATES`, `TASK_CAUSES`; `repositories/teammate_tasks.py` con `open_or_continue` (un hilo tiene **una** tarea viva), `running`, `waiting`, `paused`, `finished`, `cancel`, `cancel_for_teammate` y `expire_due` (el único método que corre sin persona).api/companion/tools/actions.py`: `stage_action` recibe
      `level` y `ttl=None` cuando el hilo es de teammate; `is_stale` devuelve `False` con
      `expires_at` nulo; `services/action_level.py` (T044). _Requisitos: 6.1, 6.3, 7.1_
- [x] T050 [US2] `api/console/companion.py`: el driver de teammate cierra el run en `waiting` al
      aparcar y emite `task.state`; `resume_
      **HECHO.** `stage_action` recibe `task_id` y fija `level`; `is_stale` devuelve `False` con `task_id`; `StagedAction` sirve `expires_at: null` y `level`; `core/action_level.py` clasifica.run` sin 409 por reloj para acciones de teammate,
      abre un run nuevo en la tarea y publica `inbox.changed` en `teammates:inbox:{principal}`;
      techos de D6 (`teammate_run_max_seconds`). _Requisitos: 3.2, 6.1, 6.2, 5.3_
- [x] T051 [US2] `services/teammate_
      **HECHO.** `start_run` abre o continúa la tarea y se la pasa al run y al toolbelt; `_finalise_run` cierra en `waiting` cuando hay tarea; `_move_task` mueve la tarea y emite `task.state`; `resume_run` continúa la **misma** tarea, hereda `teammate_id`/`task_id` y publica `inbox.changed`. El paquete compartido aprende `waiting` para no dar por terminado lo que espera.inbox.py` + rutas en `api/console/teammates.py`:
      `GET /inbox`, `GET /inbox/stream` (SSE por persona sobre Redis pubsub, `ping` 15 s),
      `GET /tasks`, `POST /tasks/{id}/cancel`; barrido `expire_due` como cron del **worker**:
      `apps/worker/src/nexus_worker/streams/teammate_task_expiry_cron.py` (cada 10 min, junto a
      `reminder_cron.py`), con test en `apps/worker/tests/`. _Requisitos: 5.1, 5.2, 5.4, 6.1_
- [x] T052 [P] [US2] Proxies BFF `apps/console/src/app/api/teammates/{inbox, inbox/stream,
      tasks, tasks/[id]/cancel}/route.ts` (el stream con `maxDuration` como el del Companion). _
      **HECHO.** `services/teammate_inbox.py` (lectura, canal por persona, `inbox_events` como flujo probado sin HTTP) y las rutas `GET /inbox`, `GET /inbox/stream`, `GET /tasks`, `POST /tasks/{id}/cancel`, más `DELETE /teammates/{id}` (que la US2 necesitaba para cancelar lo que esperaba; T072 lo da por hecho). El barrido es un cron del **worker** cada 10 min con su test — `scheduled_job` era un modelo, no un planificador (hallazgo I1 del análisis).Requisitos: 12.3_
- [x] T053 [P] [US2] `apps/desktop/src/notifications-policy.ts` (puro) y en `main.ts`:
      `Notification` del SO, resumen al abrir, badge del Dock/bandeja con el conteo,
      preferencia `silence_aviso` en `userData`; handlers `app:inbox.list`, `app:inbox.decide`,
      `app:tasks.list`, `app:tasks.cancel`, `app:notifications.prefs`; el stream de la bandeja
      abierto mientras hay sesión y, **en cada reconexión** (el proxy BFF corta a los 300 s),
      `GET /inbox` de nuevo y reconciliación — la bandeja no tiene historial. «Abierta» = proceso
      vivo, aunque la ventana esté en la bandeja del sistema. _Requisitos: 7.2, 7.3, 7.4, 7.5, 5.3_
- [x] T054 [US2] Renderer `routes/inbox.tsx` (Pendientes: nivel, prueba, cómo se deshace,
      desde cuándo, `can_
      **HECHO.** `notifications-policy.ts` (puro), `inbox-watcher.ts` (reconcilia en cada reconexión), `adapters.ts` con `Notification` y badge del Dock, preferencia en `userData`, y los handlers `app:inbox.list`, `app:tasks.list`, `app:tasks.cancel`, `app:notifications.prefs`. Decidir retira la tarjeta **aquí** sin esperar al canal; el canal es para las otras pantallas. Al perder la sesión, la bandeja se olvida.
      **HECHO.** `api/teammates/{inbox,inbox/stream,tasks,tasks/[id]/cancel,[id]}/route.ts` y `withPermission` reutilizado; el proxy SSE con `maxDuration` y sin historia que perder.decide`, estado vacío del diseño) y en el hilo el estado
      `esperandote` con la tarjeta; `app-state.ts` aplica `inbox.changed` y `task.state`. _Requisitos: 5.1, 5.3, 5.5, 6.2_

---

## Phase 5: User Story 3 — Ejecutar en mi máquina, con mi política y el techo (P1)

**Goal**: un teammate ejecuta en la máquina bajo lista blanca → techo → preferencia;
la app nunca amplía; la salida es dato.

**Independent Test**: tres combinaciones de techo/preferencia sobre un ejecutable
en lista y uno fuera; `test_
      **HECHO y verificado con display.** `routes/inbox.tsx` con los cinco estados (skeleton, vacío que explica cuándo aparece algo, error con reintento, `can_decide=false` como nota, ideal), nivel con las variantes del sistema, y navegación Equipo/Pendientes con contador. Un aviso del sistema abre Pendientes en su tarjeta (`app:inbox.focus`). Evidencia en `evidence/US2/`.34` en verde; un fichero creado dentro del `workdir`
y ninguno fuera.

### Tests de la US3 ⚠️

- [ ] T055 [P] [US3] `apps/api/tests/isolation/test_34_local_policy_cannot_widen.py`: con
      `ceiling=always` y `pref=always`, un ejecutable **fuera** de la lista se deniega
      (`ejecutable_no_permitido`) y no es aprobable; `pref=always` con `ceiling=ask` →
      `requiere_aprobacion`; `pref=never` → `politica_nunca`; la preferencia de una persona no
      afecta a otra; una máquina de otro partner no recibe el trabajo en `poll`. _Requisitos: 10.1, 10.2, 10.6_
- [ ] T056 [P] [US3] `apps/api/tests/integration/test_local_dispatch.py`: `shell_local` con
      máquina presente crea `local_executions pending`; `GET /device/poll` la devuelve una vez
      en `work[]`; `POST /device/result` con `stdout_sample` la cierra y la herramienta
      recibe `{outcome, exit_code, stdout_sample, untrusted: true}`; la muestra **no** está en
      `local_executions` ni en `audit_log`; sin máquina → `refused: machine_absent` y sin fila;
      `pending` con máquina sin latido 5 min → `expirada`. _Requisitos: 3.3, 3.5, 10.5, 11.1_
- [ ] T057 [P] [US3] `apps/api/tests/integration/test_local_exec_policy_api.py`: `PUT
      /console/team/local-exec-ceiling` solo `teammates:policy` y audita; `PUT /teammates/local-exec-prefs`
      devuelve `effective` y `capped`; `GET` devuelve el techo y las preferencias acotadas. _Requisitos: 10.1, 10.3, 10.4, 13.1_
- [ ] T058 [P] [US3] `apps/api/tests/unit/test_local_exec_gate_layers.py`: `most_restrictive`
      (`never < ask < always`), resolución global vs por ejecutable, `always` concede grant
      `by_policy` con `decided_by=principal`. _Requisitos: 10.2_
- [ ] T059 [P] [US3] `apps/desktop/tests/exec-result.test.ts`: `app-runtime` envía
      `stdout_sample` ≤ 2048 B (UTF-8 con reemplazo) en `/device/result`; nunca más. _Requisitos: 3.3_
- [ ] T060 [P] [US3] `apps/desktop/tests/exec-card.test.ts` (paquete o renderer): la tarjeta
      muestra ejecutable, argumentos y directorio, nunca salida; ofrece *una vez / siempre /
      nunca*; muestra «el techo del partner manda» cuando `capped`. _Requisitos: 10.3, 10.4, 10.5_

### Implementación de la US3

- [ ] T061 [US3] Migración `0111_local_exec_policy.py`: `partner_local_exec_policy(partner_id
      PK, ceiling ask|always|never, updated_by, updated_at)` RLS por partner;
      `principal_local_exec_prefs(id, partner_id, principal_id, executable NULL, mode; UNIQUE
      (partner_id, principal_id, executable))` RLS por partner + `app.principal_id`;
      `local_executions.task_id/teammate_id/device_id/dispatched_at`; `denial_reason` +
      `politica_nunca`; `local_argument_grants.by_policy bool default false`. _Requisitos: 10.1, 10.7_
- [ ] T062 [P] [US3] Modelos en `db/models/local_workstation.py` (+`DENIAL_POLITICA_NUNCA`,
      `PartnerLocalExecPolicy`, `PrincipalLocalExecPref`, `EXEC_MODES`) y
      `repositories/local_exec_policy.py`. _Requisitos: 10.1_
- [ ] T063 [US3] `services/local_exec_gate.py`: paso de política tras la lista blanca y la
      firma (`most_restrictive`, `never` → denegada `politica_nunca`, `always` → grant
      `by_policy`); `GateDecision.capped`; auditoría `local_exec.allowed_by_policy` /
      `denied_by_policy` / `allowed_once`. _Requisitos: 10.2, 10.6, 10.7, 13.1_
- [ ] T064 [US3] `services/local_dispatch.py`: `dispatch(execution)` (fila `pending` +
      `exec.dispatched`), `await_result(execution_id, wait_seconds)` (BLPOP
      `local_exec:{id}`), `expire_absent()`; `api/device_bridge.py`: `poll` devuelve `work[]`
      de **esta** máquina (`dispatched_at`), `ResultIn.stdout_sample` ≤ 2048 → Redis con TTL
      15 min, nunca a la fila. _Requisitos: 3.3, 10.5, 11.1_
- [ ] T065 [US3] Herramienta `companion/tools/local_exec.py` (`shell_local`) registrada en
      `catalog.py` con `reaches_network: None`: resuelve máquina y vínculo del cliente, gate,
      `stage_action(kind="local_exec", level="critico")` si aprobable, despacho y espera;
      resultado con `untrusted: true` y prefijo fijo; `refused: machine_absent`;
      `companion_tool_timeout_s` no aplica. _Requisitos: 3.3, 3.5, 10.2, 10.5_
- [ ] T066 [US3] `api/console/team.py`: `GET/PUT /console/team/local-exec-ceiling`;
      `api/console/teammates.py`: `GET/PUT /local-exec-prefs`; auditoría
      `local_policy.ceiling_changed` / `pref_changed`. _Requisitos: 10.1, 10.3, 10.4, 13.1_
- [ ] T067 [P] [US3] Consola: control del techo en la página de equipo
      (`apps/console/src/app/(console)/team/…`, `components/team/local-exec-ceiling.tsx` con
      test; `team:manage` + `teammates:policy`); proxies BFF `api/teammates/local-exec-prefs/route.ts`
      y `api/team/local-exec-ceiling/route.ts`. _Requisitos: 10.1_
- [ ] T068 [P] [US3] Escritorio: `app-runtime.ts` incluye `stdout_sample` en el resultado;
      `http-transport.ts` lo envía; `bridge.ts` tipa `work[]` de `contracts/local-dispatch.md`. _Requisitos: 3.3_
- [ ] T069 [US3] Renderer: `exec-card.tsx` en `@nexus/companion-ui` (una vez / siempre /
      nunca, `capped`), `routes/account.tsx` §Ejecución local (preferencia global y por
      ejecutable, techo acotando); handlers `app:policy.prefs`, `app:policy.setPref`; estado
      `maquina_ausente` en el hilo con la ausencia diseñada. _Requisitos: 3.5, 8.4, 10.3, 10.4_

---

## Phase 6: User Story 4 — Crear un teammate desde la aplicación (P2)

**Goal**: crear, cambiar y archivar un teammate desde la app; aparece para todos;
su catálogo es el de su oficio.

**Independent Test**: crear uno, verlo con otra persona del partner, cambiar el
oficio y ver el catálogo cambiar en el siguiente run, archivar y ver el hilo
legible.

### Tests de la US4 ⚠️

- [ ] T070 [P] [US4] `apps/api/tests/integration/test_teammates_crud.py`: `POST` traduce
      permisos a `tool_names`, 422 `model_not_allowed`, 422 `tool_not_in_catalog`; `PATCH`
      cambia el catálogo y deja en cada hilo activo un mensaje `role=system, kind=teammate_changed`
      visible al cargar el historial; `DELETE` archiva, cierra tareas
      `esperandote`, nunca borra; auditoría `teammate.created/updated/archived` con la
      persona. _Requisitos: 2.1, 2.3, 2.4, 2.6, 13.1_
- [ ] T071 [P] [US4] `apps/desktop/tests/new-teammate-form.test.tsx`: los cinco estados del
      formulario (pristine/dirty/submitting/error conserva lo escrito/ok); nombre ≤ 80. _Requisitos: 2.1, 12.5_

### Implementación de la US4

- [ ] T072 [US4] `api/console/teammates.py`: `POST`, `PATCH`, `DELETE /console/teammates/{id}`
      (T070 en verde); `GET /jobs` devuelve también los modelos de `partner_model_allowlist`
      con `note` y `cost_label`. _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.6_
- [ ] T073 [P] [US4] Proxies BFF `api/teammates/[id]/route.ts` (PATCH, DELETE). _Requisitos: 12.3_
- [ ] T074 [US4] Renderer `routes/new-teammate.tsx` (nombre, oficio con semilla editable,
      modelo con nota y coste, cinco interruptores) y `routes/teammate-settings.tsx`
      (cambiar, archivar con confirmación); handlers `app:roster.create/update/archive`. _Requisitos: 2.1, 2.5, 2.6_

---

## Phase 7: User Story 5 — Cuánto me queda, el mismo número (P2)

**Goal**: Cuenta muestra el consumo con el mismo medidor que la consola, por
teammate, y la pausa por tope se pinta como estado.

### Tests de la US5 ⚠️

- [ ] T075 [P] [US5] `apps/api/tests/integration/test_teammates_usage.py`: `by_teammate`
      agrega `runs` del mes por `teammate_id`; `budget` idéntico a `/companion/budget`. _Requisitos: 8.1, 9.1_
- [ ] T076 [P] [US5] `apps/desktop/tests/account-usage.test.tsx`: Cuenta pinta el mismo número;
      con `exhausted` el hilo pasa a `en_pausa_por_tope` y el copy dice dónde se sube. _Requisitos: 8.1, 9.3_

### Implementación de la US5

- [ ] T077 [US5] `GET /console/teammates/usage` en `api/console/teammates.py` (D14). _Requisitos: 8.1, 9.1_
- [ ] T078 [P] [US5] Proxy BFF `api/teammates/usage/route.ts`. _Requisitos: 12.3_
- [ ] T079 [US5] Renderer `routes/account.tsx`: uso del mes y por teammate, equipo con roles
      (solo lectura, los cinco del código), «Abrir la consola», «Cerrar sesión» (el de 002);
      handler `app:usage`; `budget.paused` → estado del hilo. _Requisitos: 8.1, 8.2, 8.3, 9.3_

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T080 [P] Panel de entorno `routes/thread.tsx` §Entorno: máquina, presencia, directorio
      del cliente, `archivos` tocados en la tarea (de `exec.*`, solo nombres), `navegador` como
      ausencia diseñada, enlace a la puesta en marcha de 002 si falta máquina o directorio;
      handler `app:env.forThread`. _Requisitos: 11.1, 11.2, 11.3, 11.4_
- [ ] T081 [P] Comportarse como app: `apps/desktop/src/electron/{single-instance, window-state,
      tray}.ts` (instancia única con `requestSingleInstanceLock`, ventana que recuerda su sitio
      en `userData`, icono de bandeja con el conteo, atajo global configurable); tests puros
      `window-state.test.ts`, `tray-badge.test.ts`. _Requisitos: 12.4_
- [ ] T082 [P] Auditorías del workspace sobre `apps/desktop/src/app` y `packages/companion-ui`:
      `ui-states-checklist` → `a11y-audit` → `responsive-audit` → `design-tokens`; cero 🔴;
      sin `fg-subtle` en texto legible ni aviso con texto claro. Evidencia en `evidence/T082/`. _Requisitos: 12.5_
- [ ] T083 [P] Notas de sustitución: `specs/001-puesto-trabajo-partner/spec.md` R15.1 y
      `specs/002-identidad-app-escritorio/spec.md` R12.1 («superado por specs/003»);
      `contracts/device-bridge-v2.md` de la 002 apunta a `local-dispatch.md`. _Requisitos: §Spec viva_
- [ ] T084 [P] Spec viva: `docs/desktop-teammates.md` (la pantalla, el canal IPC, la tarea,
      la política en tres capas, el despacho) y actualización de `docs/desktop-workstation.md`
      (cuatro particiones, `work[]`); `docs/companion/CONTRACT-V3.md` enlazado desde
      `docs/companion/README` si existe. _Requisitos: §Spec viva_
- [ ] T085 [P] Enlace de vuelta a la KB: `[[14-mvp-y-fases]]` §2 enmendado («dentro de la
      app») y §7 decisión 4; `[[10-decisiones]]` decisiones 13 y 14; `[[00-revision-del-diseno-v3]]`
      §5.1 cerrado. _Requisitos: §IX_
- [ ] T086 Ejecutar `quickstart.md` completo (§1–§5) con una persona ajena al equipo para
      CE-009; evidencia en `evidence/T086/`. CE-001 queda condicionado a la spec 004 y se
      anota así. _Requisitos: CE-001 … CE-011_

---

## Dependencies & Execution Order

### Orden de fases

- **Phase 0** (T001) → **Phase 1** (T002–T006 en paralelo) → **Phase 2** (tests
  T007–T011 en paralelo → T012 → T013 → T014, T015 → T016 → T017 → T018 → T019 →
  T020) → **Phase 2b** (T021 → T022 → T023) → **Phase 2c** (T024, T025) → US1 → US2
  → US3 → US4 → US5 → Polish.
- **US1** necesita Phase 2 (roster, eje) y 2b (el paquete).
- **US2** necesita US1 (un hilo que aparcar y una pantalla donde verlo).
- **US3** necesita US2 (la tarea que espera y el nivel `critico`) y la 002 (máquina
  presente con directorio).
- **US4** necesita US1; **US5** necesita US1 y T025.
- **Polish** T080 necesita US3; T081 y T082 pueden ir desde US1.

### Paralelismo

- Phase 1 entera en paralelo. Los cinco tests de la Phase 2 en paralelo **antes**
  de T012. Dentro de cada historia todos sus tests en paralelo; API y escritorio
  en paralelo una vez la API de la historia está (T033 → T034–T038; T047–T051 →
  T052–T054; T061–T066 → T067–T069).

---

## Implementation Strategy

### MVP — US1 + US2 + US3

Un roster con hilo (US1) sin tarea que espera (US2) miente al cerrar la app; y
sin ejecutar en la máquina (US3) es la consola con otra cara. Las tres P1 juntas.

### Entrega incremental

1. Phase 0–2c → eje teammate en plataforma, paquete compartido, puertas.
2. + US1 → roster e hilo en la app. Demo.
3. + US2 → cerrar la app y volver; Pendientes; avisos. Demo.
4. + US3 → ejecutar en la máquina con política. **Entregable.**
5. + US4, US5 → crear teammates y ver el consumo.
6. Polish → app de verdad, docs, KB, quickstart.

---

## Cobertura por capacidad

| Requisito | Qué se puede hacer que antes no | Test que lo vio en rojo | Tarea que lo construye |
|---|---|---|---|
| 1.1–1.5 | Roster por partner, leído por persona con estado derivado; sin `personal/team`; vacío diseñado | T007, T026 | T012, T014, T016, T033, T040 |
| 2.1–2.6 | Crear/cambiar/archivar desde la app; subconjunto del catálogo; nota en hilos; nunca borrar | T009, T070, T071 | T017, T072, T074 |
| 3.1–3.7 | Hilo de teammate y persona, en plataforma, con estados nombrados y máquina ausente diseñada; formas de mensaje | T008, T030, T031, T042, T056 | T018, T038, T040, T050, T065, T069 |
| 4.1–4.3 | Catálogo por teammate en lo que ve el modelo | T009 | T017, T018 |
| 5.1–5.5 | Pendientes de la persona, solo teammates, sincronía < 2 s, `can_decide`, vacío | T043, T046 | T051, T053, T054 |
| 6.1–6.4 | La aprobación espera a la tarea; `esperandote`; Companion web sin cambios | T042, T011 | T047, T048, T049, T050 |
| 7.1–7.5 | Tres niveles; aviso del SO; resumen al abrir; sin correo; silenciar sin subir | T044, T045 | T049, T053 |
| 8.1–8.4 | Cuenta: mismo número, por teammate; equipo; consola; política visible | T075, T076, T057 | T077, T079, T069 |
| 9.1–9.3 | Un solo medidor y camino; pausa por tope como estado | T025, T076 | (no-regresión) T050, T079 |
| 10.1–10.7 | Tres capas, la más restrictiva gana, tarjeta con comando, nunca amplía, auditado | T055, T057, T058, T060 | T061, T063, T066, T067, T069 |
| 11.1–11.4 | Panel de entorno; archivos; navegador ausente; puesta en marcha | T056 (11.1) | T080 |
| 12.1–12.6 | Segunda superficie con canal enumerado y sin credenciales; consola sin canal; app de verdad; AA y tokens; sin duplicar consola | T027, T028, T029, T032, T082 | T035, T036, T037, T039, T081, T082 |
| 13.1–13.2 | Ocho actos auditados con persona; sin cuerpos | T010, T070, T057 | T013, T063, T066, T072 |
| 14.1–14.3 | 001/002 en verde; ambiente sin acceso nuevo; consola sin teammates | T024, T032, T055 | T020, T023, T018 |

Ningún requisito aparece **solo citado**. Si `/speckit-analyze` encuentra uno,
la tabla está mal y se corrige antes de implementar.
