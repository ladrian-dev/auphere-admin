# Bug Verification: el clasificador contesta al cliente en vez de clasificar

- **Slug**: el-clasificador-contesta-en-vez-de-clasificar
- **Tested**: 2026-11-08
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

Las pruebas pasan con LiteLLM real hasta un servidor local que hace de Anthropic y de OpenAI, y
con el doble del proveedor. Es `partial` porque **no se ha hecho ninguna llamada a Anthropic ni a
OpenAI** y no está desplegado: que Haiku 5.5 respete la herramienta forzada se sabe por cómo
funciona `tool_choice`, no por haberlo visto.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Las pruebas nuevas, antes | `cd apps/worker && uv run pytest tests/unit/test_classifier_reaches_the_provider.py` | fail | 17 failed, 12 passed. El nodo con la conversación sale `fallback` en vez de `book` |
| Las mismas, después | igual | pass | 29 passed |
| Worker, lo tocado y lo que llama a `classify` | `uv run pytest` de `test_classifier_reaches_the_provider`, `test_booking_brake`, `test_pipeline_booking_brake`, `test_pipeline_interactive`, `test_llm_resilience`, `test_pipeline_router`, `test_pipeline_reception`, `test_outcome_grader`, `test_skills_pipeline`, `test_router_policy` | pass | 261 passed |
| Worker, todo lo que se llama `classif` | `uv run pytest tests -k classif` | pass | 42 passed, 870 deselected |
| API, el grafo y el freno contra la base | `cd apps/api && uv run pytest tests/integration/models/test_router_in_the_graph.py tests/integration/test_react_loop.py tests/integration/test_booking_brake_turn.py tests/isolation/test_conversation_memory_runtime.py tests/isolation/test_2_tool_whitelist_runtime.py` | pass | 12 passed. Base propia `nexus_test_classify`, Redis 9, en otro proceso que el worker |
| Lint y formato | `cd apps/worker && uv run ruff check src tests && uv run ruff format --check src tests` | pass | |
| Tipos | `uv run mypy --strict src` (y como `scripts/verify.sh lint`, desde `apps/api`) | pass | 144 archivos |
| Llamada real a Anthropic u OpenAI | | not-run | Sin llamadas externas |
| Staging | | not-run | Sin desplegar |
| Suites completas | | not-run | Solo lo tocado, como se pidió |

Pasaban ya antes del arreglo, y por tanto no prueban nada de él, solo que no se rompe lo que ya
era seguro: `test_a_chat_reply_instead_of_a_label_still_lands_safely`,
`test_a_free_text_answer_still_routes_to_fallback` y el caso de texto libre de
`test_the_label_survives_how_a_model_writes_it`. `test_pipeline_interactive.py::TestCapture::test_buttons_call_is_captured_and_loop_breaks`
se puso en rojo con el arreglo por su doble sin `extra`; ver `fix.md`.

## Output Excerpts

```
17 failed, 12 passed in 71.68s (0:01:11)
29 passed in 67.98s (0:01:07)
261 passed in 79.58s (0:01:19)
42 passed, 870 deselected in 89.07s (0:01:29)
12 passed in 48.59s
Success: no issues found in 144 source files
```

## Cómo verificarlo en staging

Tras desplegar `develop`, en CloudWatch Logs Insights sobre `/nexus/staging/runner`, con una
ventana que empiece en el despliegue y unas cuantas conversaciones de prueba (una pregunta de
disponibilidad, una de precio, «quiero hablar con una persona»):

1. Lo que no da etiqueta debe caer a casi cero (antes, 80 de 84):

   ```
   fields @timestamp, tenant_id
   | filter event = "classify.unknown_label_using_fallback"
   | stats count() by bin(1h)
   ```

2. Las intenciones de los turnos vuelven a repartirse (`book`, `info`, `escalate`…), no todas en
   `fallback`:

   ```
   filter event = "handler.turn_complete"
   | stats count() by intent
   ```

3. Clasifica Haiku y no la reserva (si `openai/gpt-5.6-sol` sube, Haiku está rechazando):

   ```
   filter event = "llm.call_complete" and role = "classify"
   | stats count() by model
   ```

4. Ningún intento fallido nuevo al clasificar (un `400` aquí sería el proveedor rechazando el
   forzado, y saldría en todas las llamadas):

   ```
   filter event = "llm.attempt_failed" and role = "classify"
   | stats count() by model, error
   ```

5. El freno deja de cerrar en falso por respuestas que no son YES ni NO:

   ```
   filter event = "booking.brake" and outcome = "classifier_failed_closed"
   | stats count() by bin(1h)
   ```

## Residual Risks

- **El proveedor de verdad.** Que Anthropic acepte `tool_choice` forzado con `thinking`
  desactivado y `max_tokens: 32` en Haiku 5.5 sale de su documentación y del cable que arma
  LiteLLM 1.83.14, no de una llamada. El paso 4 lo diría el primer minuto.
- **El significado de las etiquetas** cambia cómo se clasifica, también con la reserva de
  OpenAI: sin batería de clasificación que lo mida.
- **El proxy de LiteLLM** no está en este camino hoy; si vuelve, sin probar.

## Recommendation

Mantener abierto hasta pasar los cinco pasos en staging. Si el paso 4 sale con `400`, revertir a
`gpt-5.6-sol` para clasificar mientras se mira el cable.
