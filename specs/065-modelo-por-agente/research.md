# Investigación: El modelo de cada agente

**Spec**: [spec.md](spec.md) · **Fecha**: 2026-11-19 · Código leído en `develop` (`39a4dc37`).

Cada decisión lleva su razón y lo que se descartó. Las que dependen de cómo se comporta LiteLLM se comprobaron en el cable contra un servidor de eco local, sin llamar a ningún proveedor (D3). Las de Anthropic, en su documentación y su página de precios del 2026-11-19. Las de producción, en CloudWatch (`/nexus/prod/runner`, 60 días).

Decisiones de Luis del 2026-11-19: oferta de Claude tras pasar en staging (D11), ajuste vivo (D2), reserva de la otra familia (D5), los seis para todos los partners (D11), cobrar todo al partner (D14), un solo sitio para el modelo (D15) y Haiku 5.5 por defecto salvo Jemma (D16).

---

## D1. Precios y pesos de los modelos nuevos

**Decisión.** Opus 5.5 y Sonnet 5.5 entran en `model_profiles` y `model_prices` por la API de Anthropic (`anthropic/claude-opus-5-5`, `anthropic/claude-sonnet-5-5`), copiando contrato, residencia y familia de la fila de Haiku 5.5, como hizo la migración 0221. Tarifas de https://platform.claude.com/docs/en/about-claude/pricing:

| Modelo | Entrada | Escritura caché 5 min | Lectura caché | Salida | Recargo |
|---|---|---|---|---|---|
| Claude Opus 5.5 | 4,00 | 5,00 | 0,20 | 20,00 | ninguno (1M a precio estándar) |
| Claude Sonnet 5.5 | 2,00 | 2,50 | 0,10 | 10,00 | ninguno |
| Claude Haiku 5.5 (ya está) | 0,10 | 0,125 | 0,01 | 0,50 | ×5 si el prompt pasa de 100.000 tokens |

Pesos por carril con la regla de la 0120 y la 0221: peso = precio × multiplicador (2,2) ÷ 10.

| Modelo | Peso entrada | Peso lectura | Peso salida |
|---|---|---|---|
| Opus 5.5 | 0,880 | 0,044 | 4,400 |
| Sonnet 5.5 | 0,440 | 0,022 | 2,200 |

**Razón.** Sin pesos, `metering` registra `unweighted_model` y el turno se mide pero no se debita (`consumer._turn_quota`).

**Descartado.** Los borradores de Bedrock UE: otra credencial, otro precio y otra ruta, sin probar. Siguen como borradores.

**Lo que cuesta una respuesta de Jemma** (tokens del 18-nov, venta ×2,2, con la caché de cada proveedor según su documentación, §D14; sin el razonamiento y con los tokens que cuenta OpenAI):

| | Sol | Opus 5.5 | Terra | Sonnet 5.5 | Luna | Haiku 5.5 |
|---|---|---|---|---|---|---|
| Con la 065 (escritura cobrada en las dos familias) | 0,124 | 0,120 | 0,063 | 0,060 | 0,0066 | 0,0034 |
| Hoy (la escritura de GPT-5.6 no se mide) | 0,102 | 0,120 | 0,052 | 0,060 | 0,0055 | 0,0034 |

Por respuesta: 20.092 tokens de contexto en 1,69 llamadas, de los que 10.087 (50,2 %) salieron de caché con Sol, 110 de salida y la clasificación con Haiku 5.5 (0,0003). Con la escritura cobrada en las dos, cada pareja de la misma gama cuesta casi lo mismo (Sol y Opus, Terra y Sonnet): la diferencia es menor que lo que no se sabe todavía (tokenizador, razonamiento y cuánto se lee con 5 minutos de caché en lugar de 30). Vale la primera: Luis decidió cobrar la escritura de GPT-5.6 (§D14).

## D2. Precedencia y dónde vive la elección

**Decisión.** Agente → `policies.llm.respond_model` de la versión → modelo por defecto de Auphere del entorno (D16). La degradación por presupuesto (WP-20) sigue por encima. La elección vive en `agents` como **ajuste vivo** (decisión de Luis): sin publicar versión. La asignación por cliente desaparece (D15).

**Razón.** Un solo sitio por agente (decisión de Luis). El escalón de la versión se mantiene porque lo escribe una plantilla de semilla (`woocommerce_sales_v1`) y no se elige desde ninguna pantalla; si molesta, se migra igual que el del cliente en otra spec.

**Descartado.** En la versión (`policies.llm.respond_model` o `model_policy`): obliga a publicar, y `model_policy` pasa por el router (D6).

## D3. Lo que recibe cada familia (comprobado en el cable)

Sonda local con LiteLLM 1.83.14 (la del worker), `LITELLM_LOCAL_MODEL_COST_MAP=True`, la clase real `LiteLLMProvider` y un servidor de eco. El mapa local no conoce ninguno de los seis modelos.

**Hacia Anthropic con herramientas, hoy** (los tres 5.5 igual): `POST /v1/messages`, `anthropic-version: 2023-06-01`, beta `context-management-2025-06-27`, `system` con `cache_control`, `max_tokens: 4096` (la reserva de LiteLLM para un modelo que no conoce), sin `temperature` y sin `thinking`.

| Qué | Hacia Anthropic (5.5) | Hacia OpenAI (GPT-5.6) |
|---|---|---|
| `thinking` | Solo como kwarg con `allowed_openai_params=["thinking"]`. Como kwarg solo: `UnsupportedParamsError` sin salir. En `extra_body`: sale anidado y mal. | Quitarlo (ya lo hace `_drop_openai_unsupported`). |
| Esfuerzo | `output_config={"effort": "low"\|"medium"\|"high"}` como kwarg; LiteLLM añade la beta `effort-2025-11-24`. `xhigh` y `max` sin ruta en esta versión. | `output_config` **llega al cuerpo** hoy: añadirlo a `_ANTHROPIC_ONLY_ON_OPENAI`. |
| `reasoning_effort` | **Nunca**: falla en el proceso, se traduce a `budget_tokens` (que los 5.5 rechazan) o, con `"none"`, rompe LiteLLM. | Con herramientas, `extra_body={"reasoning_effort":"none"}`, como hoy. Como kwarg desvía a `/responses`. |
| `tool_choice: "none"` | Sale `{"type":"none"}`: válido. | Con el mapa local, `UnsupportedParamsError` en el proceso: mandarlo en `extra_body`. |
| `tool_choice` forzado | Sale como `any` / `tool`: 400 en Opus y Sonnet 5.5. La respuesta no lo usa; el clasificador no pasa por el modelo del agente. | — |
| Rechazo | `stop_reason: "refusal"` → `finish_reason: "content_filter"`, sin excepción, con el texto parcial si lo hay. | — |
| Historial con razonamiento | LiteLLM coloca `thinking_blocks` delante del `tool_use`, firma intacta. Sin ellos no corrige nada. | LiteLLM **reenvía** `thinking_blocks`, `reasoning_content`, `provider_specific_fields` y `tool_calls[].index`: hay que quitarlos. |
| `system` a mitad de `messages` | LiteLLM lo **sube** al `system` de arriba como bloque nuevo (ver D4). | Se queda en `messages`. |

**Medido el 2026-11-20 (T050-T052), con las entradas de D13 registradas.**
- `thinking` como kwarg **ya pasa** hacia los tres 5.5 sin `allowed_openai_params`: la fila de arriba vale para el mapa local a secas. Se sigue mandando `allowed_openai_params=["thinking"]` por si una entrada faltara; LiteLLM lo consume y no llega al proveedor.
- `tool_choice: "required"` sale como `{"type": "any"}` en los tres: el perfil lo quita para Opus y Sonnet (`FORCED_TOOL_CHOICE`).
- Un rechazo **sin** texto (`content: []`, `stop_reason: "refusal"`) también llega como `content_filter`.
- El `cache_control` de arriba (`cache_control={"type": "ephemeral"}` como kwarg) llega tal cual al cuerpo hacia Anthropic, sin tocar los mensajes: es la forma de caché de la conversación que usa el perfil (§D14).

**Errores que se disfrazan.** `raise_mapped_proxy_failure` convierte cualquier `APIConnectionError` en `LLMProxyUnavailable: proxy unreachable`, también sin proxy: un parámetro inválido parece una caída de red. `llm.attempt_failed` tiene que llevar la clase original.

## D4. El razonamiento dentro del turno: solo se añade, nunca se edita

**Decisión.** Los tres Claude 5.5 responden con razonamiento adaptativo y esfuerzo bajo, y el turno trata lo enviado como un registro que solo crece:

1. `acomplete_with_tools` devuelve `message.thinking_blocks` tal cual (firma y `redacted_thinking` incluidos) con el modelo que los produjo. `_assistant_tool_message` los pone en `thinking_blocks`.
2. **Nada de lo enviado cambia entre dos llamadas del turno** cuando el modelo razona: el `system` de arriba, el conjunto de herramientas y los mensajes anteriores. Hoy dos cosas lo rompen:
   - la última vuelta añade `FINAL_ANSWER_NOTE` como `system`, que LiteLLM sube al `system` de arriba, y el freno de reservas la retira al reintentar;
   - la última vuelta quita `code_execution` de las herramientas cuando hay Skills.

   Para Anthropic, el cierre usa solo `tool_choice: "none"` (fuera de lo que se comprueba), sin nota y con las mismas herramientas. Para OpenAI sigue como hoy.

   **El freno de reservas, por el mismo mecanismo** (comprobado en el cable el 2026-11-20): su reintento añade su nota como `system` (Principio III), y LiteLLM la sube al `system` de arriba como **un bloque nuevo al final**, sin tocar los anteriores. Desde T053 el reintento no retira nada (la nota del cierre ya no está con Claude), así que lo enviado sigue siendo un prefijo y la nota es lo único nuevo. Si Anthropic cuenta un bloque añadido al final del `system` como edición, no se sabe: lo decide la batería real en modo `"error"` (`booking_brake_retry`, T055). Si cuenta, con `drop_block` en prod el reintento pierde los bloques anteriores sin error.
3. Red de seguridad: las llamadas a los 5.5 con razonamiento llevan `thinking.block_binding.prefix_mismatch_behavior = "drop_block"` (beta `thinking-binding-controls-2026-08-01`). Un cambio que se escape descarta el bloque en vez de dar un 400. Comprobado en el cable con 1.83.0 y 1.83.14: el campo sale tal cual y la beta se suma a las que añade LiteLLM (`context-management-2025-06-27,effort-2025-11-24,thinking-binding-controls-2026-08-01`; con Skills, LiteLLM une y ordena las de los dos). **LiteLLM no devuelve `input_transformations`** en la respuesta, así que en producción un descarte no se ve. **Sí hay ruta** (comprobado el 2026-11-20 con 1.83.14): un `CustomLogger` en `litellm.callbacks` recibe en `async_log_success_event` el cuerpo crudo del proveedor como `kwargs["original_response"]` (una cadena JSON), con `input_transformations` dentro y los `metadata` de la llamada (cliente y rol). Registrarlo queda pendiente (T052). La garantía es la batería real en modo `"error"` (D9), que convierte cualquier edición en un fallo visible antes de habilitar un modelo. Buscar una ruta para registrarlo (un callback de LiteLLM con la respuesta original) es parte de T052, sin bloquear.
4. Antes de cada llamada, el transporte sanea por destino: hacia OpenAI quita lo de D3; hacia Anthropic quita los bloques de **otro** modelo.

**Razón.** La firma de cada bloque guarda el `system`, las herramientas y todos los mensajes anteriores. Opus 5.5 lo exige a las cuentas creadas desde el 31-ago-2026 (un bloque reenviado tras una edición es un 400), y Haiku 5.5 tiene la misma comprobación. No sabemos la fecha de la cuenta de Anthropic de Auphere, y no hace falta saberla: el turno se diseña para pasarla en cualquier cuenta. Entre turnos no hay problema: el historial de un turno a otro es solo texto (`pipeline.py`, `history` de `{role, content}`), sin bloques de razonamiento.

Apagar el razonamiento en Sonnet (`between_tools`) o en Haiku (`disabled`) como receta normal tiene fallos conocidos con herramientas (escribir la llamada en el texto, saltarse una herramienta). Opus no deja apagarlo. Esfuerzo bajo para los tres, como recomienda Anthropic.

**Descartado.** Mandar la nota del cierre como texto tras los `tool_result`: mezclaría una instrucción de operador con lo leído, contra el Principio III.

## D5. La reserva es de la otra familia (decisión de Luis)

**Datos de producción (60 días, `/nexus/prod/runner`).**
- Turnos reales que acabaron sin modelo (`handler.llm_failed` fuera de simulación): 66, de 3 clientes, todos entre el 8 y el 22 de octubre. Del 8 al 12, OpenAI sin saldo; del 19 al 22, LiteLLM 1.106, que tumbaba toda llamada con herramientas sin importar el proveedor (una reserva cruzada no lo habría salvado). En noviembre, ninguno.
- El 2026-11-19 entre las 16:58 y las 16:59 UTC, el límite de cuota de OpenAI paró la batería de pruebas de un agente nuevo: 33 `simulation.model_failed` y `suite.stopped`. No eran clientes reales.
- 436 `llm.attempt_failed` por límite de cuota de OpenAI en 60 días, la mayoría reintentos que acabaron bien.

**Decisión.**
1. Cada perfil declara su reserva: los de OpenAI caen a **Claude Sonnet 5.5**; los de Anthropic, a **Terra**. La cadena es: modelo efectivo → reserva de la otra familia. Las reservas propias de las asignaciones de cliente desaparecen con ellas (D15). Vale también para los agentes sin elección.
2. Mientras la reserva no esté habilitada para responder en ese entorno (D11), se usa la reserva de hoy (Sol). Así, al desplegar, nada cambia hasta que la batería real pase.
3. **Cuando la reserva responde una llamada, el resto del turno sigue con ella.** Hoy cada llamada del bucle empieza otra vez por el primero.
4. **Cruce de OpenAI a Anthropic a mitad de turno** (ya hubo `tool_use` de OpenAI): Sonnet 5.5 sigue ese turno con el razonamiento apagado (`thinking: {"type": "between_tools"}`, esfuerzo ≤ high, **sin ningún otro campo**: `block_binding` junto a él es un 400). Sin razonamiento no hay bloques que conservar ni que comprobar. Así ninguna llamada depende de un bloque de razonamiento que no existe. Si el cruce es en la primera llamada, Sonnet responde normal.
5. Cruce de Anthropic a OpenAI: el saneado de D4.4.

   Con `between_tools`, el texto entre herramientas puede volver como bloques de progreso (`thinking`). Si llegan, se conservan y vuelven al mismo modelo como cualquier otro bloque (D4.1).
6. Un rechazo (`content_filter`) es un fallo: se descarta el texto parcial, no se reintenta en el mismo modelo y pasa a la reserva.
7. Cada salto deja `llm.respond_fell_back` con el agente, el modelo elegido, el que respondió y el motivo.

**Razón.** Una reserva del mismo proveedor no protege de lo que de verdad pasa: cuota, saldo o caída de un proveedor. Sonnet 5.5 cuesta lo mismo que Terra (D1) y es la de Anthropic que puede apagar el razonamiento, cosa que Opus no puede. Terra, a la inversa, es la reserva más barata de OpenAI que sostiene un turno de recepción.

**Descartado.**
- *Aplanar el historial ajeno a texto al cruzar*: es robusto frente a las reglas del proveedor, pero el modelo pierde la forma de lo que ya hizo y podría repetir una herramienta con efectos. Queda como plan B si la batería real tumba el punto 4.
- *Opus como reserva*: no deja apagar el razonamiento.

**El cruce a mitad de turno sin herramientas previas** (OpenAI → Sonnet en la primera llamada) no tiene riesgo: no hay historial de herramientas.

## D6. El router sigue apagado

**Decisión.** No se tocan `model_policy`, el router de la 047 ni `409 model_policy_managed`.

**Razón.** El filtro duro (`router_catalog.hard_reason`) exige retención cero; ningún modelo de prod la tenía en la auditoría del 2026-11-11, y ninguna migración lo ha cambiado. Un agente fijado acabaría en `no_model`.

## D7. El plazo de cada llamada

**Decisión.** El plazo deja de ser 30 s fijos (`LiteLLMProvider.timeout_s`) y lo fija el perfil: GPT-5.6, 30 s (como hoy); Haiku 5.5, 45 s; Sonnet 5.5, 60 s; Opus 5.5, 90 s. La batería real mide el p95 y se ajusta.

**Razón.** Con 30 s, un Opus que razona caería a la reserva sin haber fallado.

## D8. Lo que se arregla de paso

1. **El cierre del turno con GPT-5.6** (`tool_choice: "none"`): con el mapa local fijo (D13) falla en el proceso. Hoy en prod no hay ni un fallo así en 60 días: o ningún turno llegó al cierre, o el mapa que descarga prod conoce GPT-5.6. Como D13 fija el mapa, el arreglo (mandarlo en `extra_body`) entra **en el mismo cambio**, o fijar el mapa lo rompería.
2. **El turno informa del modelo global**: `response_model` vale `llm.respond_model` aunque responda la asignación. El checkpoint, `TurnOutcome.model` y el juez de las pruebas (`avoid_model`) heredan el error.
3. **La reescritura del corrector usa siempre el global**: `_ask_agent_to_rewrite` llama a `respond` sin la cadena del agente.
4. **Los errores de parámetro parecen caídas de red** (D3).

## D9. La batería de compatibilidad

1. **En el cable, en CI** (`apps/worker/tests/unit/test_respond_profiles_on_the_wire.py`, patrón de `test_classifier_reaches_the_provider.py`, mapa local fijo): por cada perfil, el cuerpo exacto con herramientas, el cierre, los bloques en la segunda llamada, que nada de lo enviado cambie entre llamadas (D4.2), el saneado, el rechazo y la permanencia en la reserva, y el cruce con razonamiento apagado (D5.4). Sin coste y sin red.
2. **Contra los proveedores reales, en staging** (`apps/worker/scripts/respond_compat.py`, a mano, < US$ 1 la pasada completa), con estos escenarios por modelo:
   - respuesta sin herramientas;
   - cadena de tres herramientas;
   - imagen;
   - cambio de modelo entre turnos;
   - caída a la reserva a mitad de turno, en las dos direcciones;
   - cruce de OpenAI a Sonnet 5.5 tras herramientas;
   - freno de reservas con reintento;
   - turno largo hasta el cierre.

   Con `prefix_mismatch_behavior` en `"error"` para que cualquier edición sea un fallo visible. Mide el p95 y el factor de gasto de cada modelo frente a Sol (razonamiento y tokenizador), que alimenta la estimación del selector (D14).

**Regla.** Un modelo solo entra en el registro con su nivel 1 en verde. Solo se habilita para responder en un entorno (D11) con una pasada del nivel 2 en verde anotada.

## D10. Lo que un modelo no puede ejecutar

Las Skills de Anthropic (`container` + `code_execution`) y el conector MCP de Anthropic solo funcionan con un modelo de Anthropic.
- El selector no ofrece los de OpenAI a un agente que las usa: no hay opción apagada, la ausencia se diseña (Principio V).
- Si ya tenía uno elegido, `resolve()` pasa al siguiente origen que pueda y Avanzado lo avisa.
- La reserva de un agente así tiene que ser de Anthropic.

## D11. La puerta de la oferta, por entorno (decisión de Luis)

**Decisión.** Que un modelo se pueda elegir para responder es un **dato de cada entorno**, no del código ni de una migración:
- `model_profiles` gana `respond_enabled_at`, `respond_enabled_by` y `respond_enabled_note` (la pasada de la batería en la que se apoya).
- La 0238 da de alta Opus y Sonnet 5.5 como ejecutables (`status 'active'`) y pone `offer_label` a los tres de Anthropic, pero **no** los habilita.
- Una migración marca habilitados Sol, Terra y Luna, que ya se ofrecen.
- Dos conjuntos distintos, y no se mezclan:
  - **ofrecible** (`offer_label` ∩ activo ∩ con perfil): lo que puede entrar en la lista de un partner. `PUT /admin/partners/{id}/models` valida contra este conjunto; hoy valida contra la oferta, y con Claude sembrado sin habilitar rechazaría guardar la lista;
  - **ofrecido** (ofrecible ∩ habilitado en el entorno): lo que se puede elegir para responder.
- La oferta de un partner es: ofrecido ∩ su lista. La lista incluye los seis para todos (decisión de Luis).
- El panel (Modelos) gana «Habilitar para responder» y «Deshabilitar». Habilitar exige perfil de llamada y la nota de la pasada. Deshabilitar reconcilia como una lista más corta (requisito 8.2).
- La reserva de la otra familia (D5) solo se usa si está habilitada.

**Razón.** `deploy-prod` aplica las migraciones solo, y el panel no edita `offer_label`. Si la 0238 ofreciera Claude, prod lo tendría antes de la batería real, contra la decisión de Luis.

**Descartado.** Una bandera de configuración por entorno (variable de ECS): no se ve en el panel, no deja rastro de quién y por qué, y prod y staging divergen sin que nadie lo vea.

## D12. Una sola fuente para la forma de la petición

**Decisión.** El registro en código (`apps/api/src/nexus_api/core/respond_profiles.py`, junto a `resolve()`: el worker depende de `nexus-api` y no al revés) es la única fuente de **cómo se llama** a un modelo: parámetros, razonamiento, `max_tokens`, plazo, reserva y lo que nunca se manda.
- La base (`model_profiles`) guarda lo comercial y de operación: precio, estado, oferta, habilitación y residencia.
- `apply_capabilities`, el camino del router, que hoy no corre, toma el razonamiento del perfil para los modelos que lo tienen.
- **Añadido el 2026-11-20 (T052):** lo que solo lleva el turno de respuesta (el `thinking` adaptativo y el `cache_control` de la conversación de Claude 5.5) va en `turn_request`, no en `request`: `apply_capabilities` aplica `request` a cualquier tarea enrutada y le pisaría el `thinking: disabled` a un `classify` enrutado a Haiku 5.5. El turno lo aplica por salto en `llm.respond_hop_extra`.
- Un guardián `test_respond_profiles_cover_the_catalog` falla si un modelo con `offer_label`, uno que sea reserva o uno elegible por un agente no tiene perfil, y si las `capabilities` de la base contradicen al perfil (`reasoning_control`, `context_management`).
- Un modelo **sin perfil** que ya responde hoy por una asignación de cliente (Sonnet 4.6, Haiku 4.5) sigue con el comportamiento de hoy, byte a byte (CE-005), y no se ofrece.

**Razón.** Cómo se llama a un modelo depende de la versión de LiteLLM y de la API del proveedor, que cambian con un despliegue, no con un dato. Dos fuentes divergen en silencio.

## D13. LiteLLM igual en todas partes

**Datos.**
- Ningún servicio de AWS fija `LITELLM_LOCAL_MODEL_COST_MAP` (task definition `nexus-prod-runner:10` sin la variable; tampoco los Dockerfile de la API y el worker). LiteLLM descarga el mapa de modelos de GitHub al arrancar, así que su conducta (qué parámetros acepta) puede cambiar sin desplegar. En local, `docker-compose.yml` sí lo fija: local y prod no se comportan igual.
- El build de prod del 2026-11-18 (`deploy-prod`, run 44396343198) instaló **LiteLLM 1.83.0 en la imagen de la API** (que instala desde `apps/api/uv.lock` y lleva también el paquete del worker: ahí corren el Playground y lo que la API ejecute) y **1.83.14 en la del worker** (`apps/worker/uv.lock`), la que responde los turnos del canal. La sonda de D3 usó 1.83.14, la del worker; lo ampliado en D4.3 se comprobó con las dos.
- Las imágenes se construyen desde el lock desde el 2026-10-22.

**Decisión.**
1. `LITELLM_LOCAL_MODEL_COST_MAP=True` en el entorno de todas las tareas de ECS (Terraform de staging y de prod) y, por si falta, `os.environ.setdefault` antes del primer `import litellm` en la API y en el worker.
2. La misma versión exacta de LiteLLM en los dos locks.
3. Una prueba que falla si las dos versiones difieren.

**Razón.** La batería en el cable solo vale si prod corre con el mismo mapa y la misma versión. Es la lección de la memoria del 2026-11-05: un sondeo con el mapa descargado dio por bueno lo que con el local falla.

**Medido el 2026-11-20 (implementación), cambia el punto 1.** El mapa local que trae LiteLLM 1.83.14 **no conoce** Sol, Terra, Luna ni los tres Claude 5.5, y con él LiteLLM rechaza antes de salir **cualquier** `tool_choice` hacia GPT-5.6 (también `auto`), y `thinking` y `reasoning_effort` hacia Haiku 5.5. El mapa remoto que prod descarga hoy sí los conoce. Fijar el mapa local a secas habría dejado sin herramientas a todos los agentes con GPT-5.6. Con las entradas de esos seis modelos registradas encima (`litellm.register_model`), la misma matriz de parámetros pasa entera salvo `thinking` hacia OpenAI, que el código ya quita (`_drop_openai_unsupported`).

**Decisión revisada.**
1. Mapa local fijo **más nuestras entradas**: `nexus_api/core/litellm_models.json` guarda la entrada del mapa de LiteLLM de cada modelo del catálogo que el mapa local no conoce, copiada del mapa publicado con su fecha y su fuente. `nexus_api/core/litellm_map.py` es la única puerta a LiteLLM: fija `LITELLM_LOCAL_MODEL_COST_MAP=True` (`setdefault`) antes del primer import y registra esas entradas una vez por proceso. Nadie importa `litellm` por su cuenta (lo vigila un barrido AST).
2. La misma versión exacta en los dos locks (1.83.14, la del worker).
3. Pruebas: los dos locks coinciden; al importar el transporte la variable está fijada y las entradas registradas; todo modelo de `default_models()` y del catálogo que el mapa local no conozca tiene entrada.
4. Actualizar las entradas es un cambio de código con su prueba en el cable, no algo que pase al arrancar.

**Orden y alcance.** Fijar el mapa cambia la conducta de **todos** los usos de LiteLLM, no solo la respuesta: clasificar, el freno de reservas, el corrector, extraer, simular, el copiloto (que manda `thinking` como kwarg), la visión, la transcripción, la mejora de prompts, el constructor y las evaluaciones (`platform_models.default_models()`). Cada uso necesita su prueba en el cable con el mapa local y la versión del lock, y el arreglo de lo que falle, **en el mismo despliegue** que el mapa fijo (T009). Nunca antes.

## D14. Lo que se cobra y lo que se estima (decisión de Luis: se cobra todo)

**Hoy (supuesto, a fijar en el cable con T044).** El colector mide `prompt_tokens` (que con Anthropic, suponemos, incluye lo leído y lo escrito en caché), `cache_read_input_tokens` y `cache_creation_input_tokens`. La venta cobra la entrada como «prompt − lectura», así que lo escrito va a 1× de entrada, y `llm.cache_write` lleva `billable_qty = 0` y ningún peso (spec 007, `pricing_policy.LANES`). El informe de consumo del 2026-11-19 calculó la entrada no cacheada como «prompt − lectura − escritura» y cuadró con `cost_usd` de producción, pero casi todo era Sol, sin escritura, así que no lo prueba. Si `prompt_tokens` no incluyera lo escrito, la fórmula nueva restaría dos veces: T044 lo fija antes de tocar nada. Anthropic cobra lo escrito a 1,25× de la entrada (5 min). El recargo ×5 de Haiku 5.5 por encima de 100.000 tokens ya está en `model_prices.surcharge` (migración 0221), pero la venta no lo aplica.

**Medido en el cable (T044, 2026-11-20).** Servidor de eco, la puerta `litellm_map` y `LiteLLMProvider` real, en respuesta entera y en streaming (`apps/worker/tests/unit/test_cache_write_on_the_wire.py`). Respuesta del proveedor: 100 frescos, 5.000 leídos, 3.000 escritos y 20 de salida.
- **Anthropic**: `usage` de Anthropic `{input_tokens: 100, cache_read_input_tokens: 5000, cache_creation_input_tokens: 3000}` → LiteLLM `prompt_tokens: 8100` (= 100 + 5.000 + 3.000), `cache_read_input_tokens: 5000`, `cache_creation_input_tokens: 3000`. `prompt_tokens` **sí** suma las dos cachés: «prompt − lectura − escritura» deja los 100 frescos y no resta nada dos veces. La fórmula no cambia.
- **GPT-5.6**: `usage` de OpenAI `{prompt_tokens: 9000, prompt_tokens_details: {cached_tokens: 5000, cache_write_tokens: 3000}}` → LiteLLM lo deja **tal cual** (`prompt_tokens: 9000`, `prompt_tokens_details.cache_write_tokens: 3000`) y no rellena `cache_creation_input_tokens`. El colector solo leía `cache_creation_input_tokens`: por eso Sol salía con escritura 0. Arreglado en `collector.usage_fields` (no en `runtime/llm.py`): si no viene la clave de Anthropic, toma `prompt_tokens_details.cache_write_tokens`; con las dos, solo cuenta la de Anthropic.
- **Versiones**: el test corre con 1.83.14, la del lock. 1.83.0 se comprobó aparte, en un entorno efímero (`uv run --no-project --with litellm==1.83.0`, con el mapa local y nuestras entradas): las mismas cifras, en las dos formas y en streaming. 1.83.0 solo añade `prompt_tokens_details.cache_write_tokens: null` en la respuesta de Anthropic, que el colector no lee porque ya viene `cache_creation_input_tokens`.
- **Lo que el cable no prueba**: que OpenAI cuente lo escrito dentro de `prompt_tokens` en una respuesta real. El eco lo manda así porque así lo dice la referencia de Chat Completions; si no fuera así, la entrada de GPT-5.6 se cobraría por debajo (la resta tiene suelo 0). Lo zanja la primera llamada real con escritura en staging.

**Decisión** (Luis: el modelo solo cambia cuando el partner lo elige, así que paga lo que cuesta):
1. Un cuarto carril con peso, `cache_write`: peso = tarifa de escritura × multiplicador ÷ 10, como los otros tres (0120). La entrada pasa a cobrarse como «prompt − lectura − escritura», y la escritura con su peso. El margen vuelve a ser el multiplicador en los cuatro carriles: la propiedad que la spec 007 quería para los tres.
2. Los modelos sin tarifa de escritura tienen peso 0 en ese carril y no cambian. **GPT-5.6 sí la tiene**: OpenAI la cobra a 1,25× la entrada (Sol 5,00, Terra 2,50, Luna 0,25), y lleva su peso como los demás (Sol 1,10, Terra 0,55, Luna 0,055).
3. Los tramos: una llamada que pase el umbral de `model_prices.surcharge` se cobra con los pesos multiplicados por el factor del tramo.
4. El peso nuevo sigue las reglas de la 059 (editable en el panel, recalculado con el multiplicador, obligatorio para cobrar) y entra también en el camino del copiloto (`console/companion.py`, que mide aparte).
5. Va a prod **antes** de habilitar ningún Claude: sin él, el primer cliente en Claude se cobraría por debajo.

**Efecto que hay que saber:** sube algo el precio de quien ya usa Anthropic (asignaciones a Sonnet 4.6 y la clasificación con Haiku 5.5 de cada turno, que son céntimos) y, al desplegar, el de todos los agentes que responden con GPT-5.6, alrededor de un 21 % con el perfil de Jemma (Sol, de 0,102 a 0,124 por respuesta; Terra, de 0,052 a 0,063). Sin aviso a los partners: lo confirmó Luis el 2026-11-20, también para esta subida.

**Estimación del selector** (Luis, 2026-11-19: la caché cuenta, aunque sea la teórica de la documentación de cada proveedor). De los últimos 7 días del agente salen, por respuesta: el contexto, la parte que se leyó de caché, la salida y la clasificación. Con eso, cada modelo se calcula con las reglas de su proveedor:

1. **OpenAI, GPT-5.6** (caché automática a partir de 1.024 tokens, 30 minutos de vida por defecto): lo leído a 0,1× la entrada; lo escrito, a 1,25× la entrada, que es lo que la documentación dice que cobra desde GPT-5.6, también en Chat Completions (`usage.prompt_tokens_details.cache_write_tokens`). Se repercute (decisión de Luis, abajo).
2. **Anthropic** (un token solo se lee si antes se escribió; escribir cuesta 1,25× la entrada con 5 minutos, leer 0,05× en Opus y Sonnet 5.5 y 0,1× en Haiku 5.5, mínimo 512 tokens): lo leído a la tarifa de lectura y todo lo demás a la de escritura, porque con la caché que recomienda Anthropic para agentes (abajo) cada token nuevo se escribe una vez.
3. La fracción leída es la medida en el agente. Si se midió con OpenAI (30 minutos de vida), en Claude (5 minutos) se leerá algo menos: la estimación de Claude es optimista hasta que la batería lo mida.
4. Los tramos de precio (Haiku 5.5, ×5 por encima de 100.000 tokens) se aplican por llamada.
5. Los pesos de venta de los cuatro carriles × el multiplicador, y × el `estimate_factor` de cada modelo, que mide la batería (D9) y recoge lo que la documentación no dice: cuántos tokens cuenta cada tokenizador para el mismo texto y cuánto razona cada modelo.
6. Sin consumo, un turno típico con la misma regla. Se enseña como estimación.

**Hallazgo del 2026-11-19, sin comprobar contra la factura.** Según la documentación de OpenAI (guía de prompt caching, página de GPT-5.6 Luna y referencia de Chat Completions), desde GPT-5.6 lo escrito en caché se cobra a 1,25× la entrada, no a 1×. El medidor registra `cw = 0` en todas las llamadas de Sol, así que, si es así, el coste que guardamos de GPT-5.6 se queda corto en lo no leído y el margen real de Jemma con Sol sería de 1,8× en lugar de 2,2× (por encima del suelo de 1,5×). Lo que lo zanja: lo que facturó OpenAI el 17 y el 18 de noviembre frente a la suma de `cost_usd` de esos días (Luis). T044 hace que el medidor registre esa escritura; sin ello, ni sabemos lo que cuesta ni el peso nuevo cobra nada.

**Decisión de Luis (2026-11-19): la escritura de GPT-5.6 se cobra al partner**, como la de Anthropic. Sube a todos los agentes que ya responden con Sol, Terra o Luna sin que nadie elija nada (en Jemma, de 0,102 a 0,124 por respuesta con Sol; de 0,052 a 0,063 con Terra), y devuelve el margen de esos modelos a 2,2×, que sin cobrarla sería 1,8×.

**Caché hacia Anthropic** (lo que la estimación supone): una marca `cache_control` en el último bloque del `system` y la caché de la conversación en la última posición de cada llamada, con 5 minutos, que es la combinación que la documentación de Anthropic recomienda para bucles de agente. Hoy el transporte solo marca el `system`: la historia y los resultados de herramientas se reenvían sin caché en cada llamada del turno. T050 lo fija en el cable y la batería real lo mide (`cache_read_input_tokens` en la segunda llamada de un turno).

**Fijado en el cable el 2026-11-20 (T050):** LiteLLM 1.83.14 deja pasar el `cache_control` de arriba (la caché automática de la conversación), así que el perfil de Claude 5.5 lo manda y ningún mensaje lleva marca: lo anterior queda igual byte a byte. Si Anthropic lo trata como edición en modo estricto, lo dice `cache_marker_is_not_an_edit` (T055).

## D15. Un solo sitio: el modelo del cliente pasa a sus agentes (decisión de Luis)

**Decisión.**
1. **Comprobación previa** (script de solo lectura, staging; prod con el sí de Luis): clientes con asignación `respond`, su modelo, sus agentes no archivados, y cuáles tienen `fallback_chain` o `max_cost_per_turn_usd`, que dejan de usarse. Se revisa antes del despliegue.
2. **Migración que no falla**: por cada asignación `respond`, cada agente no archivado del cliente sin elección propia recibe ese modelo. `set_by` sale de la auditoría (`console.model.update` → partner; si no consta, Auphere). Una línea de auditoría por cliente (`model.respond_binding.migrated`, con lo de antes y los agentes) permite deshacerlo.
3. Desde ese despliegue, la asignación `respond` no se lee para decidir un modelo:
   - `resolve()` ya no la recibe;
   - `PUT /console/clients/{ref}/model` responde `410 client_model_retired`, y su `GET` desaparece;
   - `PUT /admin/tenants/{id}/model-bindings/respond`, `422 respond_is_per_agent`;
   - los demás roles no cambian.
4. Las filas se conservan sin uso una versión y las borra la migración de la versión siguiente.
5. Un modelo heredado sin perfil (Sonnet 4.6, Haiku 4.5) sigue con el comportamiento de hoy (D12). Se ve con su precio y la línea «ya no se ofrece» (`outside_offer: retired`), y el partner solo puede cambiarlo a uno de su oferta.
6. **Barrido**: además de los sitios de T004, `services/model_usage.py`, `services/model_lifecycle.py`, `core/partner_allowlist.py` (`reconcile_bindings` deja de tocar `respond`), `api/admin/budget_policies.py`, `api/console/companion.py`, `worker/metering/pricing.py` (`cheapest_model`) y el bundle (`load_bindings` deja de dar `respond`).

**Razón.** Tres sitios para decidir el modelo y nadie sabe cuál manda. La migración no falla por datos, porque una migración que aborta según lo que haya en prod tumba `deploy-prod`; lo que se pierde (reservas propias, topes) se ve antes, en la comprobación previa.

**Descartado.** Dejar la asignación de cliente como valor por defecto del cliente: era la propuesta inicial, y Luis prefirió un solo sitio.

## D16. El modelo por defecto de Auphere: Haiku 5.5, por etapas (decisión de Luis)

**Decisión.**
1. El modelo por defecto de Auphere deja de ser `llm_respond_model` del worker y pasa a ser un ajuste de plataforma por entorno, `platform_settings.agent_respond_default`. Lo lee `resolve()` desde el catálogo cacheado y se invalida con `CATALOG_CHANGED`. `llm_respond_model` sigue moviendo solo lo de la plataforma: el constructor, el Playground QA antiguo (`api/qa.py`) y la reserva del clasificador. El Playground del agente y su batería usan el modelo efectivo del agente (requisito 6.1).
2. Solo admite modelos habilitados para responder (D11). Al desplegar vale el modelo con el que respondían los agentes sin elección: hoy Sol, el valor del código, porque las taskdefs del runner de staging (`:19`) y de prod (`:10`) no fijan `NEXUS_LLM_RESPOND_MODEL` (comprobado el 2026-11-19).
3. Cambiarlo, desde el panel:
   - enseña la lista de agentes afectados (los que no tienen elección propia ni de versión), con cliente y modelo de ahora;
   - pide confirmación y motivo;
   - lo audita;
   - publica la invalidación de esos agentes;
   - devuelve la pasada de pruebas a los agentes afectados (spec 047, requisito 68.14).
4. Las guardas de la 059 lo tratan como en uso: `default_models()` lo publica como `agent_default`.
5. **La ruta a Haiku 5.5 en prod**, por orden:
   1. la batería real pasa en staging (T064);
   2. humo en prod (T065);
   3. el cuarto carril de cobro, en prod;
   4. Haiku se habilita en prod;
   5. Auphere elige Haiku para dos o tres agentes reales de clientes distintos y mira una semana caídas a la reserva, derivaciones a persona y quejas;
   6. Auphere cambia el por defecto.

   Jemma no cambia, porque tiene Terra elegido (D15).

**Razón.** El ajuste de hoy (`llm_respond_model`) mueve también modelos de la plataforma: cambiarlo para abaratar a los agentes cambiaría el constructor y el Playground. Y la batería prueba un agente de laboratorio, no los reales: el paso con pocos agentes reales es lo que dice si Haiku sostiene a los clientes de verdad.

**Riesgo que asume Luis:** Haiku 5.5 es el modelo pequeño de Anthropic, orientado a clasificar y enrutar. Su reserva es Terra, así que un fallo no deja sin respuesta. Una respuesta mediocre sí se ve, y por eso el paso con pocos agentes reales va antes del cambio general.
