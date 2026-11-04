# Bug Fix: la suite de un agente no decide, se repite y frena la puerta

- **Slug**: la-suite-no-decide-y-se-repite
- **Fixed**: 2026-11-04
- **Assessment**: ./assessment.md
- **Status**: applied, sin desplegar. Enmienda: spec 047, requisito 66.

## Summary

El cliente simulado y el juez pasan a `llm_simulation_model` (Terra), y si el juez
respondió en esa conversación juzga otro. La suite deja como mucho 4 del caso y, con
todas las críticas que aplican, hasta 8 entre las dos, y se pone al día con las
herramientas: «No aplica» al guardar y, antes de cada pasada, lo que sobra se archiva
contra esa versión. Las suites que ya existen se reducen solas en su siguiente pasada. Lo
que tocó una persona no se toca, y una crítica solo la sustituye otra crítica.

**Límite conocido:** «Pide cita sin agenda» se archiva antes de una pasada con calendario y
no vuelve si después se descarta ese borrador. Solo existe en borradores de plantilla, y
una migración para marcarla «No aplica» (`ck_agent_tests_na_only_sector`) no compensaba.

## Decisión a revisar

Terra y no Luna: Terra está en uso en producción (logs de 30 días) y Luna no aparece ni
en staging ni en producción, así que no hay prueba de que responda. La diferencia es de
céntimos por pasada.

## Changes

| File | Change |
|------|--------|
| `apps/worker/src/nexus_worker/config.py`, `platform_models.py` | Familia `simulation` |
| `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py` | `_judge_for`; lo que vio el juez llega a «No sé» |
| `apps/worker/src/nexus_worker/jobs/handlers/agent_publish.py` | `reconcile_suite` antes de la pasada |
| `apps/worker/src/nexus_worker/simulation/world.py` | Una cita por conector cuenta |
| `apps/api/src/nexus_api/services/testing/sector_catalog.py` | `repeats`, `choose`, `sector_items`, `reconcile_suite` |
| `apps/api/src/nexus_api/services/testing/runs.py` | `why_failed` también para «No sé» |
| `apps/api/src/nexus_api/services/builder/agent_draft.py`, `prompts/agent_draft.md` | Como mucho 4 del caso, sin lo común |
| `apps/api/src/nexus_api/api/console/agent_spec_drafts.py`, `agent_tests.py` | Llaman a `reconcile_suite` |
| `apps/console/src/components/builder/test-list.tsx`, `agent-builder.tsx` | «No aplica» y secciones plegadas; «No sé» no es un fallo |
