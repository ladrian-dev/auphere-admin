# Bug Verification: el Playground del panel prueba el agente sin sus conectores

- **Slug**: playground-del-panel-sin-agente
- **Tested**: 2026-11-16 (local)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verificado en local; sin desplegar ni probar en staging

## Red before the fix

`test_panel_playground_tests_the_agent.py`, contra el `qa.py` de `develop`: 4 en rojo.
El primero muestra el síntoma de staging: con el estado que manda el Playground,
`_load_tool_policy` bloquea las dos herramientas del conector activado
(`tienda_test.list_items` y `tienda_test.create_order`), y `state.get("agent_id")` es
`None`.

Las dos pruebas que se añadieron después, también en rojo contra lo de `develop`:

- `test_the_real_qa_graph_offers_the_agents_connector_tools`: el modelo no recibe ninguna herramienta (`set()`), con Quédate conectado y activado.
- `test_agents_api.py::test_a_playground_thread_from_before_agents_runs_with_the_principal`: el estado de la consola sale sin `agent_id`.

## Green after the fix

En una base propia (`nexus_test_pgagent`, Redis 14), sin otra ejecución sobre ella:

- `test_panel_playground_tests_the_agent.py`: 4 passed.
- `test_qa_thread_agent_within_tenant.py`: 2 passed.
- Batería de lo tocado y de lo que usa estas rutas, **1739 passed** en 6 min 44 s:
  - los dos archivos nuevos;
  - `test_44_agent_within_client.py`;
  - `test_qa_endpoints.py`, `test_qa_metrics.py`, `test_qa_playground_metering.py` y `test_qa_streaming_endpoints.py`;
  - `test_8_qa_thread_isolation_by_operator.py`, `test_9_qa_concurrent_isolation.py`, `test_10_qa_runs_rls.py` y `test_11_qa_web_channel_isolation.py`;
  - `test_console_scope.py`;
  - `test_agents_api.py` y `test_companion_trial.py`;
  - `connectors/test_playground_never_reaches_the_business.py` y `connectors/test_activations.py`.
- Tras añadir la prueba de la consola y la del grafo real, se repitieron los archivos que
  cambiaron (los dos nuevos, `test_agents_api.py`, `test_44`, `test_qa_streaming_endpoints.py`
  y `test_qa_endpoints.py`): **52 passed**.
- Panel: `pnpm typecheck` en verde. `vitest run src/components/qa src/app/(dashboard)/tenants/[id]/agent/__tests__`: 34 passed. `eslint` de lo tocado, limpio.
- `./scripts/verify.sh lint`: todo verde.

## Not verified

- **En el navegador, contra el stack real.** El Playground con un agente de la consola
  nueva y su conector («Prueba Quédate 061») no se ha probado: el arreglo no está en
  staging. Lo más cerca en local es `test_the_real_qa_graph_offers_the_agents_connector_tools`:
  el grafo de verdad, pero sin modelo de verdad y sin la API de Quédate. Para darlo por cerrado, abrir allí el Playground del cliente, mandar un
  mensaje que pida una herramienta de Quédate y ver en el inspector que la llamada
  aparece, y no «no tool».
- Las suites completas (`verify.sh py`) no se corrieron, como manda la regla del repo.
