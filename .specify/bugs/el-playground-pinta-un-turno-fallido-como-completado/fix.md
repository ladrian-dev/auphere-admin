# Bug Fix: el Playground pinta un turno fallido como «Completado · 0 tokens · 0 ms»

- **Slug**: el-playground-pinta-un-turno-fallido-como-completado
- **Fixed**: 2026-09-23
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

El handler del worker deja constancia de por qué usó el texto de emergencia
(`AgentState.turn_failure`: `llm_failed` con el error del proveedor, o
`empty_response`). El traductor SSE lo convierte en un evento `turn.failed` (una
vez por run), el `RunHandle` lo anota y `start_run` cierra el run como `error` con
`reason` en `run.completed` aunque el driver haya terminado limpio. La consola
guarda el motivo y el inspector lo cuenta en una frase; la burbuja con el texto de
emergencia se conserva porque es lo que recibiría un cliente. Lo que recibe el
cliente final por el canal **no cambia**.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/runtime/state.py` | añadido `turn_failure` | Con el contrato escrito al lado |
| `apps/worker/src/nexus_worker/runtime/pipeline.py` | modificado | `turn_failure` en las dos ramas de fallback; viaja en el `return` del handler |
| `apps/api/src/nexus_api/api/qa_streaming.py` | modificado | `_TranslatorState.turn_failure_emitted`; `on_chain_end` emite `turn.failed`; `RunHandle.failure_reason`; `_push_event` anota; `start_run` cierra como `error` con `reason` |
| `apps/api/src/nexus_api/api/console/playground.py` | docstring | `turn.failed` en la lista de eventos del stream |
| `apps/api/tests/unit/test_qa_streaming_translator.py` | añadidos 2 tests | una sola emisión; salida sana no emite |
| `apps/api/tests/unit/test_qa_streaming_orchestrator.py` | añadido 1 test | driver limpio + `turn.failed` → `run.completed` `error` con `reason`, `on_complete` ve `error` |
| `apps/console/src/components/playground/transcript.ts` | modificado | `Turn.failureReason` desde `run.completed.reason` |
| `apps/console/src/components/playground/turn-inspector.tsx` | modificado | Frase por motivo conocido; `text-destructive` (contraste) en vez de `text-status-danger` |
| `apps/console/src/i18n/lanes/playground.ts` | añadidas 2 claves | `playground.run.reason.llm_failed` / `.empty_response` |
| `apps/console/src/components/playground/__tests__/transcript.test.ts` | añadidos 2 tests | error con motivo; run sano sin motivo |

## Diff Highlights

```py
# worker pipeline.py — rama llm_failed
final_text = _EMPTY_RESPONSE_FALLBACK
turn_failure = {"kind": "llm_failed", "detail": str(exc)}
break
…
return {"tool_calls": envelopes, "response": final_text, "response_model": …, "turn_failure": turn_failure, …}
```

```py
# api qa_streaming.py — start_run
else:
    if handle.failure_reason:
        status = "error"
        error = handle.final_error or handle.failure_reason
…
"status": status,
**({"error": error} if error else {}),
**({"reason": handle.failure_reason} if handle.failure_reason else {}),
```

```tsx
// console turn-inspector.tsx
{turn.failureReason && isKnownReason(turn.failureReason) ? t(REASON_KEY[turn.failureReason]) : turn.error}
```

## Tests Added or Updated

- API traductor: `test_turn_failure_in_node_output_becomes_turn_failed_once`,
  `test_healthy_node_output_emits_no_turn_failed`.
- API orquestador: `test_turn_failed_closes_the_run_as_error_with_reason`.
- Consola: «a turn that fell back to the emergency text closes as error with its
  reason», «a healthy run has no failure reason».

## Local Verification

```
uv run --directory apps/api ruff check … && ruff format … && mypy --strict qa_streaming.py state.py pipeline.py   # limpios
uv run pytest tests/unit/test_qa_streaming_translator.py tests/unit/test_qa_streaming_orchestrator.py -q
  26 passed
pnpm exec tsc --noEmit && pnpm exec eslint --max-warnings 0 src/components/playground …   # limpios
NODE_OPTIONS=--experimental-require-module pnpm exec vitest run src/components/playground src/i18n
  Test Files 6 passed · Tests 37 passed
```

En el navegador (API sin claves de modelo, cliente `panaderia-la-espiga`), al
enviar «¿Hacéis pan sin gluten?»: burbuja con el texto de emergencia, e inspector
**«Estado: Error … El turno falló. El modelo no respondió. Lo que ves es el texto
de emergencia que recibiría un cliente. Revisa el modelo del cliente o inténtalo de
nuevo.»** La fila `qa.runs` queda en `error` con el error del proveedor.

## Deviations from Assessment

Ninguna. El worker no tiene test unitario propio de la rama de fallback (el handler
exige un bundle completo); el contrato lo fijan los tests del traductor y del
orquestador sobre la misma forma de salida.

## Follow-ups

- Tokens 0 / latencia 0 ms en un turno fallido siguen siendo ciertos pero poco
  útiles; con el estado «Error» dejan de engañar. Un «—» en su lugar es cosmético
  (bloque D del plan).
- Los hilos nacen «Untitled» (A7 del plan).
