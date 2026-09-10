# Implementation Plan: los teammates viven en la aplicación de escritorio

**Branch**: `003-teammates-app-escritorio` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: `specs/003-teammates-app-escritorio/spec.md` (14 requisitos, CE-001…CE-011) y la
Opción A de `.specify/assessments/teammates-en-la-app/`.

## Summary

La aplicación de escritorio gana su pantalla de operar —roster, hilo por
teammate, Pendientes, Cuenta, Crear teammate— como **renderer propio** (React,
Vite, `@nexus/ui`) en una tercera vista de la ventana, con `preload` mínimo y un
canal IPC enumerado; el proceso principal habla con el BFF de la consola con la
sesión de la persona y reenvía los *streams*. En la plataforma, el loop del
Companion gana el eje **teammate** (roster por partner, hilo con `teammate_id`,
catálogo por teammate), la **tarea** como objeto durable que encadena turnos y
cuya aprobación espera, el **nivel de aviso**, la **política de ejecución local
en tres capas**, y **el despachador de trabajo local** que la 001 dejó
declarado y vacío (`/device/poll` → `work=[]`). El Companion de la consola se
extrae a `packages/companion-ui` para que las dos pantallas compartan
componentes. Un solo loop, un solo medidor, cero credenciales nuevas.

## Technical Context

**Language/Version**: Python 3.11 (API), TypeScript 5.7 (consola, escritorio, paquete compartido), Node 22.

**Primary Dependencies**: FastAPI · SQLAlchemy async · Alembic · Redis (streams y pubsub) · LiteLLM por `llm_proxy` — sin cambios. Consola: Next.js 16, React 19, `@nexus/ui`. Escritorio: Electron 44.3.0 (ya), **React 19.2 + Vite 7.3 + `@vitejs/plugin-react`** (nuevos en `apps/desktop`; ya presentes en el workspace raíz, MIT). Paquete nuevo `@nexus/companion-ui` (React + tokens, sin `next`).

**Storage**: Postgres con RLS (tablas nuevas: `teammates`, `teammate_tasks`, `partner_local_exec_policy`, `principal_local_exec_prefs`; columnas nuevas en `threads`, `runs`, `actions`; filas nuevas del vocabulario de auditoría) · Redis (`local_exec:{execution_id}` para el resultado del despacho; canal por persona para la bandeja) · `userData` de Electron para el estado de ventana (sin datos de negocio).

**Testing**: pytest (unit, integration, `tests/isolation/` bloqueante) · vitest + jsdom (consola y paquete) · vitest (escritorio, módulos puros) · las cuatro auditorías estáticas de UI.

**Target Platform**: macOS y Windows (escritorio); la firma, la notarización, la actualización y la contención en Windows son la **spec 004**.

**Project Type**: monorepo — API + consola + escritorio + paquete compartido.

**Performance Goals**: decidir en una vista actualiza la otra en < 2 s (CE-003); el roster y la bandeja cargan en < 1 s con 50 teammates y 200 pendientes; el *stream* de un hilo llega al renderer con < 300 ms de retraso añadido por el salto IPC.

**Constraints**: el renderer no tiene credenciales (CE-007); la app no puede ampliar la lista blanca ni el techo (CE-008); un solo medidor (CE-006); la vista de la consola sigue sin `preload` (002-R14); un run del Companion hoy muere a los 300 s (`companion_run_max_seconds`) y una herramienta a los 10 s (`companion_tool_timeout_s`): la ejecución local necesita sus propios techos (research D6).

**Scale/Scope**: por partner, decenas de teammates y cientos de tareas al mes; 5 pantallas + 2 overlays en el renderer; ~20 componentes portados; 4 tablas y 6 rutas nuevas en la API; 6 rutas BFF de proxy en la consola; 1 control nuevo en la página de equipo.

## Constitution Check

*PUERTA: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.
Una fila en rojo detiene el plan: se corrige el diseño o se enmienda la constitución.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | `teammates` y las políticas son tablas **de partner** con RLS por `app.partner_id` (como `partner_devices`); el hilo sigue con RLS por `principal_id` (0090) y gana `teammate_id` sin tocar la política; el catálogo por teammate es un **subconjunto** de `ALL_TOOLS` y se comprueba en lo que recibe el modelo. Tests: `tests/isolation/test_31_teammate_roster_scope.py`, `test_32_teammate_thread_two_axes.py`, `test_33_teammate_catalog_is_subset.py`, `test_34_local_policy_cannot_widen.py` |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficies `0` y `3a`, ya abiertas. El renderer nuevo no es superficie del agente: no ejecuta, no lee ficheros, no tiene credenciales (contrato `desktop-app-ipc.md`, test `no-credentials-over-ipc`) |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | La muestra de salida de un comando entra al hilo como **resultado de herramienta marcado como contenido no confiable** (research D7), nunca en el prefijo del sistema; la auditoría sigue sin guardarla. No hay navegador en esta spec (R11.3 lo pinta como ausencia) |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Se conserva todo (durable, idempotente, 409). **Enmienda acotada**: para acciones de teammate `expires_at` es NULL y la vida la fija la **tarea** (`teammate_tasks.expires_at`); la caducidad por reloj de las acciones del Companion no cambia (research D3). Auditoría: filas nuevas con `{actor}` = persona, nunca el teammate |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Estados del hilo y de la tarea enumerados en `data-model.md`; `máquina ausente` y `navegador` son ausencias diseñadas; `esperándote` es un estado, no un timeout |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | El teammate usa el mismo toolbelt `console.*` del Companion; la app tampoco «navega» la consola para operar: el proceso principal llama al BFF |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada requisito lleva su test en `tasks.md`; las cuatro garantías tocadas tienen test de aislamiento escrito **antes** de la implementación |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | Dependencias nuevas en `apps/desktop`: `react`, `react-dom` (MIT), `vite`, `@vitejs/plugin-react` (MIT) — ya en el workspace raíz, leídas en `research.md` §Licencias. Ninguna otra |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[10-decisiones]]` §1 (+13, +14), `[[14-mvp-y-fases]]` §2 enmendado, `[[00-revision-del-diseno-v3]]` §3–§5; el plan devuelve tres notas a la KB (tasks, fase final) |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | **1** (RLS: roster por partner, hilo con dos ejes), **2** (whitelist: catálogo por teammate; política que solo restringe), **3** (env aislado: la política no amplía; la salida es dato), **6** (auditoría con la persona) | `T0xx` en `tests/isolation/test_31…test_34` + `no-credentials-over-ipc` en el escritorio |
| **Licencias** — ¿qué dependencia nueva entra? | `react@19.2` MIT · `react-dom@19.2` MIT · `vite@7.3` MIT · `@vitejs/plugin-react` MIT. Párrafos citados en `research.md` §Licencias. **Nada de KiroCrew entra** (se copian decisiones, no ficheros) | `T0xx` (la tarea de licencias en `tasks.md`) |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Modelo**: el mismo camino (`llm_proxy_partner_scope` → LiteLLM → wallet), atribuido por teammate vía `runs.teammate_id`; **ejecución local**: `meter_local_model_use` de la 001, sin cambios. Lo ve en Cuenta (app) y en Consumo (consola) con el **mismo** `budget_out` | `T0xx` test «un solo número» |

**Complejidad que hay que justificar:** ver Complexity Tracking.

## Constitution Check — vuelta a comprobar tras el diseño

Tras `research.md`, `data-model.md` y los contratos:

- **I**: la RLS de `teammates` por partner deja fuera al `analyst`/`billing` de crear (permiso `teammates:use` = owner/admin/builder, como `companion:use`); el `LEFT JOIN` de la bandeja filtra por `threads.principal_id` — no por `teammate_id`. ☑
- **II**: apareció una tentación y se rechazó: que el renderer abriera el SSE directamente contra el BFF con las cookies de la partición de la consola. Habría puesto cookies al alcance de un renderer con `preload`. El *stream* pasa por el proceso principal (research D9). ☑
- **III**: `stdout_sample` viaja en `ResultIn` (≤ 2 KB) y termina en `messages.tool_calls[].result` con `untrusted: true`; **no** en `local_executions`. ☑
- **IV**: `actions.expires_at` NULL solo cuando `thread.teammate_id IS NOT NULL` (CHECK). ☑
- **VII**: los cuatro tests de aislamiento se escriben en la Fase 1 de `tasks.md`, antes de cualquier migración. ☑

Ninguna fila cambia de color. El plan pasa.

## Project Structure

### Documentation (this feature)

```text
specs/003-teammates-app-escritorio/
├── plan.md
├── research.md              # D1–D15
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── teammates-api.md     # /console/teammates/* y /console/companion/* que cambia
│   ├── local-dispatch.md    # puente v3: work[] y stdout_sample
│   ├── teammates-events.md  # CONTRACT-V3: 4 eventos nuevos, 1 ampliado
│   ├── desktop-app-ipc.md   # el canal enumerado del renderer
│   └── companion-ui.md      # la API del paquete compartido
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   ├── 0109_teammates.py                  # teammates, threads.teammate_id, runs.teammate_id, RLS
│   ├── 0110_teammate_tasks.py             # teammate_tasks, actions.level, actions.expires_at NULL para teammate
│   ├── 0111_local_exec_policy.py          # partner_local_exec_policy, principal_local_exec_prefs, denial 'politica_nunca'
│   └── 0112_teammate_audit_vocab.py       # filas del vocabulario
├── src/nexus_api/
│   ├── db/models/{teammate.py, local_workstation.py (+policy), companion.py (+cols)}
│   ├── repositories/{teammates.py, teammate_tasks.py, local_exec_policy.py}
│   ├── services/{teammate_catalog.py, local_exec_gate.py (+capas), local_dispatch.py, teammate_inbox.py}
│   ├── companion/tools/{catalog.py (+shell_local spec), local_exec.py (la herramienta)}
│   ├── api/console/{teammates.py, schemas_teammates.py, companion.py (+eje), team.py (+techo)}
│   ├── api/{device_bridge.py (poll work[], result stdout_sample), companion_streaming.py (+eventos v3)}
│   └── core/console_auth.py               # teammates:use, teammates:policy
└── tests/{isolation/test_31…34, integration/test_teammates_*.py, unit/…}

packages/companion-ui/                     # NUEVO — extraído de apps/console/src/components/companion
├── src/{state.ts, types.ts, transport.ts, use-companion.ts, i18n.ts, messages/{es,en}.ts}
├── src/components/{timeline, confirm-card, composer, meters, thinking, verify-table, intake-card, plan-card, tool-card, support}.tsx
└── tests/

apps/console/
├── src/components/companion/{drawer, companion-launcher, trial-panel, page-context}   # se quedan; importan del paquete
├── src/app/api/teammates/**/route.ts      # proxies BFF (roster, tasks, inbox, prefs, usage, streams)
├── src/app/(console)/team/…               # techo de ejecución local (team:manage)
└── src/lib/backend/teammates.ts

apps/desktop/
├── package.json                           # + react, react-dom, vite, @vitejs/plugin-react; entra en el workspace raíz
├── vite.app.config.ts                     # renderer → dist/app/
├── src/app-ipc.ts                         # el contrato enumerado (canales + formas)
├── src/platform-client.ts                 # llama al BFF con la sesión (session.fromPartition().fetch)
├── src/sse.ts                             # parser SSE puro
├── src/app-state.ts                       # roster/bandeja/estado de tarea (puro)
├── src/notifications-policy.ts            # niveles → aviso del SO / bandeja (puro)
├── src/electron/{main.ts (+appView, tray, single instance, window-state), app-preload.ts}
├── src/app/                               # el renderer React: routes roster/thread/inbox/account/new-teammate
└── tests/{app-ipc, no-credentials-over-ipc, platform-client, sse, app-state, notifications-policy, …}
```

## Complexity Tracking

| Añadido que la spec no pedía literalmente | Por qué | Alternativa rechazada |
|---|---|---|
| **`teammate_tasks`** como objeto durable que encadena runs | R3.2 y R6 exigen que el trabajo y la aprobación sobrevivan al run; hoy un run muere a los 300 s y un aparcado más viejo se considera muerto (`_is_expired`). Sin tarea, «espera a la tarea» no tiene sujeto | Subir `companion_run_max_seconds` a días: un run en proceso de un despliegue rodante no sobrevive; sería mentir |
| **Despachador de trabajo local** (`work[]`, `stdout_sample`) | CE-001 exige que un teammate lea y escriba en la carpeta; la 001 dejó el `poll` vacío a propósito. Es la pieza que falta, no un extra | Ejecutar por la edición (Opción B): rechazada en la evaluación |
| **Proxies BFF en la consola** para teammates | El renderer no puede acuñar tokens de 60 s (nunca tendrá la clave) y la API solo habla con tokens; el BFF ya es el único que acuña | Que el escritorio acuñe: rompe «la app no tiene credencial de backend» |
| **CONTRACT-V3** (4 eventos, 1 ampliado) | V2 fijó «veinte, ni uno más» con test; los teammates necesitan `task.state`, `exec.dispatched`, `exec.completed`, `inbox.changed` y `level` en `hitl.requested` | Reutilizar `phase.changed`: mentiría sobre lo que pasa |
| **`apps/desktop` entra en el workspace raíz** | Para consumir `@nexus/ui` y `@nexus/companion-ui` como dependencias de workspace | Publicar los paquetes: no hay registro; copiar: diverge (la barra ya lo enseñó) |

## Riesgo de plan, dicho una vez

- **Un run que espera un comando local ocupa un slot** (`companion_max_process_runs` = 12) durante toda la ejecución (hasta 10 min). En beta con pocos partners cabe; el plan añade un techo propio (`teammate_run_max_seconds`, `local_exec_wait_seconds`) y una métrica de slots ocupados por espera para verlo venir. La solución de fondo —el turno se cierra al despachar y la tarea lo reanuda al llegar el resultado— está en `research.md` D6 como camino de la fase siguiente si la métrica lo pide.
- **Portar el Companion a un paquete** toca 44 archivos con 12 tests; la consola tiene que seguir en verde a mitad de camino. Se hace en una fase propia, con la consola consumiendo el paquete antes de que el escritorio exista.
- **La spec 004 es condición de CE-001** (instalación limpia). Todo lo demás se verifica con `electron .` en desarrollo.
