# Bug Verification: restaurar o publicar por las rutas viejas se salta la puerta

- **Slug**: restaurar-un-borrador-publica-sin-puerta
- **Tested**: 2026-10-29
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Reproducidos los tres caminos: el rollback ponía en marcha un borrador, la ruta
de publicar de antes publicaba una versión con pruebas sin pasarlas y el promote
del panel de operador publicaba sin motivo. Después del arreglo los tres se
cierran y el rollback a una versión que estuvo activa sigue funcionando.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción | `pytest tests/integration/builder/test_no_way_around_the_gate.py` antes del arreglo | fail | 3 en rojo: rollback al borrador → 200 y activo; publicar sin pasada → 200; promote sin `reason` → 200. La cuarta (rollback a una que estuvo activa) ya pasaba: es la guarda |
| Arreglo | lo mismo, después | pass | 4 passed: 409 `rollback_target_never_published` (consola y panel) sin cambiar nada, con la ruta para publicar; `gate_blocked` con `tests_not_run`, que un owner salta con motivo; 422 `reason_required` (sin cuerpo, `{}` y motivo en blanco) y con motivo, en la versión y en `agent.publish` |
| La puerta y las versiones | `pytest tests/integration/builder/test_publish_gate.py tests/integration/builder/test_versions.py` | pass | con el promote sin motivo de `test_the_same_gate_in_the_old_console_and_the_operator_panel` pasado a 422 |
| Sin regresiones (unitarias) | `pytest` de las 14 suites unitarias que publican, promueven o hacen rollback (`test_endpoint_agent_config`, `test_endpoint_evals`, `test_agent_versions_per_agent`, `test_endpoint_console*`, `test_agents_api`, `test_companion_actions`, …) | pass | 168 passed, con `reason` añadido a los promote del panel. `test_agent_versions_per_agent` (rollback a una versión que nació activa) pasa gracias a que la degradación guarda `promoted_at` |
| Sin regresiones (integración) | `pytest tests/integration/builder/ tests/integration/agents/ tests/integration/models/ tests/integration/test_console_draft_diff.py tests/integration/test_partner_auto_provisioning.py tests/integration/test_companion_action_resume.py tests/integration/test_dev_seed_fabrica.py tests/integration/lite/test_lite_agents_business.py tests/integration/test_client_is_born_with_quota.py` | pass | 221 passed tras plegar `tests_not_run` en la condición de las críticas |

## Not run

- El panel de operador (`apps/admin`) contra la API nueva: su «Promover» no manda
  cuerpo y ahora recibe 422 hasta que pida el motivo (ver `fix.md`).
