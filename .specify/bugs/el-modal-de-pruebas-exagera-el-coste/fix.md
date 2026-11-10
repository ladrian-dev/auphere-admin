# Bug Fix: el modal de las pruebas dice 4 o 5 veces lo que cuestan

- **Slug**: el-modal-de-pruebas-exagera-el-coste
- **Fixed**: 2026-11-04
- **Assessment**: ./assessment.md
- **Status**: applied, sin desplegar. Enmienda: spec 047, requisito 66.5 (enmienda el 61.8).

## Summary

La estimación sale de lo medido, con la caché y el clasificador. La consola ya no pregunta
salvo que la pasada no quepa en lo que queda de «Construcción y pruebas». El coste real
sigue en Uso.

## Changes

| File | Change |
|------|--------|
| `apps/api/src/nexus_api/services/testing/estimate.py` | Tamaños medidos, clasificador |
| `apps/api/src/nexus_api/services/wallet/build_budget.py` | `read_for_partner` |
| `apps/api/src/nexus_api/api/console/agent_tests.py` | `budget` en `dry_run` |
| `apps/console/src/components/builder/run-estimate.tsx` | `doesNotFit`: solo pregunta entonces |
