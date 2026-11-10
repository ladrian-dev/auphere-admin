# Bug Verification: la reserva del turno siguiente pierde los ids del servicio y de la persona

- **Slug**: la-reserva-del-turno-siguiente-pierde-los-ids
- **Tested**: 2026-11-08
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified (local; sin probar en staging ni con un modelo de verdad)

## Summary

Reproducido sobre `develop` (c7a193b4) con el despachador, el grafo y el servidor MCP
de verdad: el turno 2 («A las 10») no ve los ids del turno 1. El modelo llama a
`reservas.create` con los nombres, la validación lo rechaza y la respuesta acaba en
la frase de traspaso. En staging acabó en «Ese horario ya no está disponible»: el
modelo de verdad lo contó así; el doble de la prueba lo confirma y lo para el freno.

Con el arreglo, el segundo turno reserva Corte con Lucía por nombre. Lo que no se
resuelve vuelve con las opciones y sin error.

Base y Redis propios: `nexus_test_toolnames` y `redis://localhost:6379/15`. Las
pruebas de la API y las del worker, en procesos de pytest separados y una ejecución
cada vez.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción y pruebas nuevas en rojo | `pytest tests/integration/reservas/test_reserva_por_nombre.py` antes del arreglo | fail | 11 de 11. El segundo turno: frase de traspaso, con el prompt sin los ids |
| Aislamiento nuevo en rojo | `tools.py` y `schemas.py` de `HEAD`, `pytest test_44…::test_an_agent_never_offers_nor_books_its_siblings_services test_reservas_client_vs_client.py::test_the_agent_reads_a_neighbours_service_or_person_as_one_that_does_not_exist` | fail | 2 de 2 |
| Simulación y freno en rojo | `pytest worker/tests/unit/test_booking_brake_simulation.py test_booking_brake.py` antes del arreglo | fail | 4 en rojo. La de reservar por nombre ya pasaba: la simulación aceptaba `service_name` |
| Pruebas nuevas | `pytest tests/integration/reservas/test_reserva_por_nombre.py` | pass | 11 passed |
| Aislamiento | `pytest tests/isolation/test_44_agent_within_client.py test_reservas_customer_axis.py test_reservas_client_vs_client.py` | pass | 29 passed |
| Reservas y el turno (API) | `pytest tests/integration/reservas/ business/test_services.py connectors/test_booking_skills.py reservations/test_pass_to_reservas.py reservations/test_auto_pass.py test_turn_effects_idempotent.py test_booking_brake_turn.py` | pass | 352 passed |
| Constructor y Playground (API) | `builder/test_playground_draft.py test_agent_suite.py test_playground_channel_race.py test_model_failures_are_not_agent_failures.py test_one_pass_on_auphere.py test_tests_check_what_is_measured.py`, `connectors/test_playground_never_reaches_the_business.py`, `isolation/test_056_booking_brake_same_conversation.py test_37_customer_axis_contract.py test_51_new_tools_take_no_end_customer.py` | pass | 101 passed, 1 skipped |
| Validador y herramientas de la consola (API) | `unit/test_agent_spec_validator.py test_endpoint_console_agent_tools.py test_pending_tools.py` | pass | 36 passed |
| Freno y simulación (worker) | `pytest worker/tests/unit/test_booking_brake_simulation.py test_booking_brake.py` | pass | 74 passed |
| Worker, selección | `pytest worker/tests -k "simulation or playground or brake or simulated or multiturn or checkable_state or builder_call_budget or classifier_reaches or tools_already_used or conversation_arg"` | pass | 164 passed |
| MCP, registro | `pytest mcp/tests -k "registry or reservas or dry_run or view"` | pass | 5 passed |
| Lint | `./scripts/verify.sh lint` (ruff check y format de api, worker, channels y mcp; `mypy --strict` de los cuatro; renderer) | pass | 15 de 15 |

## Not run

- Las suites completas: solo corren de camino a `main`.
- Staging, con un modelo de verdad: que el modelo, con las descripciones nuevas, pase
  los nombres en el segundo turno y reintente con una opción tras un `unknown_*`. La
  prueba del turno usa un doble que llama como lo haría el modelo.
- La prueba de una versión del panel de operador, que lee la copia del catálogo en
  base (ver `fix.md`).
