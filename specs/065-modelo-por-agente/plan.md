# Implementation Plan: El modelo de cada agente

**Branch**: `065-modelo-por-agente` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/065-modelo-por-agente/spec.md`

## Summary

Seis piezas, en este orden de dependencia:

1. **LiteLLM determinista** (research.md §D13): mapa de modelos local y fijo en todos los servicios, y la misma versión en la API y en el worker. Sin esto, nada de lo probado en CI vale en prod.
2. **Un perfil por modelo** (§D12): `nexus_api/core/respond_profiles.py` es la única fuente de cómo se llama a cada uno de los seis (parámetros, razonamiento, `max_tokens`, plazo, reserva, lo que nunca se manda). El transporte aplica el perfil del modelo de **cada salto**. Un modelo sin perfil que ya responde hoy por una asignación sigue como hoy.
3. **El turno entre familias** (§D3–D5):
   - los bloques de razonamiento vuelven al mismo modelo;
   - nada de lo enviado cambia entre llamadas de un turno con razonamiento;
   - la reserva es de la otra familia y se queda el resto del turno;
   - el cruce de OpenAI a Anthropic tras herramientas sigue sin razonamiento;
   - un rechazo es un fallo;
   - el turno informa del modelo que respondió.
4. **La elección por agente, en un solo sitio** (§D2, §D15, §D16):
   - tres columnas en `agents`;
   - una sola resolución (`core/respond_model.py`: agente → versión → por defecto de Auphere) para el turno, las guardas de la 059, la consola y el panel, con un barrido que lo vigila;
   - la asignación de cada cliente pasa a sus agentes y se retira;
   - el modelo por defecto de Auphere pasa a ser un ajuste de plataforma por entorno, que arranca en Sol y Luis quiere llevar a Haiku 5.5 por etapas.
5. **Se cobra todo** (§D14): un cuarto carril de peso para la escritura en caché y los tramos de precio, en prod antes de habilitar ningún Claude.
6. **La puerta por entorno** (§D11): `model_profiles.respond_enabled_*`. Auphere habilita un modelo para responder desde el panel, con la pasada de la batería anotada. La oferta, las elecciones y la reserva solo usan modelos habilitados.
7. **Pantallas**:
   - Agente › Avanzado gana el selector;
   - el panel gana el modelo por agente, «Habilitar para responder» y el modelo por defecto con su lista de afectados;
   - el copiloto propone por agente.

**Verificación**: la batería en el cable en CI para los seis perfiles, y la batería real en staging antes de habilitar cada modelo de Anthropic en cada entorno.

## Technical Context

**Language/Version**: Python 3.11 (API y worker); TypeScript con Next.js 16 y React 19 (consola `apps/console`, panel `apps/admin`).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, LiteLLM (ya en los locks; se iguala la versión de la API y del worker), `@nexus/ui`. Sin dependencias nuevas.

**Storage**: PostgreSQL. Tres columnas en `agents` (RLS existente), tres en `model_profiles` (plataforma), y filas nuevas en `model_profiles`, `model_prices` y `partner_model_allowlist`.

**Testing**:
- pytest: unit, integration e isolation (API); unit (worker).
- Vitest con Testing Library (consola y panel).
- Batería en el cable: pytest con servidor de eco y mapa local.
- Batería real: script a mano en staging.
- Playwright en staging.

**Target Platform**: AWS ECS (staging y prod), consola en Vercel, como hoy. Terraform solo en staging hasta el paso a `main`.

**Project Type**: Web service con dos frontales (consola de partners y panel de operador).

**Performance Goals**:
- Ninguna consulta nueva en el camino caliente del turno: la elección y la habilitación viajan en el `AgentBundle` y en el catálogo, que ya se cachean.
- La estimación de precio es una consulta agregada sobre 7 días del agente, solo al abrir Avanzado.

**Constraints**:
- **CE-005**: al desplegar, ningún agente cambia de modelo. Lo único que cambia sin que Auphere lo habilite es el arreglo del cierre con GPT-5.6, que entra junto al mapa fijo (§D8.1, §D13).
- La reserva de la otra familia solo se activa en un entorno cuando su modelo está habilitado allí.
- El router y `model_policy` no se tocan (§D6).

**Scale/Scope**: unos 10 partners y unas decenas de agentes; seis modelos.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto; whitelist exhaustiva | ☑ | La elección vive en `agents` (RLS FORCE). La consola resuelve el agente con `agent_in_path`, el panel con `scoped_session_from_path` y el turno en `bundle_of` con la sesión acotada. El modelo no cambia la lista blanca. Un barrido vigila que nadie resuelva el modelo por su cuenta (Principio I: «barre»). Tests en `tests/isolation/`. |
| II | Corte por superficie | ☑ | Superficie `0`: consola, panel y su API, que ya existen. |
| III | Lo leído es dato | ☑ | La nota de cierre deja de mezclarse con nada: con Anthropic, el cierre es solo `tool_choice: "none"`; con OpenAI sigue como `{"role":"system"}`. No se mete ninguna instrucción en un mensaje con contenido leído (§D4). |
| IV | Acción consecuente con confirmación; auditoría nombra a la persona | ☑ | Cambiar de modelo no está en la lista cerrada de acciones con aprobación. Se audita con la persona, y con motivo en el panel. Habilitar un modelo exige la nota de la batería. La propuesta del copiloto pide confirmación como hoy. |
| V | Estados honestos; la ausencia se diseña | ☑ | El selector tiene cargando, vacío, error, parcial (sin estimación) e ideal. Un modelo que el agente no puede usar o que no está habilitado no aparece. Si el modelo elegido dejó de poder responder, se dice (`notice`). |
| VI | Por API, nunca navegando la consola | ☑ | El copiloto aplica por `PUT …/agents/{id}/model`. |
| VII | Test primero; nada de `skip` | ☑ | Cada criterio EARS nace como test en rojo (tasks.md). La batería en el cable falla si falta un perfil. |
| VIII | Licencias | ☑ | Sin dependencias nuevas; LiteLLM ya está y solo se iguala su versión. |
| IX | KB dueña del porqué | ☑ | `[[decisions/2026-11-19-modelo-por-agente]]`. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | **Garantía 1 (RLS)**: la elección es dato del cliente en `agents`. Un partner no lee ni cambia agentes de otro, y el turno la lee con la GUC del cliente. **Garantía 7**, rozada: los modelos nuevos y la reserva cruzada pasan por `_raw_complete`, que ya rechaza los lotes entre clientes. | T010–T013 (tasks.md) |
| **Licencias** | Ninguna dependencia nueva. | — |
| **Medidor** | Modelo: las llamadas de conversación del agente, también las de la reserva, con el modelo que respondió y sus pesos × multiplicador. **Cambia lo que se cobra**: un cuarto carril con peso para la escritura en caché y los tramos de precio de Haiku (§D14). El partner lo ve en su bolsa, como hoy, y en la estimación del selector. Opus 5.5 y Sonnet 5.5 entran con pesos. | T003, T040, T043–T047 |

**Complejidad que hay que justificar:** ver Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/065-modelo-por-agente/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/api.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
apps/api/
├── pyproject.toml / uv.lock                                  # LiteLLM igual que el worker
├── alembic/versions/0237_agent_respond_model.py             # columnas en agents
├── alembic/versions/0238_respond_offer_claude_55.py          # respond_enabled_*, Opus/Sonnet 5.5, offer_label, lista y trigger
├── alembic/versions/0239_cache_write_lane_default.py     # quota_weight_cache_write; platform_settings.agent_respond_default
├── alembic/versions/0240_respond_bindings_to_agents.py       # la asignación de cada cliente pasa a sus agentes
├── scripts/respond_bindings_report.py                       # comprobación previa, solo lectura
├── src/nexus_api/__init__.py (o el arranque)                 # LITELLM_LOCAL_MODEL_COST_MAP antes de importar litellm
├── src/nexus_api/db/models/{agent,model_profile}.py
├── src/nexus_api/core/respond_model.py                       # resolve(): la única resolución
├── src/nexus_api/core/respond_profiles.py                    # el perfil de cada modelo (lo lee también el worker)
├── src/nexus_api/core/respond_catalog.py                     # oferta = label ∩ activo ∩ habilitado; BOOT_*
├── src/nexus_api/core/partner_allowlist.py                   # reconcilia también las elecciones de agentes
├── src/nexus_api/services/{model_lifecycle,model_usage}.py   # por resolve(); reservas como uso
├── src/nexus_api/services/agent_model.py                     # elección, oferta por agente, estimación
├── src/nexus_api/api/console/{agent_model,models}.py
├── src/nexus_api/metering/pricing_policy.py                  # cuarto carril y tramos
├── src/nexus_api/api/admin/{agent_models,models_catalog,partner_models,model_bindings,platform_settings}.py
├── src/nexus_api/companion/tools/{catalog,proposals,actions}.py
└── tests/{isolation,unit,integration/models}/…
apps/worker/
├── pyproject.toml / uv.lock
├── src/nexus_worker/__init__.py (o el arranque)              # LITELLM_LOCAL_MODEL_COST_MAP
├── src/nexus_worker/runtime/llm.py                           # perfil por salto, bloques, saneado, rechazo, plazo, reserva, permanencia
├── src/nexus_worker/runtime/{agent_loader,pipeline,state}.py
├── src/nexus_worker/platform_models.py                       # reservas de la otra familia en default_models()
├── src/nexus_worker/simulation/{runner,customer}.py
├── scripts/respond_compat.py                                 # batería real (staging)
└── tests/unit/…
apps/console/src/components/builder/{agent-model-select,agent-builder}.tsx, …
apps/admin/src/app/(dashboard)/{tenants/[id]/agent,models}/…
infra/terraform/20-services/…                                 # LITELLM_LOCAL_MODEL_COST_MAP en las taskdefs (staging; prod en el paso a main)
docs/modelos-y-router.md, docs/console.md, docs/agentes.md, docs/admin.md, docs/billing.md
specs/047-la-fabrica-de-agentes/spec.md                       # nota de enmienda en el requisito 64
```

**Structure Decision**: monorepo existente; API y worker en Python, consola y panel en sus apps Next.js.

## Diseño por capas

### 1. LiteLLM determinista (§D13)

- `os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")` en el arranque de la API y del worker, antes del primer `import litellm`, más la variable en las taskdefs.
- Misma versión exacta en los dos locks, y una prueba que compara.
- Va en el **mismo despliegue** que los perfiles y que una prueba en el cable por cada uso de LiteLLM (`default_models()`): fijar el mapa cambia la conducta de todos, y sin el arreglo del cierre rompería GPT-5.6 (§D8.1, §D13).

### 2. El perfil de cada modelo (`nexus_api/core/respond_profiles.py`, §D12)

| Modelo | Con herramientas | Razonamiento | `max_tokens` | Plazo | Reserva |
|---|---|---|---|---|---|
| Sol, Terra, Luna | `extra_body.reasoning_effort = "none"`; `tool_choice` por `extra_body` | apagado | como hoy | 30 s | Sonnet 5.5 |
| Opus 5.5 | `output_config.effort = "low"` (kwarg) | adaptativo, bloques conservados, `drop_block` | 8192 | 90 s | Terra |
| Sonnet 5.5 | `output_config.effort = "low"`; al cruzar tras herramientas de OpenAI, `thinking: {"type":"between_tools"}` | adaptativo, bloques conservados, `drop_block` | 8192 | 60 s | Terra |
| Haiku 5.5 | `output_config.effort = "low"` | adaptativo, bloques conservados, `drop_block` | 8192 | 45 s | Terra |

- `forbidden`: `temperature`, `top_p`, `top_k`, `reasoning_effort` hacia Anthropic; `tool_choice` forzado hacia Opus y Sonnet 5.5; `thinking` y `output_config` hacia OpenAI.
- `thinking` solo con `allowed_openai_params=["thinking"]`; `output_config` como kwarg (§D3).
- `apply_capabilities` (router) toma el razonamiento del perfil cuando lo hay.

### 3. El turno (`llm.py`, `pipeline.py`)

1. `LLMResponse` gana `model`, `fell_back`, `finish_reason` y `reasoning_blocks`.
2. `acomplete_with_tools`:
   - lee `thinking_blocks` (LiteLLM no devuelve `input_transformations`: un descarte por `drop_block` no se ve en prod, y la batería en modo estricto es la garantía);
   - con `content_filter` lanza `ProviderRefused`, sin texto parcial; `_call_with_resilience` no lo reintenta en el mismo modelo.
3. La cadena de cada llamada: modelo efectivo → `reserve` del perfil, si está habilitada; si no, Sol, como hoy.
4. `TurnModelPin`:
   - cuando la reserva responde, el resto del turno sigue con ella;
   - si el cruce fue de OpenAI a Anthropic tras herramientas, el turno sigue con `cross_in_request`.
5. Saneado por destino antes de cada llamada (§D4.4).
6. **Solo se añade** (§D4.2): con un modelo que razona, el cierre del turno no añade `FINAL_ANSWER_NOTE` ni quita herramientas; usa `tool_choice: "none"`. El freno de reservas deja de retirar la nota. Con GPT-5.6, el cierre sigue como hoy, pero sale.
7. `pipeline.py`:
   - resuelve con `resolve()`;
   - guarda los bloques en `_assistant_tool_message`;
   - fija `response_model` y `response_fell_back` con lo que devolvió el transporte;
   - `_ask_agent_to_rewrite` usa la cadena del agente.
8. `llm.attempt_failed` registra la clase original de la excepción.

### 4. Elección, puerta y pantallas

- `resolve()` en `core/respond_model.py`, pura (data-model.md §5).
- La oferta (`respond_catalog`) exige `respond_enabled_at`.
- El modelo por defecto de Auphere es `platform_settings.agent_respond_default` (§D16), en el catálogo cacheado; `llm_respond_model` queda para la plataforma.
- La asignación de cada cliente pasa a sus agentes con `0240` y se retira (§D15).
- `default_models()` publica las reservas de la otra familia como usos, de modo que la 059 no deja retirar una reserva habilitada.
- **Consola, Avanzado**:
  - solo los modelos de la oferta, con «Ahora» en el que responde y sin origen (requisito 2.7);
  - las opciones con nombre, proveedor, línea de su gama y precio estimado;
  - una línea con precio y motivo si el que responde está fuera de la oferta;
  - un botón «Guardar modelo» y el toast «Responde con {modelo} desde el próximo mensaje».

  Una acción principal por fila.
- **Panel**:
  - en `tenants/[id]/agent`, el modelo de cada agente con su origen y un cambio con motivo;
  - en Modelos, «Habilitar para responder» con la nota de la pasada, y «Deshabilitar».

## Complexity Tracking

| Añadido | Por qué hace falta | Por qué no basta lo simple |
|---|---|---|
| Mapa fijo y versión igual de LiteLLM, con prueba por uso | Requisito 4.12; que lo probado en CI sea lo que corre. | Hoy el mapa se descarga al arrancar, y la API de prod lleva 1.83.0 frente al 1.83.14 del worker: la conducta cambia sin desplegar y entre procesos. |
| Puerta por entorno (`respond_enabled_*`) | Requisito 1.3, decisión de Luis. | Las migraciones se aplican solas al desplegar, y el panel no edita `offer_label`. |
| Reserva de la otra familia y cruce sin razonamiento | Requisito 11, decisión de Luis; turnos reales sin respuesta por falta de saldo en OpenAI (octubre). | La reserva del mismo proveedor cae con él. Cruzar con razonamiento activo depende de una regla del proveedor que no se pudo comprobar. |
| Permanencia en la reserva durante el turno | Requisito 4.4. | Volver al primero en cada llamada mezcla historial de dos familias en las dos direcciones. |
| Turno que solo añade, con `drop_block` | Requisitos 4.10 y 4.11. | Las notas y herramientas que hoy se quitan y se ponen rompen los bloques de razonamiento (400 en cuentas nuevas). |
| Barrido AST de la resolución | Principio I. | Cuatro sitios repiten hoy el orden; uno olvidado reabre los agentes mudos de la 059. |
| Migración de las asignaciones de cliente, con comprobación previa | Requisito 12, decisión de Luis. | Dejar la asignación de cliente como un escalón más deja tres sitios donde se decide el modelo. |
| Modelo por defecto como ajuste de plataforma | Requisito 13, decisión de Luis (Haiku 5.5). | `llm_respond_model` mueve también el constructor, el Playground y la reserva del clasificador. |
| Cuarto carril de cobro | Requisito 5.5 a 5.8, decisión de Luis. | Sin él, Claude y GPT-5.6 se cobran por debajo de su coste en lo escrito en caché, y Haiku en su tramo largo. |
| Plazo por modelo | Requisito 4.7. | Con 30 s fijos, Opus cae a la reserva sin haber fallado. |
