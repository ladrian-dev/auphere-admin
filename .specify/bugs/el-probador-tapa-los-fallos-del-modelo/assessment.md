# Bug Assessment: el chat de prueba y las pruebas del agente esconden que el modelo no respondió

- **Slug**: el-probador-tapa-los-fallos-del-modelo
- **Created**: 2026-11-03
- **Source**: pasted text (Luis, sesión del 2026-11-03) y logs de staging
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

Si el modelo no responde, el chat de prueba del agente devuelve `200` con una
disculpa fija como si fuera la respuesta del agente; las pruebas dan 0 de 17 en un
trabajo que termina `done`, y parece que el agente está mal cuando ni llegó al
modelo; la alarma `turn_error_burst` no lo ve.

## Symptom

Quien construye un agente no puede distinguir «el agente lo hace mal» de «no se pudo
probar porque el modelo falló». Lo esperado es que la consola lo diga, y que un fallo
así no cuente como fallo del agente.

## Reproduction

Visto en staging, cliente `6d3e5a76` (`jemma-s-hair`), 2026-11-03:

1. El partner no tiene clave en el proxy (`missing partner virtual key`).
2. `POST …/test-runs` a las 19:58:12 → trabajo `702d794a`.
3. Los logs dan 51 `jobs.tests.attempt_failed` con `error=LLMProxyUnavailable`: el
   modelo del agente falló (`handler.llm_failed`), y después el del cliente simulado
   lanzó una excepción.
4. `suite.run` con `passed=0 failed=17`; `jobs.finished status=done`.
5. En el chat, `POST …/playground/sessions/…/messages` responde `200` con el texto de
   emergencia.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/runtime/pipeline.py:1991` — deja `turn_failure` en el
  estado y responde con `_apology`. Es correcto para un canal.
- `apps/worker/src/nexus_worker/simulation/runner.py:264` — `run_turn` lee `response`
  y descarta `turn_failure`. **Aquí se pierde** para el playground y las pruebas.
- `apps/api/src/nexus_api/api/console/agent_playground.py:298` — `TurnOut` no tiene
  dónde decirlo.
- `apps/worker/src/nexus_worker/simulation/customer.py:189` — un fallo del modelo del
  cliente simulado sube como excepción cualquiera.
- `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py:167` — esa excepción se
  apunta como «El agente no terminó el turno», `passed=False`.
- `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py:182` — un fallo del juez
  no lo captura nadie: tumba el trabajo con `internal`.
- `apps/api/src/nexus_api/services/testing/runs.py:315` — `finish_run` quita
  `stale` aunque no se haya probado nada.
- `apps/worker/src/nexus_worker/streams/consumer.py:159` — el único que alimenta
  `nexus:alert:turn_errors:*`, y solo cuando el turno lanza (`TurnRetry`).

## Root Cause Hypothesis

Confianza alta. La red de seguridad del handler convierte el fallo en un texto, y el
chat del cliente (`qa_streaming`) aprendió a leer `turn_failure` en septiembre
(`el-playground-pinta-un-turno-fallido-como-completado`), pero la simulación de la
spec 047 (`simulation/runner.py`) se escribió después y no lo lee. Ninguna de las dos
superficies nuevas tiene una forma de decir «no se pudo probar».

## Proposed Remediation

**Preferred**:

1. `TurnOutcome.failure` en `run_turn`, una sola vez para el playground y las pruebas:
   `llm_failed`, `no_model` o `empty_response`. Un `handoff` o un `turn_limit` no es un
   fallo del modelo: lo decidió el router.
2. **Playground**: `TurnOut.failure {reason}`, con `200`. El turno existe, la burbuja
   es lo que recibiría un cliente, y se guarda en la conversación. El detalle del
   proveedor no sale de la API.
3. **Pruebas**: `stop = model_failed`, `passed = NULL` en cuanto falla el modelo del
   agente, el del cliente simulado o el del juez cuando su veredicto decide. Un estado
   propio, `model_failed` («No se pudo probar»), que no entra en «Falla», en la nota ni
   en «Arreglar», y deja la prueba desactualizada para que la siguiente pasada la repita.
4. **Si no se pudo probar nada**: la pasada queda `failed` con `stopped =
   model_unavailable` y el trabajo falla con ese código, como `build_budget_exhausted`.
   Si se pudo probar algo, el trabajo termina `done` y dice cuántas no.
5. **La alarma**: los fallos de la simulación **no** van a `turn_error_burst`, porque
   esa alerta escribe `platform.turn_error_burst` y `operator_alerts.py` lo convierte en
   un WhatsApp al dueño del negocio. Un partner que prueba su borrador no puede despertar
   al negocio. Van a un tipo propio, `simulated_model_failure_burst`, sin fila de
   auditoría, con su alarma en Terraform y su línea en `docs/correos.md`.

**Alternatives**:

- Responder `502` en el playground: se perdería lo que recibiría un cliente y la
  conversación se quedaría a medias, con un turno en la base que el chat no enseña.
- Reutilizar `unknown` («No sé») para las pruebas: ya significa que el juez no pudo
  decidir, y el partner no sabría qué hacer con él.
- Contar en `turn_error_burst`: es lo que pedía el enunciado como primera opción; se
  descarta por el WhatsApp al negocio.

**Files likely to change**: `simulation/{runner,customer,failures}.py`,
`jobs/handlers/agent_tests.py`, `streams/platform_watcher.py`,
`api/console/agent_{playground,tests}.py`, `services/testing/runs.py`,
`services/publishing.py`, una migración del `CHECK` de `stop`, Terraform, los documentos
y en `apps/console` el chat, la lista, la tarjeta y la barra de guardar.

**Tests to add or update**: integración del playground y de la suite con modelos que
fallan; unitarias del vigilante; pruebas de componente del chat y de la lista.

## Risks & Considerations

- La migración cambia un `CHECK`. Una versión vieja del worker no escribe `model_failed`,
  así que el orden de despliegue no importa.
- Una prueba crítica que no se pudo probar sigue bloqueando la puerta, con su propio
  código: «no se probó» no es «pasa».
- Un turno que agota sus 120 s sigue contando como fallo del agente: no se sabe de qué
  lado está. Se deja así y se dice.

## Open Questions

- Ninguna que bloquee. Queda para Luis si `turn_error_burst` debe contar también los
  fallos del modelo **en canales**: hoy tampoco los ve (ver `fix.md`).
