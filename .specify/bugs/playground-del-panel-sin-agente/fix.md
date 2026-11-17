# Bug Fix: el Playground del panel prueba el agente sin sus conectores

- **Slug**: playground-del-panel-sin-agente
- **Fixed**: 2026-11-16
- **Assessment**: ./assessment.md
- **Status**: applied, sin desplegar

## Summary

El hilo del Playground fija su agente al crearse y cada turno lo lleva en el estado,
como el canal. En la consola nueva, el turno ya encuentra la activación del agente y
le ofrece sus herramientas de conector. Los hilos que nacieron sin agente prueban el
principal y quedan sellados con él la primera vez que corren. En el panel, el
Playground deja elegir el agente con `?agent=`, y la insignia dice el modo del hilo
en pantalla.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/api/qa.py` | modified | `ThreadCreate.agent_id` (activo y del cliente o 404, por RLS y por `tenant_id`); `ThreadOut.agent_id`; `thread_agent_id` (principal sellado en los hilos NULL); `qa_turn_state`, un solo constructor del estado para `/send` y `/runs` |
| `apps/api/src/nexus_api/api/console/playground.py` | modified | `start_run` usa `thread_agent_id` y `qa_turn_state`: un hilo de la consola de antes de la spec 030 tenía el mismo bloqueo |
| `apps/admin/src/lib/qa-api.ts` | modified | `QAThread` trae `agent_id` y `dry_run`; `QAThreadCreateInput.agent_id` |
| `apps/admin/src/lib/qa-playground-agent.ts` | added | Qué agente se prueba y qué hilos son suyos (compartido por las dos páginas) |
| `apps/admin/src/components/qa/playground-shell.tsx` | modified | Insignia «Dry run» / «En vivo» según el hilo; el hilo nuevo se abre con el agente elegido; `?agent=` se conserva al cambiar de hilo; nombre del agente en el encabezado |
| `apps/admin/src/components/qa/thread-list.tsx` | modified | «· en vivo» en los hilos en vivo |
| `apps/admin/src/app/(dashboard)/tenants/[id]/agent/agent-picker.tsx` | modified | `allowCreate` para ocultar «Nuevo agente» donde solo se elige |
| `apps/admin/src/app/(dashboard)/qa/[tenantId]/chat/page.tsx` | modified | Lee `?agent=`, filtra los hilos y pasa el selector |
| `apps/admin/src/app/(dashboard)/tenants/[id]/playground/page.tsx` | modified | Lo mismo en la pestaña Playground del cliente |
| `apps/api/tests/isolation/test_44_agent_within_client.py` | modified | La razón de `qa.threads` dice ahora que el turno lee su `agent_id` y dónde se prueba |
| `apps/api/tests/isolation/README.md` | modified | Fila del test de aislamiento nuevo |
| `docs/qa-playground/runbook.md` | modified | Spec viva: elegir el agente, la insignia ya no es «siempre DRY RUN», guarda 8 |
| `apps/admin/src/components/qa/playground-shell.tsx` (`AgentsUnreadable`) | modified | Estado de error del selector: si la lista de agentes no se lee, lo dice |

## Tests Added or Updated

- `tests/integration/connectors/test_panel_playground_tests_the_agent.py`, en un cliente de la consola nueva con un conector activado, por los endpoints del panel y con el grafo sustituido por uno que guarda el estado:
  - `test_a_new_thread_tests_the_principal_with_its_connector`: `/runs` y `/send` llevan el agente y la política real no bloquea nada.
  - `test_a_thread_from_before_tests_the_principal_and_keeps_it`: un hilo con `agent_id` NULL corre con el principal y queda sellado.
  - `test_a_thread_for_another_agent_tests_that_agent`
  - `test_an_archived_agent_cannot_open_a_thread`: 404.
  - `test_the_real_qa_graph_offers_the_agents_connector_tools`: el grafo de QA de verdad (dry run, proveedor en memoria) por `/send`, con Quédate conectado y activado. `quedate.search_listings` llega a la llamada del modelo. Sin el arreglo, el modelo no recibe ninguna herramienta, que es lo que se vio en staging.
- `tests/unit/test_agents_api.py::test_a_playground_thread_from_before_agents_runs_with_the_principal`: la consola, con un hilo `agent_id` NULL, corre con el principal y lo sella. En rojo sin el cambio de `console/playground.py`.
- `tests/isolation/test_qa_thread_agent_within_tenant.py`:
  - `test_a_thread_cannot_test_another_clients_agent`: 404 y ningún hilo creado.
  - `test_a_thread_without_agent_seals_its_own_clients_principal`: el agente del otro cliente es más antiguo, y aun así se sella el principal propio.
- `apps/admin/src/components/qa/__tests__/playground-agent-and-mode.test.tsx`: la insignia sigue al `dry_run`; el POST lleva el `agent_id` elegido y la URL conserva `?agent=`; sin lista de agentes no se manda `agent_id`; el filtro de hilos y la elección del agente.
- Las fábricas de `QAThread` de `inspector-drawer`, `resume` y `thread-list` traen los dos campos nuevos.

## Local Verification

- **Antes del arreglo** (`qa.py` original, test nuevo): rojo con el síntoma de staging. `_load_tool_policy` con el estado del turno bloquea `tienda_test.list_items` y `tienda_test.create_order`, y `state.get("agent_id")` es `None`.
- **Después**: ver `test.md`.
- `./scripts/verify.sh lint`: todo verde (ruff, format y `mypy --strict` de los paquetes).
- `pnpm typecheck` en `apps/admin`: verde.
- `vitest run src/components/qa src/app/(dashboard)/tenants/[id]/agent/__tests__`: 34 en verde. `eslint` de los archivos tocados, limpio.
- `/cso --diff` (código): 0 hallazgos. Dos notas fuera del diff, abajo.
- Puertas de UI del workspace (`ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens`), en estático y sin pintar: ningún 🔴. De los 🟡 se arreglaron:
  - se leen 200 hilos antes de filtrar por agente;
  - el shell no se vuelve a montar al cambiar de agente, así que el selector no pierde el foco;
  - el selector va en línea en el encabezado y no pinta una caja vacía con un solo agente;
  - las dos insignias tienen la misma caja;
  - la explicación del modo también llega a los lectores de pantalla;
  - «· en vivo» va en color de aviso.
- Queda un 🟡, que viene de antes: la insignia dice el modo del hilo al cargarlo. Si alguien lo cambia por la API con la página abierta, no se entera hasta recargar.

## Deviations from Assessment

- El filtro de hilos por agente se hace en la página (con la lista de agentes, que ya trae `is_principal`), no con un parámetro nuevo de `GET /qa/threads`: así la lista no tiene que resolver el principal sin el contexto del cliente.

## Lo que se revisó y no se tocó

- **Crear un hilo en vivo desde el panel (ADR-024).** No entra: es funcionalidad nueva y abre una frontera de confianza. Lo que hay hoy: la API lo admite (`POST` con `dry_run: false` o `PATCH`). Además, el BFF del panel (`app/api/qa/threads/route.ts`) reenvía el cuerpo tal cual, así que un operador QA ya puede crearlo desde el navegador con un `fetch`, aunque no haya botón. La insignia y la lista ahora lo dicen cuando pasa. Propuesta de spec aparte.
- **La escalada que se arrastra a los siguientes hilos del mismo operador.** No se ha reproducido. Revisado en el código:
  - Cada hilo tiene su cliente (`qa::{operador}::{hilo}`), su conversación y su checkpoint (`thread_id` = id del hilo).
  - El escalado a una persona (`escalate.escalate_to_human`) declara efectos y el dry run lo intercepta. En vivo solo cambia la conversación del hilo.
  - El escalado de modelo del router (`router_escalations`, `pinned_model`) vive en el checkpoint del hilo.
  - El panel vacía los mensajes al cambiar de hilo (`useQARuntime`).
  - El único canal entre hilos que aparece es la memoria del agente. Con `runtime_memory_tool` activado, el modelo puede escribir en `/memories/tenant/…`, que no es de ningún cliente final y que leen todos los turnos siguientes: los del Playground y los de los clientes reales. La herramienta de memoria no es MCP, así que el dry run no la intercepta. Si en staging el agente de prueba tenía la memoria activada, una nota del tipo «hay una escalada pendiente» explicaría lo que se vio.
  - Para confirmarlo: `runtime_memory_tool` de la versión activa de ese agente y las filas de `agent_memories` con `customer_id IS NULL` de ese cliente.

## Follow-ups

- Sin desplegar: la rama sale de `develop` (`bcd80129`) y staging no tiene el arreglo. Falta probar en el Playground de staging un agente de la consola nueva con su conector («Prueba Quédate 061»).
- Mismo hueco en otros dos caminos, sin tocar porque no son el Playground. Arman el estado del turno sin `agent_id`, así que en la consola nueva el turno sale sin conectores:
  - `apps/worker/src/nexus_worker/streams/owner_fanout.py`: el turno que reentra tras la respuesta del dueño. Es un camino de canal real.
  - `apps/api/src/nexus_api/services/evals/pipeline_driver.py`: las evaluaciones, que preparan el cargador con la versión pero no la nombran en el estado.
- Bug aparte, sin abrir: el Playground en dry run puede escribir memorias de todo el cliente (contra el requisito 20.1 de la 047: «ningún cambio en … datos del cliente»).
- Spec aparte, sin abrir: crear y alternar hilos en vivo desde el panel (ADR-024), con su auditoría y su confirmación.
