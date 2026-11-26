# Implementation Plan: El agente tras el traspaso y la disponibilidad

**Branch**: `080-agente-tras-el-traspaso` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/080-agente-tras-el-traspaso/spec.md`

## Summary

Hay cuatro cambios pequeños en el runtime del turno y en las herramientas `reservas.*`. Ninguno abre superficie, migra datos ni añade llamadas al modelo.

1. **El freno de citas** (`runtime/booking_brake.py`) suma una fuente de respaldo: una reserva viva del `customer_id` de la conversación con un evento `created` o `moved` desde el inicio del ciclo (`coalesce(context_from, attended_at)`). Ese cliente lo lee el servidor de la fila de la conversación.
2. **El mapa de herramientas por intención** (`runtime/pipeline.py`, `_INTENT_CATEGORIES`) añade las herramientas `reservas.*` a `fallback` y a `escalate`. El techo sigue siendo la lista blanca del agente.
3. **`reservas.find_slots`** acepta no recibir `date`. En ese caso recorre los días desde hoy, en la zona del negocio, hasta juntar 6 horarios o agotar `agent_max_days_ahead`, y cada horario lleva su `date` y su `weekday`. El simulador del Playground hace lo mismo.
4. **`reservas.cancel`** registra el evento con `Actor("agent", <nombre>)` y sigue con `by="customer"`.

## Technical Context

**Language/Version**: Python 3.11 (API, worker y MCP con uv).

**Primary Dependencies**: FastAPI, SQLAlchemy async, LangGraph (runtime) y el registro MCP propio (`nexus_mcp`). No entra ninguna dependencia nueva.

**Storage**: PostgreSQL con RLS. Solo hay lecturas nuevas (`reservations`, `reservation_events` y `conversations`) dentro de la sesión del cliente. No hay migración.

**Testing**: pytest.
- Unitarias del worker: `apps/worker/tests/unit`.
- Integración de la API, que incluye las herramientas MCP sobre base real: `apps/api/tests/integration/reservas`.
- Aislamiento: `apps/api/tests/isolation`.
- La base es propia: `nexus_test_080`, Redis 10.

**Target Platform**: los servicios `runner` (worker) y `api` en ECS. Las herramientas MCP corren dentro del runner.

**Project Type**: web service multi-tenant (runtime de agentes).

**Performance Goals**: buscar sin fecha encuentra en un solo turno lo que hoy cuesta hasta 6 llamadas a la herramienta. En el peor caso, con la agenda vacía en toda la ventana, recorre `agent_max_days_ahead` días (60 por defecto) y debe tardar menos de 1,5 s pidiendo un profesional concreto del fixture de pruebas. Es el peor caso por consulta: un servicio de 8 h que no cabe en sus tramos de 5 y 6 h. Lo mide T008. Con «cualquiera», cada día lee a todo el equipo: el coste crece con el número de profesionales y no se ha medido con equipos grandes.

**Constraints**: el freno sigue cerrado ante cualquier error: si no puede leer, no respalda. No se cambia la forma de `find_slots` con fecha (requisito 3.5).

**Scale/Scope**: unos 6 ficheros de código y sus pruebas.

## Constitution Check

*PUERTA: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto; whitelist exhaustiva | ☑ | **Garantía 8.** El `customer_id` sale de la fila `conversations` leída con RLS, nunca de los argumentos ni del modelo. Lo prueba `tests/isolation/test_080_booking_brake_customer_cycle.py` (T004), que barre la reserva de otro cliente final, la de otro tenant, la cancelada, la de antes del ciclo y un turno sin conversación. **Garantía 2.** `_filter_tools_for_intent` solo intersecta con `bundle.tools`, y lo prueba T007, que barre todas las intenciones. |
| II | Corte por superficie de confianza | ☑ | Superficie `0`, ya abierta: el runtime y `reservas.*`. |
| III | Lo leído es dato, nunca instrucción | ☑ | No cambia el canal de instrucciones. La nota del freno sigue como `system`. La descripción de `find_slots` es texto de plataforma. |
| IV | Acción `mutates` con aprobación durable | ☑ | No hay acciones nuevas. Cancelar ya existía y pasa a registrar al agente como autor (más trazabilidad, no menos). |
| V | Estados honestos; la ausencia se diseña | ☑ | Buscar sin fecha sin resultado dice `why_closed="none_in_window"` en vez de inventar. Ofrecer herramientas en más intenciones no promete nada nuevo al cliente. |
| VI | Por API, nunca navegando la consola | ☑ | No aplica: no hay agente operando la plataforma. |
| VII | Test primero; criterio = test | ☑ | Cada criterio tiene su prueba en `tasks.md` y se ve en rojo antes de implementar. |
| VIII | Licencias | ☑ | Ninguna dependencia nueva. |
| IX | La KB es dueña del porqué | ☑ | `[[research/2026-11-26-beta-jemma-p0-p1]]`. Esa nota enlaza esta carpeta (T016). |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento**: ¿qué garantías toca? | **8**: el freno lee las reservas del cliente de la conversación. **2**: más intenciones reciben herramientas. | T002 en `tests/isolation/test_080_booking_brake_customer_cycle.py`. T005 (barrido de intenciones contra la lista blanca, unitario del worker) y la suite existente `test_45_tools_only_from_activations.py`, que se vuelve a correr (T015). |
| **Licencias**: ¿qué dependencia nueva entra? | Ninguna. | — |
| **Medidor**: ¿qué gasta y dónde lo ve el partner? | No hay llamadas nuevas. `fallback` y `escalate` llevan más definiciones de herramientas: son tokens de entrada, casi todos en caché, que se cobran en la bolsa del cliente como cualquier turno (`usage.published`). | T007 lo deja documentado en `docs/agentes.md`. |

**Complejidad que hay que justificar:** ninguna fuera de la spec.

## Project Structure

### Documentation (this feature)

```text
specs/080-agente-tras-el-traspaso/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── booking-brake.md
│   └── reservas-find-slots.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/worker/src/nexus_worker/runtime/
├── booking_brake.py          # R1: respaldo por cliente y ciclo
└── pipeline.py               # R2: _INTENT_CATEGORIES (fallback, escalate)
apps/worker/src/nexus_worker/simulation/
└── registry.py               # R3: find_slots sin fecha en la agenda simulada
apps/mcp/src/nexus_mcp/servers/reservas/
├── schemas.py                # R3: date opcional, SlotOut.date/weekday, why_closed
└── tools.py                  # R3: FindSlots sin fecha · R4: Cancel con Actor("agent")
apps/api/tests/isolation/test_080_booking_brake_customer_cycle.py   # R1 · garantía 8
apps/api/tests/integration/reservas/test_080_find_slots_sin_fecha.py
apps/api/tests/integration/reservas/test_080_cancel_del_agente.py
apps/api/tests/integration/test_booking_brake_turn.py   # + el caso de acrílicos de punta a punta
apps/worker/tests/unit/test_intent_tool_filter.py       # R2
apps/worker/tests/unit/test_simulated_find_slots.py     # R3 en la agenda simulada
docs/agentes.md · docs/reservas.md                      # spec viva, en el mismo commit
```

**Structure Decision**: el código vive en los ficheros que ya implementan cada pieza. `core.py` de Reservas no se toca: lo usan las sesiones 082 (aviso `reservations.changed`) y 083. La búsqueda por días se compone en la herramienta, encima de `services_free` y `capacity_day`, que ya existen.

## Complexity Tracking

Sin violaciones.
