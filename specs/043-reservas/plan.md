# Plan de implementación: 043 — Reservas

**Rama**: `043-reservas` | **Fecha**: 2026-10-22 | **Spec**: [spec.md](spec.md)

## Resumen

Un dominio nuevo (`services/reservations/`) con su modelo (siete tablas por
cliente, RLS FORCE, FK compuestas), un motor puro de disponibilidad para los dos
modos que usan por igual la API, las herramientas y el worker, la API
`/console/lite/reservas/*` (web y app), las herramientas `reservas.*` del agente,
cuatro crons y las pantallas de Reservas de la consola customers en los dos
modos. El admin activa el módulo y el modo en la pestaña Acceso. Google Calendar
va al final, en su propia migración y su propio cron.

## Contexto técnico

**Lenguaje/versión**: Python 3.12 (FastAPI, SQLAlchemy 2 async, Alembic) · TypeScript 5.9 / Next.js 16 / React 19.2

**Dependencias**: ninguna nueva (P3 usa el cliente del proveedor de consentimientos que ya existe).

**Almacenamiento**: PostgreSQL 16. Migraciones `0172`–`0174`.

**Pruebas**: pytest (unit del motor, integración de API/herramientas/crons, isolation) · vitest · Playwright + axe.

**Restricciones**: sin `btree_gist` (Aurora); la exclusión de solapes es por
candado de transacción + revalidación. Toda hora de negocio en
`tenants.timezone`.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | RLS FORCE + FK compuestas; `test_21` y `test_22` cubren las tablas nuevas; `tests/isolation/test_reservas_client_vs_client.py` (barrido 404 idéntico de cada ruta con id del vecino), `test_reservas_customer_axis.py` (el agente solo lo suyo), `test_reservas_route_scope.py` (partner y cliente sin módulo: 403) |
| II | Superficie | ☑ | `0`. P3 por el proveedor de consentimientos existente; las herramientas de Google del agente siguen bloqueadas |
| III | Lo leído es dato | ☑ | La nota de la reserva y el «ocupado» de Google son datos; ningún texto del cliente final llega al prompt por esta vía salvo la conversación misma |
| IV | Acción `mutates` | ☑ | Activar Reservas **prepara** versiones del agente, no las promueve; cada acción de la agenda audita a la persona (evento con nombre) |
| V | Estados honestos | ☑ | «No se pudo avisar» en el historial; `hours_missing`; sin botones apagados (`allowed`); cinco estados por vista |
| VI | Por API | ☑ | El agente opera con herramientas propias; nadie navega la consola |
| VII | Test primero | ☑ | Motor de disponibilidad con pruebas unitarias de la tabla del diseño; concurrencia; cada criterio en `tasks.md` |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | KB | ☑ | `[[research/2026-10-22-reservas-y-consola-customers/_index]]` |

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | Garantía 1 (tablas nuevas, agenda de todo el negocio), 2 (lista blanca preparada, no promovida), 8 (cliente final) | T010, T030, T031, T032 |
| **Licencias** | Ninguna | — |
| **Medidor** | Los mensajes salientes de Reservas entran como salientes del cliente por el despachador de siempre (se envían como `messages`) | T042 |

## Diseño

### Motor (`apps/api/src/nexus_api/services/reservations/`)

- `engine.py` — **puro**: franjas de un día (turnos/franjas), presencia, `fits`
  de Aforo; huecos de Servicios (intersección horario negocio ∩ persona, menos
  reservas vivas, ofertas en curso y «ocupado»), `first_fit`. Sin base de datos.
- `repo.py` — lecturas por rango (reservas vivas de un día, bloqueos, ofertas),
  siempre bajo la sesión del cliente (RLS).
- `service.py` — casos de uso (crear, mover, cancelar, transiciones, walk-in,
  bloqueos, lista de espera, ofertas) con candado + revalidación, eventos,
  outbox y push. Lo llaman la API, las herramientas y el worker.
- `settings.py` — valores de partida por modo y tipo; validación de rangos.
- `serializers.py` — `Booking` del contrato (incluido `allowed`, `local`,
  `late_minutes`).

### API

`apps/api/src/nexus_api/api/console/lite/reservas.py` (+ `reservas_schemas.py`),
todas con `lite_scope("reservas")`. `/me`, el detalle de la Bandeja y
`/phones/current/notices` ganan lo del contrato. El admin
(`api/admin/client_access.py`, `services/client_access.py`) gana `reservas`.

### Agente

`apps/mcp/src/nexus_mcp/servers/reservas/` (schemas, tools) sobre el mismo
`service.py`. Registro, catálogo (`0173`), nombres de negocio, intención
`book`/`info`. Activar/desactivar el módulo prepara versiones del agente con
`AgentConfigService.stage_new_version` por agente activo.

### Worker

`apps/worker/src/nexus_worker/streams/reservations_cron.py`,
`reservation_outbox_cron.py`, `reservation_offers_cron.py`,
(`reservation_calendar_cron.py` P3). Envío por `messages` con
`template_payload` (fuera de ventana) o texto (dentro), como
`cobranza_reminder_cron`.

### Consola

`apps/console/src/app/(console)/reservas/` (página, `loading.tsx`, `error.tsx`,
`actions.ts`) y `apps/console/src/components/reservas/`: shell de la pantalla
(pestañas, vista/periodo, navegación de fechas), **Servicios** (cuadrícula día
por profesional, semana de una persona, mes; lista con filtros; detalle lateral;
nueva/mover; cancelar con oferta; lista de espera y ofertas; ajustes: equipo,
servicios, horario, recordatorios), **Aforo** (mapa de ocupación; lista por hora
con Llegó/No vino/Deshacer; panel de la hora; llegada sin reserva; bloqueos;
lista de espera; ajustes). Panel: bloque de Reservas y fila de atención.
Módulo `reservas` en `principal-access.ts`, `lite-nav.ts`.

### Admin

`apps/admin/src/app/(dashboard)/tenants/[id]/access/`: módulo Reservas con modo
y tipo, diálogo de reservas vivas, aviso de versiones por promover.

## Estructura

```text
apps/api/alembic/versions/0172_reservations_schema.py, 0173_reservations_tools.py,
  0174_reservation_calendars.py (P3)
apps/api/alembic/data/0173_reservations_tools.json
apps/api/src/nexus_api/db/models/reservation.py
apps/api/src/nexus_api/services/reservations/{__init__,engine,repo,service,settings,serializers,agent_versions}.py
apps/api/src/nexus_api/api/console/lite/{reservas,reservas_schemas}.py
apps/mcp/src/nexus_mcp/servers/reservas/{__init__,schemas,tools}.py
apps/worker/src/nexus_worker/streams/reservation_*.py
apps/console/src/app/(console)/reservas/**, components/reservas/**
apps/admin/src/app/(dashboard)/tenants/[id]/access/**
docs/reservas.md (nuevo), docs/consola-lite.md, docs/admin.md
```

## Complexity Tracking

| Añadido | Por qué |
|---|---|
| Tabla `reservations` nueva en vez de ampliar `appointments` | `appointments` la leen AgendaPro, comisiones y el historial del cliente con sus estados; cambiarlos rompería esos flujos |
| Outbox propio (`reservation_outbox`) | «Una sola vez por reserva y tipo» y el «no se pudo avisar» del historial necesitan una fila con estado; `scheduled_jobs` no lleva reserva ni deduplicación |
| Candado de transacción en vez de `EXCLUDE` | El aforo es una suma (no se expresa con `EXCLUDE`) y `btree_gist` no está garantizado en Aurora |
