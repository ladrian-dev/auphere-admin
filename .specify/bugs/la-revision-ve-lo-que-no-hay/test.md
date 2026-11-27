# Bug Verification: la revisión automática del agente avisa de lo que no hay

- **Slug**: la-revision-ve-lo-que-no-hay
- **Tested**: 2026-11-26
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

Las reproducciones de la evaluación (las llamadas a `forbids_agenda`, `_PRICE` y el rango de
horas con el texto real de Jemma) ya no reproducen, y lo que debe seguir avisando avisa. Es
`partial` porque no se ha corrido la revisión contra el borrador de Jemma en staging ni se
ha visto la tarjeta en un navegador con datos reales: lo segundo va en la pasada viva de la 081.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción, antes | `pytest tests/unit/test_agent_spec_compiler.py` sin el arreglo | fail | 6 failed: las cinco nuevas y la de «mismo horario y precio», que el fixture escondía |
| Reproducción, después | el mismo fichero | pass | 22 passed |
| Lo que llama a `forbids_agenda` y a la revisión | 9 ficheros (unitarias, integración del constructor, agenda, migración 0229, `tests/isolation/test_057_agenda_from_agent.py`) | pass | 119 passed |
| Consola, antes | `vitest run …/tests-box.test.tsx` | fail | 1 failed: las promesas salían una a una |
| Consola, después | `tests-box`, `agent-builder`, `review-panel`, `missing-capabilities` | pass | 96 passed, con axe en la tarjeta |
| Lint y tipos | `ruff check`, `ruff format`, `mypy --strict` de `compiler.py` | pass | `verify.sh lint` y `verify.sh js` enteros, al final |
| Coste de las expresiones | textos de 2.000 a 5.000 caracteres | pass | ≤ 2 ms cada uno |
| Staging, con el borrador de Jemma | | not-run | Sin desplegar; no hay acceso al borrador de prod |

Base de pruebas propia: `nexus_test_081`, Redis 11.

## Output Excerpts

```text
6 failed, 16 passed in 7.56s
22 passed in 16.13s
119 passed, 3 warnings in 41.22s
Tests  1 failed | 11 passed (12)
Tests  96 passed (96)
```

## Residual Risks

- Una regla menos estricta puede callar algún aviso verdadero; cada regla lleva su caso que
  sigue avisando, pero solo con frases de prueba.
- `forbids_agenda` decide también lo que propone cambiar el constructor (`agenda_text.py`,
  `agent_draft.py`): esas propuestas cambian igual. Sus pruebas pasan.
- ReviewPanel y la hoja de PublishBar siguen enseñando las promesas: es su sitio (ver
  `fix.md`, «Deviations»).

## Recommendation

Cerrar tras abrir el borrador de Jemma en staging (o una copia de su texto) y ver que la
revisión no marca «El equipo no confirma las citas» ni sus precios en USD.

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

Comprobado contra la evaluación, punto por punto: la negación del equipo (`_TEAM_SUBJECT` en `_refused` y `_team_checks`), el importe como `Decimal` con «30 USD», «30,00 USD», «$30», «US$ 30» y cualquier código ISO de la ficha, «N a M» solo si parece una hora y va en una frase del horario, contra el horario del negocio, de las sedes y de las fechas especiales. De los cuatro sitios que pintaban lo mismo se quitó la repetición en la columna visible (TestsBox, debajo de «No tenemos herramienta para»); ReviewPanel (dentro de «Más ajustes», plegado) y la hoja de PublishBar (solo al guardar con bloqueo) se quedan, porque cada uno decide algo distinto; la columna se monta en `agent-builder.tsx`, de la 082. Nada que completar.
