# Bug Test: la suite de un agente no decide, se repite y frena la puerta

- **Slug**: la-suite-no-decide-y-se-repite
- **Date**: 2026-11-04

- `apps/api/tests/unit/test_suite_without_repeats.py`: qué repite qué, con los pares de
  staging, y qué entra.
- `apps/api/tests/integration/builder/test_agent_suite.py`: `reconcile_suite` con
  calendario conectado, razón de una persona y sobrantes.
- `apps/worker/tests/unit/test_agent_tests_multiturn.py`: el juez se aparta si respondió.
- `apps/worker/tests/unit/test_platform_models.py`: la simulación no usa el modelo probado.
- `apps/worker/tests/unit/test_builder_call_budget.py`: una cita por conector cuenta, y
  buscar huecos no.

**Sin verificar:** la calidad de los veredictos de Terra como juez. Se mira en staging:
cuántas pruebas salen «No sé» en la primera pasada tras desplegar.
