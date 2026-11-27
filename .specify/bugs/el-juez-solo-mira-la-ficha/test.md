# Bug Verification: el juez de las pruebas solo compara contra la ficha

- **Slug**: el-juez-solo-mira-la-ficha
- **Tested**: 2026-11-26
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

El defecto del código está arreglado y probado con el trabajo de pruebas de verdad: el juez ve
la FAQ propia, las instrucciones y el conocimiento del agente, y la ficha una sola vez. Es
`partial` porque **no está probado que esto explique el rojo de Jemma**: no se ha visto la
conversación ni la explicación del juez de su prueba crítica, ni si su juez está calibrado.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción, antes | `pytest tests/integration/builder/test_the_judge_sees_what_the_agent_knows.py` | fail | `ValueError: substring not found`: no había `<agente>` |
| Reproducción, después | el mismo | pass | |
| Unitarias del juez | `tests/unit/test_tests_check_what_is_measured.py` | pass | 12 passed; las 3 nuevas fallaban antes |
| Regresión API | 11 ficheros (estimación, suite, fallos de modelo, calibración, conocimiento) | pass | 92 passed |
| Regresión worker | 5 ficheros de `apps/worker/tests/unit` | pass | 32 passed |
| Lint y tipos | `ruff`, `mypy --strict` | pass | |
| El rojo de Jemma | | not-run | Sin acceso a prod |
| Staging | | not-run | Sin desplegar |

Base de pruebas propia: `nexus_test_081`, Redis 11.

## Output Excerpts

```text
E           ValueError: substring not found
1 failed, 1 warning in 11.00s
---
92 passed, 1 warning in 73.22s
```

## Residual Risks

- **Calibración**: `calibration.calibrate` llama a `judge_messages` sin referencia, así que el
  conjunto de calibración no mide este cambio; el texto del sistema sí cambió.
  `judge_calibrated` no mira `battery_version`, así que subir `CALIBRATION_VERSION` no
  invalidaría nada. Si un juez está calibrado en algún entorno, su nota es de la instrucción
  anterior: recalibrarlo lo decide Luis.
- **Coste**: la llamada del juez pasa de ~800 a ~3.300 tokens de entrada estimados (una por
  pasada, tres por prueba). Sin medir.
- **Conocimiento**: se lee de nuevo tras la conversación. Si los documentos del agente
  cambian a mitad de la pasada, el juez puede ver una versión distinta de la que vio el agente.
- **Inyección**: instrucciones y documentos del partner llegan al juez como dato vallado
  (`inert`); la prueba lo fija para las etiquetas, no para un modelo real.

## Recommendation

Mantener abierto hasta ver en staging una pasada de un agente con FAQ propia y conocimiento, y
pedir a Luis la conversación de la prueba crítica de Jemma para saber si era esto.

## Segunda verificación (sesión de cierre, 2026-11-26)

Revisión del arreglo contra la evaluación y ejecución de nuevo, sin cambios de código, en el
worktree `funny-pare-ffd5f3` con base propia (`nexus_test_081`, Redis 11):

| Check | Command / Action | Result |
|-------|------------------|--------|
| Lint y tipos de todo el repo | `./scripts/verify.sh lint` (ruff check y format, `mypy --strict` de api, worker, channels, mcp y renderer) | pass — «Todo verde» |
| Unitarias tocadas | `pytest tests/unit/test_agent_spec_compiler.py tests/unit/test_tests_check_what_is_measured.py` | pass — 34 passed |
| Integración de los tres bugs | `pytest tests/integration/builder/test_accepting_a_builder_faq.py test_the_judge_sees_what_the_agent_knows.py test_client_builder_and_copilot.py` | pass — 10 passed |
| Regresión de la API (revisión, agenda, constructor, pruebas, juez, ficha) | 18 ficheros: `test_agent_review`, `test_suite_estimate`, `test_agent_model_estimate_factor`, `test_only_what_we_have`, `test_057_agenda_routes`, `test_057_agenda_text_job`, `test_review_and_catalog`, `test_migration_0229_agenda_from_agent`, `isolation/test_057_agenda_from_agent`, `test_agent_draft_job`, `integration/builder/test_tests_check_what_is_measured`, `test_judge_is_the_configured_model`, `test_model_failures_are_not_agent_failures`, `test_one_pass_on_auphere`, `test_agent_suite`, `test_client_builder_launch`, `test_provenance_history`, `test_sector_identify` | pass — 175 passed |
| Lo que pasa por el trabajo de pruebas | `test_one_suite_at_a_time`, `test_publish_gate`, `test_no_way_around_the_gate`, `test_versions`, `test_jobs_reach_the_model_behind_the_proxy` | pass — 26 passed |
| Worker | `apps/worker/tests/unit/` `test_agent_tests_multiturn`, `test_suite_passes_end_together`, `test_simulation_failures`, `test_agent_tests_failing`, `test_simulation_uses_agent_model`, `test_057_simulation_readiness` | pass — 37 passed |
| Consola | `vitest run` de `tests-box`, `review-panel`, `missing-capabilities`, `agent-builder`, `publish-bar` | pass — 122 passed |

Comprobado contra la evaluación: `<agente>` lleva el prompt de la versión probada sin «Datos vigentes del negocio» y el conocimiento de cada mensaje del cliente simulado; la instrucción dice que la ficha manda; todo pasa por `inert`; el prompt de la versión se lee una vez por pasada. El rojo de Jemma sigue sin reproducir (sin acceso a prod).
