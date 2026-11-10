# Test: las pruebas esperan lo que nadie mide

- `apps/api/tests/unit/test_tests_check_what_is_measured.py`
- `apps/api/tests/integration/builder/test_tests_check_what_is_measured.py`
- `apps/worker/tests/unit/test_checkable_state_contract.py`: `CHECKABLE_STATE` y `World.final_state` no pueden separarse.

Falta repetir la pasada en staging tras desplegar, con el agente «Prueba del constructor» y con uno nuevo.
