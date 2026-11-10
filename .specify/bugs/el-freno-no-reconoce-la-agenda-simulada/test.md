# Bug Verification: el freno de citas no reconoce la agenda simulada

- **Slug**: el-freno-no-reconoce-la-agenda-simulada
- **Tested**: 2026-11-08
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified (local; sin probar en staging)

## Summary

Reproducido en `develop` (6c5b28eb). En el Playground, «te reservé» con la reserva
simulada hecha acababa en la frase de traspaso: `classifier_failed_closed` dos
veces y `handed_off`. Con el arreglo:

- las cinco pruebas en rojo pasan;
- las pruebas nuevas, que estaban en rojo contra la simulación de antes, pasan;
- una cita de un turno anterior del Playground respalda el «te esperamos» del
  siguiente.

Base y Redis propios: `nexus_test_brakesim` y `redis://localhost:6379/8`. Las de la
API y las del worker, en procesos de pytest separados.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción | `pytest tests/integration/builder/test_playground_draft.py::test_it_runs_the_draft_with_simulated_time_and_agenda` en `develop` | fail | la burbuja era la frase de traspaso |
| Pruebas nuevas contra la simulación de antes | `registry.py` y `world.py` de `HEAD`, `pytest worker/tests/unit/test_booking_brake_simulation.py` | fail | 10 de 10 en rojo |
| Segundo turno sin el gancho | `simulated_agenda=False` en el manejador, `pytest …::test_a_booking_of_an_earlier_turn_backs_the_reply_of_the_next_one` | fail | «Voy a pasar…» en lugar de «Perfecto, te esperamos…» |
| Las cinco en rojo | `pytest` de las cinco por nodo | pass | 5 passed |
| Freno y simulación (worker) | `pytest worker/tests/unit/test_booking_brake_simulation.py test_booking_brake.py test_pipeline_booking_brake.py` | pass | 85 passed |
| Worker, selección | `pytest worker/tests -k "simulation or playground or brake or simulated"` | pass | 110 passed |
| Worker, consumidores del registro simulado | `test_checkable_state_contract`, `test_agent_tests_multiturn`, `test_builder_call_budget`, `test_classifier_reaches_the_provider`, `test_simulation_failures`, `test_simulated_registry_connectors` | pass | 43 passed |
| API, constructor y freno | `builder/test_agent_suite.py`, `test_model_failures_are_not_agent_failures.py`, `test_playground_channel_race.py`, `test_playground_draft.py`, `test_turn_effects_idempotent.py`, `test_booking_brake_turn.py`, `isolation/test_056_booking_brake_same_conversation.py`, `connectors/test_playground_never_reaches_the_business.py`, `test_jobs_reach_the_model_behind_the_proxy.py` | pass | 55 passed |
| MCP, registro | `pytest mcp/tests -k "registry or dry_run or view"` | pass | 5 passed |
| Lint | `ruff check` y `ruff format --check` de worker, mcp y las pruebas tocadas de la API; `mypy --strict` de `nexus_worker` y `nexus_mcp` | pass | 144 y 65 archivos, sin errores |

## Not run

- Las suites completas (solo corren de camino a `main`).
- Staging: el Playground y una pasada de pruebas de verdad tras desplegar.
