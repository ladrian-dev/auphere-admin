# Bug Test: el modal de las pruebas dice 4 o 5 veces lo que cuestan

- **Slug**: el-modal-de-pruebas-exagera-el-coste
- **Date**: 2026-11-04

- `apps/api/tests/unit/test_suite_estimate.py`: 17 pruebas salen entre 2 y 4,5 USD.
- `apps/api/tests/integration/builder/test_agent_suite.py`: `dry_run` trae `budget`.
- `apps/console/src/components/builder/__tests__/run-estimate.test.tsx`: lo que cabe
  arranca sin preguntar; lo que no cabe pregunta con las dos cifras.
