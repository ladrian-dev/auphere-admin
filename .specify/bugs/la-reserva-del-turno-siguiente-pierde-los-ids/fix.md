# Bug Fix: la reserva del turno siguiente pierde los ids del servicio y de la persona

- **Slug**: la-reserva-del-turno-siguiente-pierde-los-ids
- **Fixed**: 2026-11-08
- **Assessment**: ./assessment.md
- **Status**: applied (sin commit)

Tarea T108 de la spec 043 (`_Requisitos: 6.2, 14.4_`). No cambia la nota
`_tools_already_used`: sigue sin argumentos ni resultados, a propósito.

## Summary

1. **Por nombre** (`schemas.py`). Campos opcionales, con descripción para el modelo:
   - `service_name` y `staff_name` en `FindSlotsInput`, `CreateInput` y
     `JoinWaitlistInput`;
   - `staff_name` en `RescheduleInput`: el servicio lo trae la reserva.

   Con un id válido todo sigue como antes: el id manda.
2. **La resolución** (`servers/reservas/names.py` y `tools.py`):
   - `names.matches` compara normalizado (sin mayúsculas, acentos ni espacios de
     más), por orden: el nombre igual, luego los que empiezan por él, luego los que
     lo contienen. Es texto puro, y lo comparten la herramienta y la simulación.
   - `_pick_service` busca en el catálogo vivo del cliente (`list_services`, bajo la
     RLS). Uno que el agente del turno ofrece (`services_for_agent`, «Atiende todos
     los servicios») es ese; uno del hermano, `not_offered`, por id o por nombre.
     Un «Corte» propio no empata con un «Corte» del hermano.
   - `_pick_staff` busca en el equipo activo (`active_staff`). Una persona que hace
     el servicio (`staff_for_service`) es esa; una que no lo hace, `not_offered`
     (R14.4), con quienes sí.
   - Ni el negocio ni el cliente salen de un argumento: los da el contexto, como
     siempre.
3. **Lo que no se resuelve no levanta.** Es la salida normal de la herramienta, con
   `refused` y las opciones (`services` / `staff: [{id, name}]`):
   - `unknown_service`: sin servicio (antes un 422 `service_required`, o un
     `ToolError` en `find_slots`), o un id inventado, archivado o de la vecina
     (antes `not_offered`);
   - `unknown_staff`: un id o un nombre que no está en el equipo activo. Antes el id
     daba `not_offered` en `create`, `slots: []` en `find_slots` y `slot_taken` en
     `reschedule`;
   - `ambiguous_service` / `ambiguous_staff`: el nombre encaja con varios.

   En `find_slots` va en un campo nuevo, `refused`, con `closed: false` y
   `slots: []`. `not_offered` sigue en `why_closed`.

   En `join_waitlist`:
   - `entry_id` y `status` pasan a opcionales, `None` con `refused`;
   - `not_offered` deja de ser un `ToolError`;
   - con `booking_id` y sin servicio, toma el servicio de la reserva.
4. **Las descripciones** de `services`, `find_slots`, `create`, `reschedule` y
   `join_waitlist`, que es lo único que el modelo lee de la herramienta, dicen dos
   cosas:
   - puede pasar los nombres cuando los ids no están en el turno;
   - un `unknown_*` o un `ambiguous_*` se arregla en el mismo turno, con una opción
     o preguntando, y nunca diciendo que la hora está tomada: solo `slot_taken`
     significa eso.

   La descripción de `refused` en los esquemas lo repite (`UNRESOLVED_HELP`).
5. **La agenda simulada** (`simulation/registry.py`):
   - acepta `service_name` como la de verdad (`names.matches`) y da
     `unknown_service` y `ambiguous_service` con las opciones;
   - `find_slots` y `join_waitlist` contestan con la forma de verdad
     (`FindSlotsOutput`, `JoinWaitlistOutput`);
   - `booking.check_availability` y `booking.create_appointment`, retiradas, siguen
     con su texto libre;
   - sin servicio, la cita genérica de siempre.
6. **El freno de citas** (spec 056) no cambia: `backs()` ya no respalda una salida
   con `refused`. Ahora una prueba lo comprueba con `unknown_service`.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/mcp/src/nexus_mcp/servers/reservas/names.py` | added | `fold`, `matches` y los cuatro códigos |
| `apps/mcp/src/nexus_mcp/servers/reservas/schemas.py` | modified | campos de nombre, `ServiceRef`, `refused`/`services`/`staff` en las salidas, `JoinWaitlistOutput` con rechazo |
| `apps/mcp/src/nexus_mcp/servers/reservas/tools.py` | modified | `_pick_service`, `_pick_staff`, `_pick`; `find_slots`, `create`, `reschedule`, `join_waitlist` y sus descripciones; fuera `_offered_service` |
| `apps/worker/src/nexus_worker/simulation/registry.py` | modified | `_pick`, `_find_slots`, `_join_waitlist` con la forma de verdad; `_create(by_name=)`; fuera `_noted` |
| `apps/api/tests/integration/reservas/test_reserva_por_nombre.py` | added | 11 pruebas, incluida la del segundo turno de verdad |
| `apps/api/tests/isolation/test_44_agent_within_client.py` | modified | el servicio del hermano por nombre: `not_offered` en `find_slots`, `create` y `join_waitlist`; opciones solo del agente |
| `apps/api/tests/isolation/test_reservas_client_vs_client.py` | modified | la vecina por id o por nombre se lee igual que lo que no existe |
| `apps/worker/tests/unit/test_booking_brake.py` | modified | `unknown_service` y `ambiguous_staff` no respaldan |
| `apps/worker/tests/unit/test_booking_brake_simulation.py` | modified | 4 pruebas: por nombre, desconocido, ambiguo, y forma de verdad de `find_slots` y `join_waitlist` |
| `specs/043-reservas/contracts/agent-tools.md` | modified | enmienda del 2026-11-08 |
| `specs/043-reservas/tasks.md` | modified | T108 |
| `docs/reservas.md` | modified | «El agente»: por nombre y los rechazos |
| `docs/agentes.md` | modified | §9: la forma de verdad de `find_slots` y `join_waitlist` simulados |

## Fuera de este arreglo

- La copia del catálogo en base (`alembic/data/0173_reservations_tools.json`,
  `tool_catalog.input_schema` y `description`) no se toca, y no hay migración:
  - el modelo del canal recibe el esquema y la descripción del registro MCP;
  - el validador del AgentSpec lee los argumentos del registro
    (`_model_visible_args`);
  - la copia solo la lee la prueba de una versión del panel de operador
    (`api/admin/agent_configs.py::_build_tool_defs`), que enseñaría los campos y la
    descripción de antes. Ya pasa con `why_not` y `price_kind`, que tampoco
    llegaron a la copia.

  Si se quiere al día, es una migración como la `0146`. Queda para Luis.
- La agenda simulada no tiene equipo ni los servicios del hermano. No comprueba la
  persona, y un servicio del hermano es `unknown_service`, no `not_offered`.
- `booking.*` (retiradas) no cambian.
