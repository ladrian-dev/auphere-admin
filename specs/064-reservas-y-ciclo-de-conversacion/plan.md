# Implementation Plan: Reservas a tiempo y conversaciones con principio y fin

**Branch**: `064-reservas-y-ciclo-de-conversacion` | **Date**: 2026-11-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/064-reservas-y-ciclo-de-conversacion/spec.md`

## Summary

Cinco requisitos sobre código que ya existe, sin superficie ni dependencia nueva:

1. **Antelación del agente.** El ajuste ya existe y la API ya lo guarda. Se
   acota a siete valores, se añade su control en los Ajustes de la consola, y
   `reservas.find_slots` devuelve aparte las horas libres que el agente no puede
   dar (`too_soon`), con la instrucción de qué decir.
2. **«Atendida».** `allowed_actions` ofrece `noshow` sobre una `done` de
   Servicios durante 7 días, y `undo` de vuelta a `done`. La pantalla de Reservas
   relee sola cada 45 s con la pestaña visible, y dice cuándo no está al día.
3. **Teléfono.** Obligatorio y validado en los dos diálogos de reserva de la
   consola y en su acción de servidor. La API no cambia: la app de hoy sigue
   funcionando.
4. **Corte de contexto.** Dos columnas en `conversations`. Resolver marca el
   corte, y la reapertura por el contacto o por un aviso lo aplica. El worker lee
   desde ahí y añade una nota con el nombre del contacto.
5. **Cierre por inactividad.** Una columna en `client_access`, dos rutas de
   ajustes de la Bandeja, un cron nuevo en el planificador y su texto en el hilo.

Las decisiones y sus alternativas están en [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.11 (API, worker, herramientas) · TypeScript 5 con React 19 (consola)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic 2, LangGraph (worker) · Next.js 16 App Router, `@nexus/ui`, Zod. **Ninguna nueva.**

**Storage**: PostgreSQL con RLS FORCE por `tenant_id`. Una migración: `0236_context_cut_and_autoclose`.

**Testing**: pytest (API: `tests/unit`, `tests/integration`, `tests/isolation`; worker: `tests/unit`) · Vitest con Testing Library (consola)

**Target Platform**: AWS ECS (API, runner, planificador) · Vercel (consola)

**Project Type**: servicio web con worker y consola

**Performance Goals**: la relectura de la agenda repite cada 45 s, por pestaña visible, el cargador entero de la página: los ajustes y entre cuatro y siete lecturas más a la API, según el modo y la pestaña. El cron de cierre recorre los clientes cada 5 minutos, con una consulta por cliente con el ajuste puesto.

**Constraints**: la app móvil de hoy no se toca y tiene que seguir funcionando (la forma de `Booking` y de crear una reserva no cambian). Ningún cliente cambia de antelación al desplegar.

**Scale/Scope**: 5 requisitos, 42 criterios. Unos 25 archivos de código y 12 de pruebas, en `apps/api`, `apps/worker`, `apps/mcp` y `apps/console`.

## Constitution Check

*PUERTA: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | Garantías 1 y 8 rozadas. Los ajustes salen del contexto de la petición (`lite_scope`), nunca del cuerpo. Tests: `tests/isolation/test_064_context_and_autoclose.py` (4.7, 5.8) y `tests/isolation/test_reservas_customer_axis.py` (3.6). No se añade ninguna herramienta. |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie declarada en la spec: `0`. Todo vive en la API de la consola, las herramientas `reservas.*` y el runtime que ya existen. |
| III | Lo leído es dato, nunca instrucción | ☑ | El nombre del contacto viene de su perfil de WhatsApp. Entra en la nota saneado y recortado (research D4), y una prueba mete un nombre con instrucciones y saltos de línea. `too_soon` son horas, no texto libre. |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | No hay acciones de agente nuevas. La corrección de una cita la hace una persona en la consola y queda en el historial con su nombre (2.4). El ajuste de la Bandeja deja `inbox.settings_changed` con quién. El cierre por inactividad lo firma `system`. |
| V | Estados honestos; la ausencia se diseña | ☑ | La agenda dice cuándo no está al día en vez de pintarse como fresca (2.9). Sin Reservas o sin Bandeja no hay control (1, 5.7). La corrección solo aparece cuando la API la permite. |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | Ningún agente navega nada. |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada fase de `tasks.md` empieza por sus pruebas en rojo. |
| VIII | Licencias leídas enteras | ☑ | Dependencias nuevas: ninguna. |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[research/2026-11-18-reservas-y-ciclo-de-conversacion]]` |

**Después del diseño:** se mantiene. El diseño no añadió superficie, dependencia
ni herramienta.

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **8**, por el enlace de la reserva a su contacto (3.6) y por el contexto del turno (4.7). **1**, por el ajuste de cierre por cliente (5.8). | Una tarea de prueba por garantía y requisito en `tests/isolation/` |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna | No aplica |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | Nada nuevo. El corte quita mensajes de cada turno. | No aplica |

**Complejidad que hay que justificar:** ninguna fuera de la spec.

## Project Structure

### Documentation (this feature)

```text
specs/064-reservas-y-ciclo-de-conversacion/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/api-y-herramientas.md
├── checklists/requirements.md
└── tasks.md                       # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/0236_context_cut_and_autoclose.py   # nuevo
├── src/nexus_api/
│   ├── db/models/conversation.py            # context_from, cut_on_reopen
│   ├── db/models/client_access.py           # inbox_autoclose_hours
│   ├── services/reservations/settings.py    # NOTICE_MINUTES
│   ├── services/reservations/core.py        # allowed_actions, transition
│   ├── services/inbox_lifecycle.py          # resolve, reopen, punto de corte, close_inactive
│   └── api/console/lite/inbox.py            # GET y PATCH /inbox/settings
└── tests/{unit,integration,isolation}/      # test_064_*.py

apps/mcp/src/nexus_mcp/servers/reservas/
├── schemas.py                               # FindSlotsOutput.too_soon
└── tools.py                                 # find_slots parte los huecos

apps/worker/
├── src/nexus_worker/
│   ├── runtime/pipeline.py                  # _load_recent_history
│   ├── streams/inbox_autoclose_cron.py      # nuevo
│   └── bootstrap.py                         # el cron, en sus tres listas
└── tests/unit/                              # test_064_*.py, test_bootstrap_split.py

apps/console/src/
├── app/(console)/reservas/actions.ts        # antelación y teléfono
├── app/(console)/inbox/actions.ts           # ajustes de la Bandeja
├── lib/backend/                             # inboxSettings, inboxPatchSettings
├── components/reservas/
│   ├── model/phone.ts                       # nuevo: validPhone
│   ├── settings/shared-sections.tsx         # «Citas que da el agente»
│   ├── services/booking-dialog.tsx          # teléfono obligatorio
│   ├── capacity/capacity-booking-dialog.tsx # teléfono obligatorio
│   ├── booking-detail.tsx                   # undo → done si ya terminó
│   └── reservas-view.tsx                    # relectura y aviso de desactualizado
├── components/inbox/                        # diálogo de ajustes, event-text.ts
└── i18n/lanes/{reservas,inbox}.ts

docs/reservas.md · docs/consola-lite.md      # en el mismo commit que lo que describen
```

**Structure Decision**: no hay estructura nueva. Cada cambio va en el archivo
que ya tiene esa responsabilidad. Los tres archivos nuevos de código son la
migración, el cron y `model/phone.ts`.

**El código de `apps/mobile` no se toca.** Se regeneran tres archivos suyos,
porque la tubería comprueba que estén al día: `src/api/openapi.json` y
`src/api/schema.gen.ts`, por las dos rutas nuevas de ajustes de la Bandeja, y
`src/i18n/lite.gen.ts`, por los textos nuevos de la Bandeja.

## Orden de entrega

Cada historia se puede fusionar sola. El orden es el de la spec:

1. Historia 1, antelación (P1).
2. Historia 2, corregir y releer (P1).
3. Historia 3, teléfono (P2).
4. Historia 4, corte y cierre por inactividad (P3). El corte (requisito 4) va
   antes que el cierre (requisito 5), que lo usa.

## Complexity Tracking

No hay violaciones que justificar.
