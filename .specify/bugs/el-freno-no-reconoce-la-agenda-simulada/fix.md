# Bug Fix: el freno de citas no reconoce la agenda simulada

- **Slug**: el-freno-no-reconoce-la-agenda-simulada
- **Fixed**: 2026-11-08
- **Assessment**: ./assessment.md
- **Status**: applied (sin commit)

Se arregla dentro de la spec 056 (requisito 1): es un defecto contra su propio
criterio, no un cambio de comportamiento nuevo.

## Summary

1. **La agenda simulada contesta con la forma de verdad** (`simulation/registry.py`).
   - Construye la salida con los modelos de `nexus_mcp.servers.reservas.schemas`,
     más `simulated: true`:
     - `create`: `CreateOutput`, con `idempotent_replay` si se repite la clave;
     - `reschedule`: `RescheduleOutput`, que mueve **la misma** cita, como
       `move_booking`;
     - `cancel`: `CancelOutput`;
     - `list_mine`: `ListMineOutput`, con las que vienen y siguen en pie;
     - `confirm_attendance`: `ConfirmAttendanceOutput`;
     - `answer_offer`: `AnswerOfferOutput` con `no_offer`, porque no hay lista de
       espera simulada.
   - La cita sale como `BookingBrief`, con día y horas locales.
   - Rechazos de la agenda, con `status: ok` y los códigos de `create_booking`:
     `slot_taken` (con `first_fit`), `too_soon` y `hours_missing`.
   - Lo que la herramienta de verdad no acepta es `ToolError`, y el grafo lo
     convierte en `status: error`: una fecha u hora que no valida, una cita que no
     existe o ya no está en pie, `confirm_attendance` sin cita.
   - Las `booking.*` retiradas fallan con error ante un rechazo, como las de
     verdad.
2. **La cita de un turno anterior respalda.** Nuevo gancho
   `MCPRegistry.simulated_booking_stands()`, que por defecto devuelve `False`; el
   registro simulado responde si su mundo tiene una cita confirmada.
   `pipeline.make_handler_node` se lo pasa a `booking_brake.unbacked_claim(...,
   simulated_agenda=...)`, que lo cuenta como respaldo de un turno anterior. Con
   un intento fallido en este turno, se hace la pregunta estrecha, igual que en el
   canal.
3. **`World`**:
   - `SimBooking.key` (la clave de idempotencia; con valor por defecto, así que
     las sesiones guardadas siguen cargando);
   - `World.move(...)`;
   - `slots(..., ignoring=)`, para que una cita que se cambia de hora no ocupe su
     propio hueco.

`backs()` no cambia: la tabla R1 sigue siendo la de la spec.

## Los dobles de las pruebas

- `test_turn_effects_idempotent.py`: la herramienta contada pasa a ser
  `reservas.create` con `CreateOutput`. `testshop.reserve` no es una herramienta
  de reservar para el freno, así que «Te reservé…» se paraba con razón. Cambian
  dos cosas más:
  - la intención pasa a `book`, porque `reservas.create` solo se ofrece en esa
    categoría;
  - el efecto de la clave pasa a ser `reserve`.

  El reintento sigue pasando por la reproducción (`replayed`), y el freno no
  actúa.
- `test_agent_suite.py`: `Booker` contesta YES a la llamada del freno (la
  reconoce por `booking_brake.CLASSIFY_PROMPT`) sin avanzar su contador de
  pasadas. Sin esto, las pruebas pasaban por accidente: en `Booker({1, 3})`, la
  llamada del freno de la pasada 2 subía el contador a 3 y el reintento reservaba
  en la 2, así que la que fallaba era la 3.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/worker/src/nexus_worker/simulation/registry.py` | modified | la agenda con los modelos de verdad, errores como la de verdad y `simulated_booking_stands` |
| `apps/worker/src/nexus_worker/simulation/world.py` | modified | `SimBooking.key`, `move`, `slots(ignoring=)` |
| `apps/mcp/src/nexus_mcp/registry.py` | modified | el gancho `simulated_booking_stands()` (`False`) |
| `apps/worker/src/nexus_worker/runtime/booking_brake.py` | modified | `unbacked_claim(simulated_agenda=)` y el docstring; `booking_tools()` sin tocar |
| `apps/worker/src/nexus_worker/runtime/pipeline.py` | modified | el manejador pasa la agenda simulada al freno |
| `apps/worker/tests/unit/test_booking_brake_simulation.py` | added | 10 pruebas con sobres del registro simulado |
| `apps/api/tests/integration/builder/test_playground_draft.py` | modified | la cita del primer turno respalda «te esperamos» en el segundo |
| `apps/api/tests/integration/builder/test_agent_suite.py` | modified | `Booker` contesta al freno |
| `apps/api/tests/integration/test_turn_effects_idempotent.py` | modified | el doble con la forma de `reservas.create` |
| `docs/agentes.md` | modified | §9: la agenda simulada y el respaldo de turnos anteriores |

## Fuera de este arreglo (auditoría del canal)

En el canal no hay ninguna lectura que tome por no hecha una reserva hecha:

- `reservas.*` y `booking.*` respaldan con su forma de verdad;
- la reproducción del turno (`tool_once`: `{**prior, "replayed": true}`, con el
  sobre guardado en JSON) respalda; `skipped:already_attempted` también;
- Composio pone como `tool` el slug, que es el nombre de `TOOL_ACTIONS`, y marca
  `error` cuando hay `result.error`.

Quedan tres casos, para Luis, en los que una afirmación **sale** sin respaldo real.
Siguen la tabla R1 y no se tocan aquí:

- `reservas.confirm_attendance` con `attending=false` cancela y devuelve `status: ok`
  con la cita, así que respalda;
- `reservas.list_mine` con `only_upcoming=false` lista también canceladas y
  pasadas;
- `reservas.create` con la clave de una reserva ya cancelada la devuelve como
  `idempotent_replay`.

Tampoco se tocan aquí:

- el revisor de resultados (`_rewrite_claims_a_booking`) no recibe la agenda
  simulada (no tiene el registro). Está apagado por defecto y, dentro del turno,
  ya respaldan los sobres;
- `reservas.services`, `reservas.find_slots` y `reservas.join_waitlist` simulados
  conservan su forma propia, porque el freno no los lee.
