# Bug Assessment: el freno de citas no reconoce la agenda simulada

- **Slug**: el-freno-no-reconoce-la-agenda-simulada
- **Created**: 2026-11-08
- **Source**: pruebas en rojo en `develop` (6c5b28eb) tras fusionar la spec 056; visto en staging en el Playground
- **Verdict**: valid
- **Severity**: critical (P0: rompe el Playground y las pruebas del agente, que deciden la publicación)

## Report (verbatim or summarized)

Desde la spec 056, en el Playground y en las pasadas de pruebas del agente toda
reserva simulada acaba en «Voy a pasar tu consulta a una persona del equipo…»:
el agente reserva, dice «te reservé el lunes a las 10:00» y el freno de citas lo
para. Es un defecto contra el criterio de la propia 056 (historia 1, escenario 3:
una reserva hecha en el turno sale sin cambios y sin llamadas).

En rojo en `develop`:

- `apps/api/tests/integration/builder/test_playground_draft.py::test_it_runs_the_draft_with_simulated_time_and_agenda`
- `apps/api/tests/integration/builder/test_agent_suite.py::test_three_runs_pass_three_of_three_and_two_of_three_is_flaky`,
  `::test_the_judge_has_one_dimension_per_criterion_and_does_not_block_uncalibrated`,
  `::test_a_pass_is_a_conversation_kept_turn_by_turn`
- `apps/api/tests/integration/test_turn_effects_idempotent.py::test_a_retried_turn_reserves_once_and_answers_once`

## Symptom

1. **Turno con reserva.** `reservas.create` simulado devuelve
   `{"ok": true, "simulated": true, "booking_id", "when", "service"}` con
   `status: ok`. `booking_brake.backs()` solo respalda con `result.booking` y sin
   `refused`, que es la forma de la herramienta de verdad (`CreateOutput`). La
   reserva no respalda, el freno llama al clasificador, reintenta y traspasa.
2. **Turno siguiente** (encontrado al arreglar el 1). La cita del turno anterior
   está en la agenda simulada (`World`), no en `reservations`. «Te esperamos el
   lunes», sin herramientas, tampoco tiene respaldo: el freno lee la base, no la
   encuentra y traspasa.
3. **Al revés** (sin síntoma visible todavía). Varios rechazos simulados
   respaldaban una cita que no existía:
   - `booking.create_appointment` / `modify_appointment` fallaban con `status: ok`
     y `ok: false`, y para las `booking.*` basta `status: ok`;
   - `reservas.confirm_attendance` devolvía «hecho» aunque no hubiera cita;
   - `reservas.list_mine` contaba también las canceladas.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/simulation/registry.py` — `_create`, `_reschedule`,
  `_cancel`, `_mine` y `_noted` para `confirm_attendance` / `answer_offer`, con una
  forma propia.
- `apps/worker/src/nexus_worker/runtime/booking_brake.py` — `backs()` (tabla R1)
  y `unbacked_claim()`, que para los turnos anteriores solo lee la base
  (`conversation_backed`).
- `apps/mcp/src/nexus_mcp/servers/reservas/tools.py:423` y `schemas.py` — la forma
  de verdad (`CreateOutput`, `RescheduleOutput`, `ListMineOutput`,
  `ConfirmAttendanceOutput`, `AnswerOfferOutput`, `BookingBrief`).
- Los dobles de las pruebas:
  - `test_turn_effects_idempotent.py`: `testshop.reserve` con `booking_id`, que el
    freno no conoce;
  - `test_agent_suite.py`: `Booker` cuenta como pasada nueva cada llamada
    `classify`, también la del freno.

## Root Cause Hypothesis

Hay dos agendas con dos formas, y el freno se escribió y se probó contra una sola:

- la tabla R1 y las pruebas unitarias usan sobres escritos a mano con la forma de
  la herramienta de verdad;
- ninguna prueba pasaba al freno un sobre producido por el registro simulado;
- el respaldo de turnos anteriores mira `reservations`, que la simulación no
  toca nunca (requisito 20.1).

Confianza: **alta**. Reproducido con la prueba del Playground: `classifier_failed_closed`
dos veces y `handed_off`.

## Proposed Remediation

**Preferred**: que la simulación conteste con la forma de verdad, en vez de aflojar
`backs()`.

- Los manejadores de `reservas.*` que lee el freno construyen su salida con los
  modelos de la herramienta de verdad, más `simulated: true`. Rechazos de la
  agenda: `refused` con `status: ok`. Lo que la herramienta no acepta:
  `ToolError`, que el grafo convierte en `status: error`. Las `booking.*`
  retiradas fallan siempre con error.
- Un gancho `MCPRegistry.simulated_booking_stands()`, que por defecto devuelve
  `False` y que el registro simulado responde con su mundo. El manejador lo pasa
  al freno como `simulated_agenda`, que cuenta como «turno anterior con
  respaldo».
- Los dobles:
  - `reservas.create` con `CreateOutput`;
  - `Booker` contesta YES al freno sin avanzar su contador.

**Alternative**: que `backs()` acepte también `booking_id`. Descartada: las dos
formas seguirían separándose, y lo que el modelo lee en el Playground seguiría sin
ser lo que lee en el canal.

## Test plan

- Unitaria nueva, `apps/worker/tests/unit/test_booking_brake_simulation.py`, con
  los sobres que produce el propio registro simulado por `pipeline._dispatch_tool`:
  - cada salida valida contra el modelo de la herramienta de verdad (`extra="forbid"`);
  - reserva, cambio y cita en pie respaldan;
  - rechazo, error, cancelación y oferta sin lista no respaldan;
  - la misma clave devuelve la misma reserva;
  - una cita de un turno anterior respalda sin clasificador.
- Integración nueva, `test_playground_draft.py`: «te esperamos» en el segundo turno
  sale tal cual.
- Las cinco en rojo, en verde.
