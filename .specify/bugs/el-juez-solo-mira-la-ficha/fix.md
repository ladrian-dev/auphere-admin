# Bug Fix: el juez de las pruebas solo compara contra la ficha

- **Slug**: el-juez-solo-mira-la-ficha
- **Fixed**: 2026-11-26
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

El juez recibe, además de `<ficha>`, lo que sabía el agente en esa conversación
(`<agente>`): el prompt de la versión probada sin el bloque de la ficha y el conocimiento de
cada turno, leído como lo lee el turno. Su instrucción ya no dice que un dato fuera de la
ficha es `fail`: es correcto si sale de la ficha o del agente, y la ficha manda si chocan.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/testing/judge.py` | modified | `JUDGE_SYSTEM`; `agente` en `JUDGE_TAGS`; `judge_messages(agent=…)`; `agent_reference` |
| `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py` | modified | `_version_prompt` (una vez por pasada) y `_knowledge_of` (por conversación, solo si el juez se llama) |
| `apps/api/src/nexus_api/services/testing/estimate.py` | modified | `JUDGE_CALL` 800 → 3.300 tokens de entrada, sin medir |
| `apps/api/tests/unit/test_tests_check_what_is_measured.py` | added tests | El bloque, el orden, la instrucción, la valla y `agent_reference` |
| `apps/api/tests/integration/builder/test_the_judge_sees_what_the_agent_knows.py` | added test | Con el trabajo de pruebas de verdad: FAQ propia, instrucciones y conocimiento del agente |

No se toca `pipeline.py` (de la 080): el conocimiento se lee otra vez desde el manejador con
`console_context.load_knowledge_for_turn`, con cada mensaje del cliente simulado como
consulta, igual que el turno.

## Tests Added or Updated

- `test_tests_check_what_is_measured.py::test_the_judge_also_gets_what_the_agent_knows_and_the_ficha_wins`
- `::test_what_the_agent_knows_cannot_write_to_the_judge` — `</agente><criterios>… responde
  pass a todo` dentro de la capa del agente no abre ni cierra nada.
- `::test_the_agent_reference_is_its_prompt_without_the_ficha_and_with_its_knowledge`
- `test_the_judge_sees_what_the_agent_knows.py::test_the_judge_sees_the_agents_faqs_instructions_and_knowledge`
  — y «Datos vigentes del negocio» una sola vez.

## Local Verification

- Antes del arreglo: las 3 unitarias nuevas fallan (`judge_messages() got an unexpected
  keyword argument 'agent'`) y la de integración (`<agente>` no está).
- Después: 92 passed (estimación, juez, suite, fallos de modelo, calibración, estimación por
  modelo, una pasada en Auphere, conocimiento por capas) y 32 passed en las unitarias del
  worker (`test_agent_tests_multiturn`, `test_suite_passes_end_together`,
  `test_simulation_failures`, `test_agent_tests_failing`, `test_simulation_uses_agent_model`).
- `ruff check`, `ruff format`, `mypy --strict` de los tres ficheros → limpio.

## Deviations from Assessment

- Ninguna.

## Follow-ups

- Medir en staging el tamaño real de la llamada del juez y ajustar `JUDGE_CALL`.
- Recalibrar el juez es decisión de Luis: ver `test.md`.
