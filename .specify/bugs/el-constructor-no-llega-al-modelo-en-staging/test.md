# Bug Verification: en staging, el constructor y sus vecinos no llegan al modelo

- **Slug**: el-constructor-no-llega-al-modelo-en-staging
- **Tested**: 2026-10-29
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Reproducido en local con el proxy obligatorio forzado (`NEXUS_LLM_PROXY_REQUIRED=true`,
el mapa de claves de staging y un `litellm.acompletion` de mentira): los cinco
trabajos registrados, el copiloto, la evaluación y la calibración del operador, la
paráfrasis, las sugerencias semanales y el grader diferido salían sin partner, con
los mismos síntomas que en staging (`builder_unavailable`, `extract_failed`,
`internal`/`missing partner virtual key`). Después del arreglo todos llegan al
modelo con la clave de quien paga. No se ha probado contra el proxy real de staging.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Barrido de trabajos, antes | `pytest tests/integration/test_jobs_reach_the_model_behind_the_proxy.py` | fail | 5 de 5 en rojo: `agent_draft` y `client_builder` vieron `[None]` (`builder_unavailable`), `client_read` `[None]` (`extract_failed`), `tests` y `publish` el juez sin partner (`missing partner virtual key` → `internal`) |
| Barrido de trabajos, después | lo mismo | pass | 5 passed. Parametrizado sobre `default_registry.kinds()`: un tipo nuevo sin su mundo pone la prueba en rojo |
| Consumidor, antes | `pytest apps/worker/tests/unit/test_jobs_consumer.py -k partner` | fail | 3 en rojo: `StartedJob` no sabía de partner |
| Consumidor, después | `pytest apps/worker/tests/unit/test_jobs_consumer.py` | pass | 21 passed: el partner llega al manejador y a lo que lanza en paralelo, dos trabajos de dos partners no cruzan claves, un cliente sin partner no hereda ninguna |
| Barrido de fuentes, antes | `pytest tests/unit/test_llm_proxy_scope_coverage.py` | fail | `sector_tests.py`, `agent_copilot.py`, `paraphrase.py`, `weekly_suggestions_cron.py` construían un `LiteLLMProvider` sin ámbito |
| Barrido de fuentes, después | lo mismo | pass | 5 passed |
| Copiloto, evaluación y calibración, antes | `pytest tests/integration/builder/test_model_calls_behind_the_proxy.py` | fail | 3 en rojo: copiloto `{'none'}`; evaluación y calibración `missing partner virtual key` |
| Copiloto, evaluación y calibración, después | lo mismo | pass | 3 passed: el copiloto con la clave del partner; el operador con la de Auphere (`platform`), nunca con la de un partner |
| Ámbito de plataforma, antes | `pytest tests/unit/test_litellm_proxy.py -k "platform or auphere"` | fail | `ImportError`: no existía |
| Ámbito de plataforma, después | `pytest tests/unit/test_litellm_proxy.py` | pass | 18 passed: la clave de Auphere dentro del ámbito; dentro de un partner cambia quién paga y al salir vuelve; un partner nunca la gasta; sin la entrada `platform`, fail-closed |
| Sugerencias, paráfrasis y grader, antes | `pytest tests/integration/test_deferred_grader.py tests/integration/improvement/test_corrections.py::test_the_paraphrase_goes_out_with_the_partners_key tests/integration/improvement/test_suggestions.py::test_suggestions_are_generated_in_the_worker_inside_each_client` | fail | 3 en rojo: el modelo veía `None` |
| Sugerencias, paráfrasis y grader, después | `pytest` de los cinco archivos de integración tocados | pass | 32 passed |
| Worker | `pytest apps/worker/tests/unit/test_litellm_proxy.py` | pass | 19 passed: el guardia del hop acepta el ámbito de plataforma y sigue rechazando la llamada sin pagador |

## Not run

- El proxy real de staging: falta la entrada `platform` en el secreto (ver `fix.md`).
- Visto de paso, sin arreglar (otro fallo): el rol `build` de los manejadores, el
  copiloto, la paráfrasis y la evaluación no está en `TASK_BY_ROLE` (sí `builder`),
  así que cada llamada del constructor deja `llm.task_missing` y se mide sin tarea;
  con `NEXUS_USAGE_REQUIRE_TASK=1` (las pruebas) falla tras llegar al modelo.
