# Test: un adelanto por lista de espera no respalda la respuesta

Las tres pruebas nuevas, en rojo antes del cambio y en verde después (2026-11-27,
base propia `nexus_test_fixrev`, Redis 14).

## Antes del cambio: 3 failed

- `tests/unit/test_083_cycles.py::test_accepting_a_waitlist_offer_for_a_live_booking_is_a_move`:
  `moved` con `total: 0`.
- `tests/isolation/test_080_booking_brake_customer_cycle.py::test_a_move_by_accepting_a_waitlist_offer_in_this_cycle_backs`:
  «el adelanto por lista de espera no respaldó».
- `tests/integration/console/test_client_report.py::test_accepting_a_waitlist_offer_counts_as_a_move`:
  `moved` con `total: 0`.

## Después del cambio

- API: `test_083_cycles.py`, `test_080_booking_brake_customer_cycle.py`,
  `test_056_booking_brake_same_conversation.py` y `test_client_report.py`: 50 passed.
- Worker (`uv run --directory apps/api pytest`): `test_pipeline_booking_brake.py`,
  `test_057_agenda_not_ready.py` y `test_057_agenda_whitelist.py`: 46 passed.
- `./scripts/verify.sh lint`: en verde.
