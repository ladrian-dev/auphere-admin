# Tareas: spec 080, el agente tras el traspaso y la disponibilidad

**Entrada**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md) y [contracts/](contracts/).

**Reglas**:
- Primero la prueba: cada prueba se ve en rojo antes de su implementación.
- Base propia: `nexus_test_080`, Redis 10.
- Solo se corren las pruebas de lo tocado; nunca la suite completa.
- `[P]` = se puede hacer en paralelo con la anterior.

## Fase 1: Preparación

- [x] **T001** Exporta `NEXUS_DATABASE_URL` (`…/nexus_test_080`) y `NEXUS_REDIS_URL` (`…/10`), y comprueba que no hay ningún pytest vivo. Si las dependencias del worktree no están, `uv sync --extra dev` en `apps/api` y en `apps/worker`.

## Fase 2: Historia 1, el freno ve las reservas del cliente (P1)

- [x] **T002** Prueba de aislamiento `apps/api/tests/isolation/test_080_booking_brake_customer_cycle.py`, en rojo. Comprueba, con reservas hechas como las hace la consola (`origin=person`, sin `conversation_id`):
  - **Respalda:** una reserva viva del cliente de la conversación con un evento `created` en el ciclo.
  - **Respalda:** la misma situación con un evento `moved` en el ciclo.
  - **No respalda:**
    - la de otro cliente final del mismo tenant;
    - la de otro tenant;
    - la cancelada;
    - la creada antes de `context_from`;
    - una conversación sin `customer_id`.
  - El test 056 sigue en verde.

  _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5_
- [x] **T003** [P] Caso de acrílicos de punta a punta en `apps/api/tests/integration/test_booking_brake_turn.py` (`-k acrilicos`), en rojo. Una persona crea la reserva para el cliente, se devuelve la conversación y el cliente escribe «gracias». El freno no actúa y no hay paso a persona.

  _Requisitos: 1.1, 1.6, 2.1_
- [x] **T004** Implementa en `apps/worker/src/nexus_worker/runtime/booking_brake.py`:
  - `load_customer_backing(session, customer_id, since)`: reserva viva (`LIVE_STATUSES`) del cliente con un evento `created` o `moved` cuyo `created_at` sea mayor o igual que `since`.
  - En `conversation_backed`, leer `customer_id`, `attended_at` y `context_from` en la misma consulta, con el ciclo en `coalesce(context_from, attended_at)`.
  - Sin cliente o sin ciclo, no aplicar el paso nuevo.
  - Los fallos, cerrados como hoy.
  - T002 en verde.

  _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

## Fase 3: Historia 2, saludo y paso a persona conservan Reservas (P1)

- [x] **T005** En `apps/worker/tests/unit/test_intent_tool_filter.py`, en rojo:
  - `fallback` y `escalate` reciben las 9 `reservas.*` que tenga el agente.
  - Un agente sin Reservas no recibe ninguna.
  - `escalate.escalate_to_human` sigue en los dos.
  - Barrido: para cada intención de `VALID_INTENTS`, lo devuelto ⊆ `bundle.tools`.
  - Los conectores siguen fuera de `escalate`.

  _Requisitos: 2.1, 2.2, 2.3, 2.4_
- [x] **T006** En `apps/worker/src/nexus_worker/runtime/pipeline.py`:
  - Una tupla `_RESERVAS_TOOLS` con las 9 `reservas.*` de `book`, añadida a `_INTENT_CATEGORIES["fallback"]` y `["escalate"]`.
  - Actualizar el comentario de `_INTENT_MEANINGS`.
  - La clasificación no cambia.
  - T005 y T003 en verde.

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5_
- [x] **T007** En `docs/agentes.md`, la tabla de herramientas por intención y la nota del medidor: los turnos `fallback` y `escalate` de un agente con Reservas llevan más definiciones de herramientas y se cobran como cualquier turno.

  _Requisitos: 2.1, 2.2_

## Fase 4: Historia 3, buscar sin fecha (P1)

- [x] **T008** Crea `apps/api/tests/integration/reservas/test_080_find_slots_sin_fecha.py`, en rojo. El reloj se fija como en `test_064_notice.py`. Casos:
  - A las 13:24, con huecos desde la tarde, el primer horario es de hoy y lleva `date` y `weekday`.
  - A última hora, sin nada hoy, el primero es del siguiente día con hueco, y los días cerrados se saltan.
  - Tope de 6, en orden cronológico.
  - Profesional pedido.
  - Antelación: lo que cae dentro sale en `too_soon` con fecha.
  - Ventana sin nada: `why_closed=none_in_window`.
  - Servicio desconocido: `refused` igual que con fecha.
  - Aforo: cada horario lleva `left`.
  - Con fecha: no aparecen `date`/`weekday` por horario.
  - Peor caso (agenda llena, 60 días, 2 personas): menos de 1,5 s.

  _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5_
- [x] **T009** Implementa en `apps/mcp/src/nexus_mcp/servers/reservas/schemas.py` y `tools.py`:
  - `FindSlotsInput.date` pasa a opcional.
  - `SlotOut` gana `date` y `weekday`.
  - `FindSlotsOutput` gana `searched_from` y `searched_to`.
  - Nuevo valor `why_closed="none_in_window"`.
  - Recorrido por días con tope de 6 (research D4).
  - Descripción reescrita (D5).
  - T008 en verde, y también `test_tools.py`, `test_064_notice.py`, `test_reserva_por_nombre.py` y `test_datos_que_dejan_reservar.py`.

  _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
- [x] **T010** [P] Crea `apps/worker/tests/unit/test_simulated_find_slots.py`, en rojo: la agenda simulada acepta no recibir `date` y devuelve la misma forma (orden, tope, `date`/`weekday`, `none_in_window`).

  _Requisitos: 3.1, 3.2, 3.4_
- [x] **T011** Implementa en `apps/worker/src/nexus_worker/simulation/registry.py`: `_find_slots` sin fecha desde `world.now_at`, sobre `world.slots`. T010 en verde, y también las pruebas existentes del simulador que llaman a `find_slots`.

  _Requisitos: 3.1, 3.2, 3.4_

## Fase 5: Historia 4, la cancelación del agente queda a su nombre (P2)

- [x] **T012** Crea `apps/api/tests/integration/reservas/test_080_cancel_del_agente.py`, en rojo:
  - `reservas.cancel` deja el evento `cancelled` con `actor_kind=agent`, `actor_name` = el nombre del agente y `data.by=customer`.
  - `reservations.cancelled_by` es `customer`.
  - No se avisa al cliente.

  _Requisitos: 4.1_
- [x] **T013** Implementa en `apps/mcp/src/nexus_mcp/servers/reservas/tools.py` (`Cancel.run`): `actor=Actor("agent", <Agent.name>)`, leyendo el nombre igual que en `Create.run`. T012 en verde.

  _Requisitos: 4.1, 4.2_

## Fase 6: Cierre

- [x] **T014** Spec viva en el mismo cambio:
  - `docs/reservas.md`: `find_slots` sin fecha y el autor de la cancelación.
  - En las specs 043 (R6), 047 (clarificación de `spec.md:179`) y 056 (R1.1), una línea «Enmendado por la spec 080» que enlace aquí.

  _Requisitos: 1.1, 2.1, 3.1, 4.1_
- [x] **T015** Pruebas de cierre:
  - `./scripts/verify.sh lint`.
  - Las pruebas tocadas y nuevas de la API y del worker.
  - `tests/isolation/test_45_tools_only_from_activations.py` y `test_056_booking_brake_same_conversation.py`.
  - `grep` de usos de `FindSlotsInput(date=` y de `"date"` obligatorio en las pruebas no tocadas.

  _Requisitos: todos_
- [x] **T016** Enlaza esta carpeta desde la nota de KB `research/2026-11-26-beta-jemma-p0-p1.md`, y deja el guion de commits en `.claude/commits/2026-11-26-080.sh` (inglés, conventional, sin firma).

  _Requisitos: —_

## Dependencias

- T002 y T003 van antes de T004.
- T005 va antes de T006, y T006 antes del verde de T003.
- T008 antes de T009, T010 antes de T011 y T012 antes de T013.
- T014 a T016, al final.

Las fases 3, 4 y 5 son independientes entre sí.

## Análisis (2026-11-26, hecho a mano en lugar de `/speckit-analyze`)

- **Cobertura:** cada criterio tiene su tarea y su prueba.
  - 1.1–1.6: T002, T003 y T004. T002 incluye además la reserva creada por la API de la consola.
  - 2.1–2.5: T005 y T006.
  - 3.1–3.7: T008 a T011.
  - 4.1–4.2: T012 y T013.
- **Constitución:**
  - §I lleva su test de aislamiento (T002) y el barrido de intenciones (T005).
  - §VII: cada prueba se vio en rojo antes de implementar. La de acrílicos (T003) se volvió a poner en rojo quitando R1.
- **Pendiente de comprobar en vivo:** CE-003, es decir, que Luna y Haiku 5.5 llamen a `find_slots` sin fecha cuando el cliente no da día.
  - No se pudo con el proveedor real: el modo automático no deja leer las claves de staging.
  - Se hará en el Playground de staging tras fusionar (quickstart, «En staging»).
  - El esquema que recibe el modelo ya no tiene `date` en `required`.
