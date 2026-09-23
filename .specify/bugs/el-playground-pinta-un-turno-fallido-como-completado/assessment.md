# Bug Assessment: el Playground pinta un turno fallido como «Completado · 0 tokens · 0 ms»

- **Slug**: el-playground-pinta-un-turno-fallido-como-completado
- **Created**: 2026-09-23
- **Source**: auditoría de la consola, evidencia viva del 2026-09-22 (KB `nexus/INFORME-AUDITORIA-CONSOLA-2026-09-22.md`, fila «c. Playground»); ya anotado el 1-sep como E1/N3 en `PLAN-ACCION-E2E-2026-08-30.md`
- **Verdict**: valid
- **Severity**: high

## Report (verbatim)

> Al enviar «Hola, ¿tenéis pan integral hoy?» la respuesta **sí llega**: «Disculpa,
> tuve un inconveniente…». Pero el detalle del turno dice **«Estado: Completado ·
> Tokens 0 / 0 · Latencia 0 ms · Modelo —»** y la API no escribe ni una línea de
> error (`preview_logs` en nivel error vacío; solo `qa.pipeline.compiled`).

Stack local sin `ANTHROPIC_API_KEY` ni `OPENAI_API_KEY`: el router de modelos agota
reintentos y fallback en cada turno.

## Symptom

Un partner prueba su agente, recibe un texto de disculpa y el inspector le dice que
el turno se completó. No hay forma de saber desde la consola que el modelo no
respondió, ni por qué. La burbuja es el texto de emergencia que recibiría un
cliente final —eso es correcto y hay que enseñarlo—, pero el estado del turno es
falso (principio V).

## Reproduction

1. API arrancada sin claves de modelo válidas (o con un modelo inválido en los
   bindings del tenant, que es el caso real de `demo-farmacia-amacrux` en agosto).
2. Playground de cualquier cliente con agente publicado → enviar un mensaje.
3. Burbuja: «Disculpa, tuve un inconveniente para completar la respuesta…».
   Inspector: Estado «Completado», tokens 0/0, latencia 0 ms, modelo «—».

## Suspected Code Paths

- `apps/worker/src/nexus_worker/runtime/pipeline.py:1126-1133` — el handler
  captura la excepción del router (`handler.llm_failed`), pone
  `final_text = _EMPTY_RESPONSE_FALLBACK` y **sigue como un turno normal**. Lo mismo
  en `:1221-1227` para una respuesta vacía (`handler.empty_response`). El estado del
  grafo no guarda que hubo fallo.
- `apps/api/src/nexus_api/api/qa_streaming.py:449-482` — `start_run` cierra con
  `status="completed"` salvo que el driver lance; el driver no lanza porque el
  pipeline no lanzó.
- `apps/api/src/nexus_api/api/qa_streaming.py:140-227` — `translate_event` no
  mira nada del estado de salida salvo el UCM.
- `apps/console/src/components/playground/transcript.ts:182-192` — el reductor
  pinta `run.completed.status` tal cual; `turn-inspector.tsx:51-55` solo enseña
  `turn.error`.

## Root Cause Hypothesis

La red de seguridad del handler (responder algo neutro antes que dejar al cliente
sin nada) se diseñó para el canal y está bien ahí. Pero convierte el fallo en un
éxito para todo lo que observa el turno: el Playground, la fila `qa.runs` y la
traza. Falta un canal de datos para «esto es el texto de emergencia, y por esto».

## Proposed Remediation

1. **Worker**: el handler deja `turn_failure = {"kind": "llm_failed" | "empty_response",
   "detail"}` en el estado cuando usa el fallback (`AgentState.turn_failure`). No
   cambia lo que recibe el cliente final.
2. **API**: `translate_event` emite `turn.failed {reason, detail}` una vez cuando ve
   `turn_failure` en la salida de un nodo; `_push_event` anota `failure_reason` y
   `final_error` en el `RunHandle`; `start_run` cierra el run como `error` con
   `reason` en `run.completed` aunque el driver haya terminado limpio. El
   `_scrub_stream` del Playground sigue sustituyendo `error` por la frase humana;
   `reason` viaja intacto.
3. **Consola**: el turno guarda `failureReason`; el inspector muestra «El turno
   falló. El modelo no respondió. Lo que ves es el texto de emergencia que
   recibiría un cliente…» con estado «Error». La burbuja se conserva.

## Files likely to change

- `apps/worker/src/nexus_worker/runtime/state.py`, `pipeline.py`
- `apps/api/src/nexus_api/api/qa_streaming.py`
- `apps/api/tests/unit/test_qa_streaming_translator.py`, `test_qa_streaming_orchestrator.py`
- `apps/console/src/components/playground/transcript.ts`, `turn-inspector.tsx`,
  `__tests__/transcript.test.ts`, `src/i18n/lanes/playground.ts`

## Tests to add or update

- Traductor: `turn_failure` en la salida de un nodo → `turn.failed` una sola vez;
  salida sana → nada.
- Orquestador: driver que emite `turn.failed` y termina limpio → `run.completed`
  con `status=error`, `reason`, `error`; `on_complete` ve `final_status=error`.
- Reductor de la consola: `run.completed {status: error, reason}` → turno `error`
  con `failureReason`; run sano → `failureReason=null`.

## Risks & Considerations

- El worker corre en producción para el canal: el cambio solo **añade** una clave
  al estado; `dispatcher.py` y el resto de nodos la ignoran. Sin migración.
- El panel de operador (`/qa`) comparte `qa_streaming`: verá también `turn.failed`
  y runs en `error` con `reason` — es lo deseable, y su UI ignora eventos que no
  conoce.
- Los eventos SSE del Playground de partner declarados en el docstring de
  `stream_run` no incluían `turn.failed`; se añade.

## Open Questions

- Ninguna.
