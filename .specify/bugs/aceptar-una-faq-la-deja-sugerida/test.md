# Bug Verification: aceptar una pregunta frecuente del constructor la deja sugerida

- **Slug**: aceptar-una-faq-la-deja-sugerida
- **Tested**: 2026-11-26
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

La reproducción de la evaluación, automatizada con el constructor de verdad y la API, ya no
reproduce: la pregunta aceptada queda confirmada, sale confirmada en `GET …/faqs` y entra en
el prompt de la versión activa. Es `partial` porque no se ha visto en staging ni en un
navegador: el worktree no está desplegado.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción, antes | `pytest tests/integration/builder/test_accepting_a_builder_faq.py` sin el arreglo | fail | `assert True is False`: la fila aceptada seguía `suggested` (lo que vio Luis) |
| Reproducción, después | el mismo fichero | pass | 2 passed |
| La forma que dejó el fallo | `test_a_faq_the_bug_left_suggested_is_confirmed_by_accepting_it_again` | pass | Pasaba ya antes del arreglo: fija que esas filas no se quedan atascadas |
| Regresión | `test_client_builder_and_copilot.py`, `test_client_builder_launch.py`, `test_provenance_history.py`, `test_sector_identify.py` | pass | 36 passed con las dos nuevas |
| Lint y tipos | `ruff check`, `ruff format --check`, `mypy --strict` de `suggestions.py` y la prueba | pass | `verify.sh lint` entero se corre al final, con todas las unidades |
| Staging | | not-run | Sin desplegar |
| Navegador | | not-run | La consola no cambia; se ve en la pasada viva de la 081 |

Base de pruebas propia: `nexus_test_081`, Redis 11.

## Output Excerpts

```text
>       assert rows[first.proposed_value["q"]].suggested is False
E       assert True is False
1 failed, 1 passed
---
9 passed, 1 warning in 15.79s
27 passed, 2 warnings in 16.56s
```

## Residual Risks

- Las que quedaron sugeridas en prod siguen en «Por confirmar» hasta que alguien pulse
  «Aceptar» otra vez. La consulta de `fix.md` las cuenta.
- Aceptar una propuesta importada (ClientSpec) con `suggested: true` también la confirma.

## Recommendation

Cerrar tras verlo en staging: aceptar una pregunta del constructor en Negocio y comprobar que
no vuelve a «Por confirmar» y que el chat de prueba la responde.

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

Comprobado contra la evaluación: `_confirmed` quita `suggested` del valor que se aplica al aceptar o editar una propuesta de `/faqs/…`, en `suggestions.decide` (no en `faqs._apply`, que sigue sirviendo a deshacer). La pregunta aceptada entra en el prompt en la misma transacción (`section_write`). Sin huecos.
