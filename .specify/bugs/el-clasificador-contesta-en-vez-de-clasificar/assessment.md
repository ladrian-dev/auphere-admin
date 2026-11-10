# Bug Assessment: el clasificador contesta al cliente en vez de clasificar

- **Slug**: el-clasificador-contesta-en-vez-de-clasificar
- **Created**: 2026-11-08
- **Source**: logs de staging (`/nexus/staging/runner`) desde el commit `7055dc60` (2026-11-07,
  «classify messages with a dedicated model, claude haiku 5.5», migración 0221)
- **Verdict**: valid
- **Severity**: critical (P0) — en staging casi ningún turno llega a su manejador: el agente se
  queda sin herramientas de reservas, de cola ni de escalado

## Report (summarized)

Desde que clasifica Claude Haiku 5.5, 80 de 84 llamadas `classify` en staging devolvieron un
texto dirigido al cliente en vez de una etiqueta, por ejemplo
`raw="Soy asistente virtual de IA. No tengo acceso a la disponibilidad de manicura"` con el
evento `classify.unknown_label_using_fallback`. Con `gpt-5.6-sol` (hasta el 2026-11-06)
funcionaba: 1179 llamadas. Las cifras son de los logs que revisó la sesión principal; aquí no
se han vuelto a consultar.

## Symptom

Todo turno va a la intención `fallback`, y `_INTENT_CATEGORIES["fallback"]` es `()`
(`apps/worker/src/nexus_worker/runtime/pipeline.py`): el agente responde sin `reservas.*`, sin
`escalate.escalate_to_human`, sin la cola. Una pregunta de disponibilidad no puede consultar
huecos y una petición de hablar con una persona no escala. Lo esperado: la etiqueta de
`VALID_INTENTS` que corresponde (`book` para la disponibilidad) y con ella sus herramientas.

## Reproduction

En el cable, con LiteLLM real y un servidor local que hace de Anthropic y de OpenAI
(`apps/worker/tests/unit/test_classifier_reaches_the_provider.py`): el servidor solo da una
etiqueta si la petición la fuerza, y si no contesta al cliente como hizo Haiku en staging.
Antes del arreglo, 17 de 29 pruebas en rojo; entre ellas el nodo `classify` de un agente de hoy
con una conversación de cuatro turnos sale `fallback` en vez de `book`. No se ha reproducido
contra Anthropic de verdad: aquí no se hacen llamadas externas.

## Root Cause Hypothesis

Confirmada en el código, con confianza alta; la conducta del modelo la dicen los logs.

1. **La forma de la petición.** `make_classify_node` mandaba una instrucción `system` y
   después **toda la conversación como turnos de chat**, `user`/`assistant` alternos, terminada
   en el mensaje del cliente. Para un modelo de chat eso es un turno que contestar, y Haiku 5.5
   lo contestaba. `gpt-5.6-sol` seguía la instrucción a pesar de la forma.
2. **Nada obligaba a una etiqueta.** La salida era texto libre y la única guía era «Respond with
   the single label». El `raw` del ejemplo acaba a media frase: es el corte de `max_tokens=32`
   de `CLASSIFY_ON_ANTHROPIC`, lo que confirma que el modelo escribía prosa y no una palabra.
3. **Por qué las pruebas no lo vieron.** La prueba de `7055dc60` comprobaba que la llamada llega
   a Haiku con 32 tokens y sin razonamiento, pero su doble contestaba `book` a cualquier
   petición: nada miraba la forma de lo que se manda.

**El clasificador tipado** (`_classify_routed`, spec 047 T140) tenía la misma forma
(`system` + historial + `user`). Hoy no corre para un agente sin `model_policy` mientras ningún
despliegue certificado para `classify` pase el filtro, pero con un despliegue sin salidas
estructuradas estrictas tendría el mismo problema.

**El freno de citas** (spec 056, `booking_brake.claims_booking`) ya mandaba el borrador como un
único `user`, pero con salida libre: una respuesta que no es YES ni NO cierra en falso (cuenta
como afirmación), y el turno reintenta o pasa a una persona. No se ha medido cuántas veces le
ha pasado en staging.

## Proposed Remediation

**Preferred** (la elegida por Luis): mantener Haiku 5.5 y forzar la salida a una etiqueta.

1. La conversación va como **dato dentro de un solo mensaje `user`**: una línea por mensaje
   entre etiquetas `<conversation>`, el último del cliente marcado, y la instrucción pide
   exactamente una etiqueta de `VALID_INTENTS`. Igual para el clasificador tipado.
2. La salida, **forzada**: `response_format` con un JSON Schema de un campo `label` con su
   `enum`. OpenAI lo toma tal cual; LiteLLM lo convierte para Anthropic en una herramienta
   forzada (`json_tool_call` con `tool_choice`) y devuelve sus argumentos como texto.
3. El freno, con el mismo mecanismo y `enum` `["YES", "NO"]`, sin cambiar que falle cerrado.
4. La lectura de la etiqueta acepta el JSON forzado o la palabra suelta; lo demás sigue
   siendo `fallback`.

**Alternatives**:

- **Volver a `gpt-5.6-sol` para clasificar.** Lo más rápido (configuración), pero deshace el
  requisito 69 y deja la petición con la forma que falla con cualquier modelo de chat.
- **`tools` + `tool_choice` explícitos por `acomplete_with_tools`.** Es lo mismo en el cable
  de Anthropic, pero añade `context_management` a la llamada, pone una herramienta en
  `LLMCall.tools` (lo que las pruebas de aislamiento leen como herramientas del agente) y hace
  correr el `tool_caller` de los dobles también en la clasificación. Descartada.
- **Prefill de `assistant`** con el principio de la respuesta: sigue siendo forma de chat y no
  obliga a nada en el resto de la salida.
- **Reintentar con el siguiente modelo de la cadena cuando la respuesta no es una etiqueta.**
  Arreglaría el síntoma pagando dos o tres llamadas por turno; con la salida forzada no hace
  falta. Queda como pregunta abierta.

**Files likely to change**: `apps/worker/src/nexus_worker/runtime/{llm,pipeline,booking_brake}.py`,
`docs/modelos-y-router.md`.

**Tests to add or update**: `apps/worker/tests/unit/test_classifier_reaches_the_provider.py`.

## Risks & Considerations

- **Garantía 2 (lista de herramientas).** La herramienta `json_tool_call` solo existe en el
  cable hacia Anthropic: la crea LiteLLM a partir de `response_format` y devuelve su resultado
  como texto. Nadie la ejecuta, el nodo `classify` no ejecuta herramientas y `LLMCall.tools`
  sigue vacío. Las herramientas de cada manejador no cambian.
- **Garantía 7 (una petición por llamada).** Sigue siendo una petición por intento, con la
  misma cadena y la misma reserva.
- **Inyección.** El mensaje del cliente es dato: la salida solo puede ser una etiqueta, las
  etiquetas `<conversation>` dentro de un mensaje se quitan y los saltos de línea se juntan,
  así que un mensaje no puede cerrar la cita ni fingir un turno.
- **Proveedores sin cable comprobado.** El forzado solo va a `anthropic/` y `openai/`. Un
  modelo de otro proveedor asignado a `classify` recibiría un parámetro sin verificar y
  fallaría siempre; ese recibe la petición de siempre.
- **Medición.** La tarea sigue siendo `classify` por el rol; `has_tools` del evento
  `llm.call_complete` sigue en falso, porque la herramienta no viene de quien llama.
- **El significado de cada etiqueta** va ahora en la instrucción. Cambia cómo se clasifica
  (para eso está), también con `gpt-5.6-sol` de reserva: ver «Open Questions».

## Open Questions

- **Para Luis: el significado de cada etiqueta** (`_INTENT_MEANINGS` en `pipeline.py`). Se
  escribió a partir de las herramientas de cada categoría: «disponibilidad» va a `book` porque
  solo ahí está `reservas.find_slots`. Decidido sin él; por revisar.
- ¿Debe ir al siguiente modelo una respuesta que no es una etiqueta? Hoy no: se queda en
  `fallback`, como antes.
- El camino por el proxy de LiteLLM (1.74.15) no está probado con `response_format`. Staging va
  directo al proveedor desde el 2026-11-03; si producción vuelve al proxy, hay que verlo.
