# Guía de validación: El modelo de cada agente

**Spec**: [spec.md](spec.md) · **Contratos**: [contracts/api.md](contracts/api.md) · **Datos**: [data-model.md](data-model.md)

## 1. En local, sin coste

```bash
./scripts/verify.sh lint
cd apps/worker && uv run --with lupa pytest tests/unit/test_respond_profiles_on_the_wire.py tests/unit/test_respond_fallback_mid_turn.py tests/unit/test_platform_default_models.py -q
cd apps/api && uv run pytest tests/unit/test_respond_model_resolution.py tests/isolation/test_065_agent_model_scope.py tests/isolation/test_console_scope.py tests/integration/models -q
./scripts/verify.sh js
```

Esperado: todo en verde y ningún `skip`. La batería en el cable comprueba, para cada uno de los seis modelos, el cuerpo que sale, el cierre con `tool_choice: "none"`, los bloques de razonamiento, el saneado al caer a OpenAI, el rechazo y la permanencia en la reserva.

## 2. Al desplegar en staging, nada cambia (CE-005)

1. Antes del despliegue, anotar el modelo efectivo de todos los agentes con `GET /admin/tenants/{id}/agents/models`, cliente a cliente.
2. Desplegar `develop` en staging.
3. Antes de desplegar, correr la comprobación previa (`apps/api/scripts/respond_bindings_report.py`) y revisar qué clientes tienen modelo propio y cuáles pierden reservas propias o tope.
4. Repetir la lectura: los agentes de clientes con modelo propio lo tienen ahora elegido (`choice`, con `set_by` según la auditoría), los demás tienen `choice = null`, y todos tienen el mismo `effective` que antes. El modelo por defecto de Auphere es Sol.

## 3. La batería contra los proveedores reales (staging, < US$ 1)

```bash
cd apps/worker && uv run python scripts/respond_compat.py --env staging --models all
```

Por cada modelo, ocho escenarios: respuesta sin herramientas, cadena de tres herramientas, imagen, cambio de modelo entre turnos, caída a la reserva a mitad de turno en las dos direcciones, cruce de OpenAI a Sonnet 5.5 tras herramientas, freno de reservas con reintento y turno largo hasta el cierre. Esperado: todo en verde, 0 errores de parámetros, el p95 de cada modelo por debajo de su plazo y el coste de cada turno anotado.

Con `prefix_mismatch_behavior = "error"`, cualquier edición del historial a mitad de turno es un fallo visible.

Si pasa, habilitar en staging desde el panel (Modelos → «Habilitar para responder») cada modelo de Anthropic, con la nota de la pasada. En prod, lo mismo tras el paso a `main`.

Anotar aquí el resultado de cada pasada antes de habilitar los modelos de Anthropic:

| Fecha | Commit | Resultado | p95 por modelo | Coste |
|---|---|---|---|---|
| 2026-11-20 | `9c836f31` | **No vale.** Los tres de Claude salieron «en verde», pero ninguno respondió un turno con herramientas: 63 llamadas rechazadas por el nombre con punto (`tools.0.custom.name`) y en todos sus escenarios respondió Terra. GPT-5.6, en rojo en la caída y el cruce a Sonnet por lo mismo. Lo arreglan T099 y T100. | — | US$ 0,45 |
| 2026-11-20 | `9c836f31` + T099 y T100 (sin commit) | Todo en verde salvo Haiku 5.5 en `booking_brake_retry`: la nota del freno en el `system` invalidó su razonamiento (`Invalid signature in thinking block`). Lo arregla T102. | Sol 2,4 s · Terra 1,5 · Luna 1,2 · Opus 3,1 · Sonnet 3,2 · Haiku 1,8 | US$ 0,51 |
| 2026-11-20 | + T102 (sin commit) | `booking_brake_retry`, tres pasadas en los seis: en verde, ningún error de firma. | — | céntimos |
| 2026-11-20 | + T102 (sin commit) | **Los seis en verde**, completa: 0 rechazos por nombre, 0 errores de firma, solo las caídas que provocan los escenarios de caída y cruce. | Sol 2,4 s · Terra 1,5 · Luna 1,6 · Opus 4,5 · Sonnet 3,1 · Haiku 2,0 | US$ 0,51 |

Gasto frente a Sol con los mismos escenarios de turno y el agente de prueba (tokens de las llamadas del propio modelo, salida a 5 veces la entrada): Terra 0,86, Luna 0,87, Opus 1,94, Sonnet 1,84 y Haiku 2,58. En entrada, Claude gasta entre 1,65 y 2 veces más, y en salida entre 2,6 y 4,8, porque el razonamiento cuenta como salida. Con el mismo texto largo (9.000 tokens en Sol) Claude cuenta 1,33 veces más. Desde T103, el registro tiene `estimate_factor` **provisionales**: Opus 1,9, Sonnet 1,8 y Haiku 2,6; los GPT-5.6 siguen en 1,0. No son un techo: la medida usó tokens brutos y en esa pasada los prompts de Sol no entraron en caché. Antes de habilitar Claude en prod hay que repetirla con un agente de tamaño real, en caché en las dos familias, carril a carril.

GPT-5.6 informa de lo escrito en caché (`prompt_tokens_details.cache_write_tokens`: 9.028 de un prompt de 9.031) y el colector lo apunta (`cache_creation_input_tokens`). El carril de escritura de GPT-5.6 se mide con el proveedor real.

## 4. El selector en la consola (staging)

1. En un cliente de prueba con dos agentes, abrir Agente › Avanzado del primero: se ve el modelo efectivo con su origen y seis opciones con precio estimado.
2. Elegir Luna y guardar: aparece el toast y el siguiente mensaje por el Playground responde Luna (el turno lo dice).
3. El segundo agente sigue con su modelo.
4. Con un rol de solo lectura, se ve el modelo y no se puede cambiar.
5. Pasar la batería del primer agente: cada prueba dice que respondió Luna.

## 5. Panel, lista del partner y retirada

1. Desde el panel, elegir Opus 5.5 para un agente de un partner sin Opus en su lista, con motivo: la consola lo enseña con su precio y la línea «Auphere eligió Claude Opus 5.5 para este agente…».
2. Quitar Luna de la lista del partner: los agentes con Luna elegida por el partner pasan al modelo por defecto y llega un aviso `agent.model_reset` por agente con el modelo nuevo.
3. Intentar retirar Opus 5.5 con un agente que lo tiene elegido: `409 model_in_use` con la lista de agentes.

## 6. Reserva de la otra familia (CE-007)

En staging, con Sonnet 5.5 habilitado, forzar el fallo del proveedor del modelo elegido (clave inválida para OpenAI en una tarea de prueba, o el escenario de la batería). Esperado: los turnos de un agente en Sol responden con Sonnet 5.5 y dejan `llm.respond_fell_back`. Repetir a la inversa con un agente en Opus 5.5 y Terra.

## 7. Cobro (CE-004)

Un día de turnos en staging con un agente en Luna y otro en Opus 5.5. Conciliar lo descontado de la bolsa con `usage_records` por llamada y modelo, al precio de venta de cada uno. Diferencia esperada: 0.

## 8. Modelo por defecto de Auphere: Haiku 5.5 por etapas (CE-008)

En staging, con Haiku 5.5 habilitado:

1. En el panel (Plataforma › Modelos), elegir Haiku 5.5 como modelo por defecto. Esperado: la lista de agentes afectados, sin los que tienen elección propia; nada cambia hasta confirmar.
2. Confirmar con motivo. Los agentes listados responden con Haiku 5.5 desde el turno siguiente y su pasada de pruebas vuelve a estar pagada por Auphere.
3. Volver a Sol y comprobar que los mismos agentes vuelven.

En prod, solo tras el paso a `main` y en el orden de T079. Anotar cada paso:

| Fecha | Paso | Agentes | Resultado |
|---|---|---|---|
| | | | |
