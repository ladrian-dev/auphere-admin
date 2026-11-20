---

description: "Tareas de la spec 065: el modelo de cada agente"
---

# Tasks: El modelo de cada agente

**Input**: Design documents from `/specs/065-modelo-por-agente/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), [quickstart.md](quickstart.md)

**Tests**: obligatorios (constitución §VII). Cada tarea de test se escribe y se ve en rojo antes de la tarea de implementación que la sigue.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: rojo antes que implementación. Ningún `skip`.
- **Aislamiento (§I)**: garantía 1 (y la 7, rozada). Sus tests son T010–T013.
- **Licencias (§VIII)**: no entra ninguna dependencia; solo se iguala la versión de LiteLLM.
- **Medidor**: llamadas de conversación, también las de la reserva, con el modelo que respondió y sus pesos, y el cuarto carril de la escritura en caché con los tramos de precio. Lo cubren T003, T040 y T043–T047.
- **Sin commits**: los hace Luis. Al cerrar se entregan los mensajes.
- **Ninguna llamada a un proveedor real fuera de T064**: las pruebas en el cable usan un servidor de eco y el mapa local de LiteLLM.
- **Nada en prod hasta el paso a `main`**, Terraform incluido (memoria del 2026-11-03). Habilitar un modelo en prod es un paso de operación posterior, con la pasada de staging anotada.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: la historia de la spec (US1…US6)

---

## Fase 1: Base compartida (bloquea todo)

- [X] T001 LiteLLM determinista (research.md §D13, decisión revisada el 2026-11-20):
  - `apps/api/src/nexus_api/core/litellm_map.py`, la única puerta a LiteLLM: `setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")` antes del primer import y registro de `core/litellm_models.json` (las entradas de los modelos del catálogo que el mapa local no conoce: Sol, Terra, Luna y los tres Claude 5.5), una vez por proceso. Los siete sitios que importan `litellm` pasan por ella; también se llama en el arranque de la API y del worker;
  - la misma versión exacta de LiteLLM en los dos locks: la API sube de 1.83.0 a 1.83.14 (`uv lock --upgrade-package litellm`);
  - test `apps/worker/tests/unit/test_litellm_is_deterministic.py`: las dos versiones del lock coinciden; al importar el transporte la variable está fijada y las entradas registradas; todo modelo de `default_models()` y de las migraciones que el mapa local no conozca tiene entrada; barrido AST: ningún módulo importa `litellm` salvo `litellm_map.py` y la prueba de humo manual.

  _Requisitos: 4.12_
- [X] T002 Migración `apps/api/alembic/versions/0237_agent_respond_model.py` (id ≤ 32 caracteres, `down_revision = "0236_context_cut_and_autoclose"`):
  - columnas en `agents`: `respond_model_profile_id uuid NULL REFERENCES model_profiles(id) ON DELETE RESTRICT`, `respond_model_set_by text NULL CHECK (respond_model_set_by IN ('partner','operator'))`, `respond_model_set_at timestamptz NULL`;
  - `CHECK ((respond_model_profile_id IS NULL) = (respond_model_set_by IS NULL))`;
  - las acciones de auditoría nuevas (`console.agent.model.update`, `admin.agent.model.update`, `admin.model.respond_enable`, `admin.model.respond_disable`) donde viva su vocabulario;
  - `downgrade` que lo deshace.

  Columnas en `Agent` (`apps/api/src/nexus_api/db/models/agent.py`). Sin política RLS nueva: la de `agents` (0152) las cubre.

  _Requisitos: 2.1, 2.6, 10.1_
- [X] T003 Migración `apps/api/alembic/versions/0238_respond_offer_claude_55.py`:
  - columnas `respond_enabled_at timestamptz NULL`, `respond_enabled_by text NULL` y `respond_enabled_note text NULL` en `model_profiles`, con `CHECK ((respond_enabled_at IS NULL) = (respond_enabled_by IS NULL))`;
  - Sol, Terra y Luna habilitados (`respond_enabled_by = 'migration:0238'`, nota «ofrecidos antes de la spec 065»);
  - filas `anthropic/claude-opus-5-5` y `anthropic/claude-sonnet-5-5`, copiadas de `anthropic/claude-haiku-5-5` (patrón de la 0221), con `max_context` 1.000.000, `status 'active'`, tarifas y pesos de research.md §D1 y sus `model_prices` con `source_url`. **Sin habilitar.**
  - `offer_label` «Opus 5.5», «Sonnet 5.5» y «Haiku 5.5»;
  - los tres de Anthropic en `partner_model_allowlist` de cada partner (`ON CONFLICT DO NOTHING`), y `partner_model_allowlist_on_partner()` redefinida con los seis;
  - `downgrade`.

  Columnas en `ModelProfile`. Los dos ids, en `BOOT_HOP_MODEL_IDS` de `core/respond_catalog.py`.

  Hecho el 2026-11-20 con un cambio sobre la spec: la etiqueta de oferta de los tres de Anthropic es «Claude Opus 5.5», «Claude Sonnet 5.5» y «Claude Haiku 5.5», como los nombra el diseño aprobado.

  _Requisitos: 1.1, 1.2, 1.3, 1.7, 5.2_
- [X] T004 [P] Test en rojo `apps/api/tests/unit/test_respond_model_resolution.py`:
  - orden agente → versión → por defecto de Auphere (`platform_settings.agent_respond_default`), con todas las combinaciones de huecos;
  - `source` correcto;
  - un origen que no puede ejecutar lo que el agente necesita (Skills o conector MCP de Anthropic) se salta;
  - **barrido AST**: `pipeline.py`, `model_lifecycle.py`, `model_usage.py`, `api/console/models.py`, `api/console/agent_model.py`, `api/admin/agent_models.py`, `core/partner_allowlist.py`, `api/admin/budget_policies.py`, `api/console/companion.py`, `worker/metering/pricing.py` y `runtime/model_resolver.load_bindings` no deciden el modelo de respuesta sin `resolve()`, y ninguno lee el rol `respond` de `tenant_model_bindings`.

  _Requisitos: 2.2, 4.8_
- [X] T005 Implementar `apps/api/src/nexus_api/core/respond_model.py` (`resolve`, puro, data-model.md §5).

  _Requisitos: 2.2, 4.8_
- [X] T006 [P] Test en rojo `apps/api/tests/unit/test_respond_profiles_cover_the_catalog.py`:
  - hay perfil para los seis y cada uno declara `family`, `timeout_s`, `max_tokens`, `forbidden`, `reserve`, `cross_in_request`, `block_binding`, `estimate_factor` y `supports`;
  - la reserva de un perfil es de la otra familia y tiene perfil;
  - todo modelo con `offer_label` en las migraciones tiene perfil;
  - las `capabilities` sembradas no contradicen al perfil (`reasoning_control`, `context_management`);
  - el perfil de Sonnet 5.5 para el cruce (`cross_in_request`) es `{"type": "between_tools"}` sin ningún otro campo, y nunca lleva `block_binding`;
  - `test_platform_default_models` sigue en verde.

  _Requisitos: 1.3, 4.1, 4.2, 4.7, 11.1_
- [X] T007 Implementar `apps/api/src/nexus_api/core/respond_profiles.py` con la tabla de plan.md §2 (el worker lo importa: la dependencia declarada es del worker a `nexus-api`, aunque algunos módulos del panel de la API importen `nexus_worker`), y que `apply_capabilities` tome el razonamiento del perfil cuando lo hay.

  _Requisitos: 1.3, 4.1, 4.2, 4.7, 11.1_
- [X] T008 [P] Test en rojo y cambio de `core/respond_catalog.py` (`lists_from_rows`, `refresh_from_db`), con dos vistas que no se mezclan:
  - **ofrecible**: `offer_label` ∩ `status 'active'` ∩ con perfil;
  - **ofrecido**: ofrecible ∩ `respond_enabled_at IS NOT NULL`.

  Un modelo ofrecible sin habilitar no se puede elegir, pero sigue siendo ejecutable y **sí puede guardarse en la lista de un partner**: `api/admin/partner_models.py` valida contra el conjunto ofrecible, con su prueba (hoy valida contra la oferta y rechazaría Claude). Actualizar `test_model_catalog_matches_db`.

  _Requisitos: 1.2, 1.3, 7.4_
- [X] T009 [P] Test en rojo `apps/worker/tests/unit/test_every_llm_use_on_the_wire.py` (servidor de eco, `LITELLM_LOCAL_MODEL_COST_MAP=True`, la versión del lock), con un caso por cada uso de `platform_models.default_models()`: clasificar, freno de reservas, corrector, extraer, simular, copiloto (manda `thinking` como kwarg), visión, transcripción, mejora de prompts, constructor y evaluaciones. Cada caso sale del proceso sin `UnsupportedParamsError` y con los parámetros que hoy llegan al proveedor. Arreglar lo que falle **en el mismo cambio que T001**: fijar el mapa no puede romper ningún uso.

  _Requisitos: 4.12, 3.2_

- [X] T045 Migración `apps/api/alembic/versions/0239_cache_write_lane_default.py` (data-model.md §8): `quota_weight_cache_write`, con el relleno de las filas existentes; la tarifa de escritura de GPT-5.6 (Sol 5,00, Terra 2,50, Luna 0,25) en `model_profiles` y en una fila nueva de `model_prices` por modelo que copia las demás tarifas en vigor (gana la fila más reciente), con su peso (1,10, 0,55 y 0,055); y `platform_settings.agent_respond_default` en Sol. Las columnas, en `ModelProfile` y en el modelo de `platform_settings`.

  _Requisitos: 5.5, 5.8, 13.1_
- [X] T014 Arreglo del cierre del turno con GPT-5.6 (research.md §D8.1): `tool_choice: "none"` hacia OpenAI viaja en `extra_body` (`runtime/llm.py`, `_drop_openai_unsupported`), con su test en el cable con el mapa local, en `apps/worker/tests/unit/test_respond_profiles_on_the_wire.py`. Va en la fase 1 porque T001 fija el mapa y, sin esto, el cierre fallaría con Sol, Terra y Luna.

  _Requisitos: 4.1, 4.12_

  Hecho el 2026-11-20 sin `extra_body`: con las entradas de T001 registradas, `tool_choice: "none"` hacia GPT-5.6 sale por `/chat/completions`. Lo vigila `test_every_llm_use_on_the_wire.py` (casos `closure` y `companion`, que exigen esa ruta).

---

## Fase 2: Aislamiento y barridos, en rojo

- [X] T010 [P] Test en rojo `apps/api/tests/isolation/test_065_agent_model_scope.py`:
  - el partner A no lee ni cambia el modelo de un agente del cliente de B: `404`, igual que un agente inexistente o archivado;
  - una sesión con la GUC de un cliente no ve las columnas de modelo de los agentes de otro;
  - el `PUT` del panel solo toca agentes del `tenant_id` de la ruta.

  _Hecho el 2026-11-20 para la consola y la GUC; el caso del panel va con su endpoint, en T070._

  _Requisitos: 10.1, 10.2_
- [X] T011 [P] Entrada de `PUT /console/clients/{ref}/agents/{agent_id}/model` en `_minimal_body` de `apps/api/tests/isolation/test_console_scope.py` (`{"model_id": null}`), para que el barrido espere `404` del otro partner.

  _Requisitos: 10.2_
- [X] T012 [P] Test en rojo `apps/worker/tests/unit/test_agent_bundle_respond_model.py`: `bundle_of` lee la elección con la sesión ya acotada (sin `WHERE tenant_id` propio), y un agente sin elección deja `respond_model = None`.

  _Requisitos: 2.1, 10.1_
- [X] T013 [P] Test en rojo en `apps/worker/tests/unit/test_respond_profiles_on_the_wire.py`: las llamadas de dos clientes, incluidas las de la reserva cruzada, salen en peticiones separadas, sin lote.

  _Hecho el 2026-11-20 para OpenAI y Claude; el caso de la reserva cruzada se añade con su implementación, en T051._

  _Requisitos: 10.3_

---

## Fase 3: El partner elige el modelo de un agente (US1, P1) 🎯 MVP

**Objetivo**: un partner cambia el modelo de un agente desde Avanzado y el siguiente turno responde con él. Con Sol, Terra y Luna habilitados ya se puede entregar.

**Prueba independiente**: con un cliente de dos agentes, cambiar el modelo de uno y comprobar que su siguiente turno responde con el nuevo, que el otro sigue igual y que hay auditoría.

- [X] T020 [P] [US1] Test en rojo `apps/api/tests/integration/models/test_agent_model_console.py`:
  - `GET` devuelve `choice`, `effective` con `source`, `options` y `can_change`. `options` es activo ∩ habilitado ∩ con perfil ∩ lista del partner, de menor a mayor precio, sin modelos que el agente no pueda ejecutar.
  - `PUT` escribe las tres columnas con `set_by = 'partner'`, audita `console.agent.model.update` con antes y después y publica `"{tenant_id}:{agent_id}"`.
  - `effective` lleva `estimate` y `outside_offer` (`null`, `retired` u `operator`), también cuando no está en `options`.
  - `PUT {"model_id": null}` vuelve al modelo por defecto (solo lo usa el panel).
  - `422 unknown_model` si está fuera de la oferta, sin habilitar, sin perfil o inactivo; `422 model_unavailable_for_agent`.
  - `403` con `agents:read`.
  - No publica versión ni lanza pruebas.
  - Regresión: un cambio de `model_policy` por el borrador o por `quality/check` sigue dando `409 model_policy_managed`.

  _Requisitos: 1.2, 1.5, 2.3, 2.4, 2.5, 2.6, 2.7, 6.2, 9.1_
- [X] T021 [US1] Implementar `apps/api/src/nexus_api/services/agent_model.py` y `apps/api/src/nexus_api/api/console/agent_model.py` (`GET/PUT /clients/{ref}/agents/{agent_id}/model` sobre `agent_in_path`), montado en `api/console/__init__.py`. Contrato en contracts/api.md.

  _Requisitos: 1.2, 1.5, 2.3, 2.4, 2.5, 2.6, 2.7_
- [X] T022 [P] [US1] Test en rojo `apps/api/tests/integration/models/test_agent_model_estimate.py`:
  - con consumo de 7 días, el precio por respuesta de cada opción sigue research.md §D14, «Estimación del selector»: la fracción leída de caché del agente a la tarifa de lectura, y lo no leído a la de escritura (Anthropic y GPT-5.6, que se repercute; Luis, 2026-11-19) o a la de entrada si el modelo no la tiene, × pesos × multiplicador × `estimate_factor` (`basis: "agent_7d"`). El test comprueba la regla con un perfil fijo, no un orden entre modelos;
  - `options` sale de menor a mayor con ese precio;
  - sin consumo, un turno típico (`basis: "nominal"`);
  - importes en cien milésimas.

  _Requisitos: 1.5, 1.6_
- [X] T023 [US1] Implementar la estimación en `services/agent_model.py`, y `provider` y `line` en `GET /console/models` (`api/console/models.py`, `schemas_models.py`).

  _Requisitos: 1.5, 1.6_
- [X] T024 [P] [US1] Test en rojo `apps/worker/tests/unit/test_respond_model_precedence.py`:
  - con elección, el turno responde con ella;
  - sin elección ni ajuste de versión, con `agent_respond_default`, que al desplegar es Sol (igual que hoy);
  - `llm_respond_model` ya no decide el modelo de un agente, solo el de la plataforma;
  - con presupuesto en degradación, el más barato por encima de todo;
  - clasificar, el freno de reservas, el corrector, el juez y el cliente simulado siguen con los modelos de la plataforma aunque el agente elija otro.

  _Requisitos: 2.2, 2.3, 3.2, 3.3_
- [X] T025 [US1] Worker: `AgentBundle.respond_model` cargado en `bundle_of` (`runtime/agent_loader.py`), y la resolución de `pipeline.py` por `resolve()`. Deja en verde T012 y T024.

  _Requisitos: 2.1, 2.2, 2.3, 3.3_
- [X] T026 [P] [US1] Tests en rojo de la consola en `apps/console/src/components/builder/__tests__/agent-model-select.test.tsx`:
  - cinco estados: cargando, vacío (sin opciones: «Responde con {modelo}» con su precio y «escríbenos»), error con reintento, parcial (sin estimación) e ideal;
  - solo salen modelos de `options`, del más barato al más caro, con «Ahora» en `effective`, que es también la opción seleccionada al abrir; no hay chip de origen ni opción para volver al modelo por defecto;
  - con `outside_offer`, la línea con el modelo, su precio y el motivo («ya no se ofrece» o «Auphere eligió»);
  - la línea de cada modelo es la de su gama (requisito 1.5);
  - «estimado» junto al precio;
  - con `agents:read`, solo lectura;
  - guardar llama a la acción y enseña el toast;
  - un modelo fuera de `options` no aparece; `notice` se enseña;
  - textos largos (alemán, +30 %) sin desbordar.

  Y en `agent-builder.test.tsx`: Avanzado ya no tiene `model-managed`, y no monta «Calidad» ni «Fijar un modelo» (`AgentModelQuality`).

  _Requisitos: 1.5, 2.4, 2.7, 4.8, 9.1, 9.2_
- [X] T027 [US1] Implementar la consola:
  - `components/builder/agent-model-select.tsx`, con `@nexus/ui`, tokens y sin hex;
  - el bloque en Avanzado de `agent-builder.tsx`;
  - carga en `app/(console)/clients/[ref]/agents/[agentId]/page.tsx`;
  - acciones en `agents/agent-model-actions.ts` (zod, `agents:write`);
  - `lib/backend/models.ts`;
  - `i18n/lanes/builder-model.ts` (es/en).

  _Requisitos: 1.5, 2.4, 2.7, 4.8, 9.2_
- [X] T028 [US1] Retirar el `ModelPicker` de `app/(console)/clients/[ref]/agent/page.tsx` (y el componente y sus textos si quedan sin uso). Comprobar que la consola lite y la app móvil no enseñan el modelo.

  _Requisitos: 2.8, 9.3_
- [X] T029 [P] [US1] Test en rojo `apps/api/tests/unit/companion/test_model_proposal_per_agent.py`:
  - la propuesta pide `client_ref` y `agent_id`;
  - valida contra `GET …/agents/{id}/model`, sin la lista escrita a mano «uno de los tres»;
  - aplica por `PUT …/agents/{id}/model` tras la confirmación.

  _Requisitos: 2.9_
- [X] T030 [US1] Implementar la propuesta por agente en `apps/api/src/nexus_api/companion/tools/{catalog,proposals,actions}.py`.

  _Requisitos: 2.9_

### Un solo sitio: la asignación del cliente pasa a sus agentes (US1)

- [X] T031 [P] [US1] Script de comprobación previa, solo lectura, `apps/api/scripts/respond_bindings_report.py`: clientes con asignación `respond`, modelo, agentes no archivados, y cuáles tienen `fallback_chain` o `max_cost_per_turn_usd`, que dejan de usarse. Correrlo en staging; en prod, con el sí de Luis (tarea suelta con la definición del scheduler, como la memoria de diagnóstico). Revisar el resultado antes del despliegue.

  _Requisitos: 12.3_
- [X] T032 [P] [US1] Test en rojo `apps/api/tests/integration/models/test_0240_respond_bindings_to_agents.py`:
  - cada agente activo sin elección de un cliente con asignación `respond` recibe ese modelo;
  - `set_by = 'partner'` si la última auditoría del modelo del cliente es `console.model.update` **y su `after_json.model_id` coincide con el modelo de la fila**; si no, `'operator'`;
  - una línea `model.respond_binding.migrated` por cliente con lo de antes;
  - no falla con `fallback_chain` o tope;
  - no borra las filas;
  - `downgrade` las deja como estaban;
  - un agente archivado no recibe nada;
  - la prueba corre con el rol con el que corren las migraciones, no con un superusuario, para que la RLS forzada de `agents` no deje escribir 0 filas en silencio;
  - la migración deja escrito cuántas asignaciones encontró y cuántos agentes escribió, para compararlo con T031.

  _Requisitos: 12.1, 12.2, 12.6_
- [X] T033 [US1] Migración `apps/api/alembic/versions/0240_respond_bindings_to_agents.py` (data-model.md §9), con el patrón de la 0229 para datos de cliente (`SET LOCAL row_security = off` dentro de un bloque, que falla en vez de filtrar) y `RAISE NOTICE` con los recuentos.

  _Requisitos: 12.1, 12.2, 12.6_
- [X] T034 [P] [US1] Test en rojo y retirada:
  - `PUT /console/clients/{ref}/model` responde `410 client_model_retired` y el `GET` ya no existe (y sale de `test_console_scope.py`);
  - `PUT` y `DELETE /admin/tenants/{id}/model-bindings/respond`, `422 respond_is_per_agent`; los demás roles igual. Solo la consola llama hoy al modelo por cliente (la app móvil y el escritorio no: comprobado con un `grep` el 2026-11-19);
  - `load_bindings` ya no devuelve `respond`;
  - `reconcile_bindings` deja el rol `respond`.

  _Requisitos: 12.4_
- [ ] T035 [P] [US1] Test en rojo: un agente migrado con un modelo heredado sin perfil (Claude Sonnet 4.6) responde con los parámetros de hoy, byte a byte. La consola lo enseña con su precio y la línea «ya no se ofrece» (`outside_offer: retired`), sin incluirlo en `options`, y el partner solo puede cambiarlo a uno de su oferta.

  _A medias el 2026-11-20: la consola, en verde (`test_agent_model_legacy.py`). El cable (`test_respond_profiles_on_the_wire.py`, el de Sonnet 4.6 frente al camino sin perfiles) todavía no puede fallar: el turno de hoy va por `respond_with_tools` sin salto enrutado, y por ahí ningún perfil llega al cable (la rama de `apply_capabilities` solo corre con un salto del router). Se cierra con T052, con la mutación (un perfil de Claude 5.5 aplicado a Sonnet 4.6 tiene que cambiar el cuerpo)._

  _Requisitos: 12.5_

**Punto de control**: MVP con Sol, Terra y Luna por agente, en un solo sitio. Jemma queda con Terra elegido para su agente.

---

## Fase 4: Lo que se cobra y lo que se informa (US3, P1)

- [ ] T040 [P] [US3] Test en rojo `apps/worker/tests/unit/test_metering_per_served_model.py`:
  - la llamada de la reserva (de otra familia) se registra y se cobra con sus pesos;
  - Opus 5.5 y Sonnet 5.5 tienen pesos (ningún `metering.unweighted_model`).

  _Requisitos: 5.1, 5.2_
- [ ] T041 [P] [US3] Test en rojo `apps/worker/tests/unit/test_response_model_is_served.py`:
  - `response_model` es el modelo que respondió, también con asignación o elección;
  - `response_fell_back`;
  - `handler.turn_complete` y `llm.respond_fell_back` sin texto;
  - `_ask_agent_to_rewrite` usa la cadena del agente;
  - `llm.attempt_failed` lleva la clase original aunque se mapee a `LLMProxyUnavailable`.

  _Requisitos: 3.1, 5.3, 5.4_
- [ ] T042 [US3] Implementar en `runtime/llm.py`, `pipeline.py` y `state.py`:
  - `LLMResponse.model`, `fell_back` y `finish_reason` desde `_call_with_resilience`;
  - `response_model` y `response_fell_back`;
  - `llm.respond_fell_back`;
  - la reescritura por la cadena del agente;
  - la clase original en `llm.attempt_failed`.

  _Requisitos: 3.1, 5.3, 5.4_
- [ ] T043 [US3] Comprobar que `metering` cobra por `usage_records.model` del salto. Deja en verde T040.

  _Requisitos: 5.1, 5.2_
- [ ] T044 [P] [US3] **Primero, en el cable** (servidor de eco, mapa local, LiteLLM 1.83.0 y 1.83.14): una respuesta de Anthropic con `cache_creation_input_tokens` y `cache_read_input_tokens` ¿suma las dos en `prompt_tokens`? Y una de GPT-5.6 con `prompt_tokens_details.cache_write_tokens` y `cached_tokens`: ¿la deja pasar LiteLLM con las dos versiones, y el colector la registra como `llm.cache_write`? Hoy Sol sale con escritura 0 (research.md §D14, «Hallazgo»). Fijar las dos respuestas en un test; si `prompt_tokens` no incluye lo escrito, ajustar la fórmula de abajo antes de tocar el consumidor (research.md §D14). Después, test en rojo `apps/worker/tests/unit/test_cache_write_lane.py`:
  - una llamada de Anthropic con lectura y escritura en caché cobra la entrada como «prompt − lectura − escritura» y la escritura con su peso;
  - el margen es el multiplicador en los cuatro carriles;
  - una llamada de GPT-5.6 con `cache_write_tokens` cobra lo escrito por el carril de escritura con su peso, y no además como entrada;
  - un modelo sin tarifa de escritura cobra lo mismo que hoy;
  - una llamada de Haiku 5.5 con más de 100.000 tokens de prompt se cobra con los pesos del tramo;
  - un modelo sin peso de escritura cuando la tiene da `unweighted_model`, no un cobro a 0.

  _Requisitos: 5.5, 5.6, 5.7, 5.8_
- [ ] T046 [US3] Implementar el cuarto carril:
  - `cache_write` en `metering/pricing_policy.LANES` y `weights_for`;
  - en `worker/metering/consumer.py`, `_apply_native_breakdown` (entrada = prompt − lectura − escritura; escritura con su cantidad, también la de GPT-5.6 desde `prompt_tokens_details.cache_write_tokens`) y `_apply_lane_weights`;
  - los tramos desde `model_prices.surcharge`;
  - el mismo cálculo en el camino del copiloto (`api/console/companion.py`);
  - el recálculo de pesos al cambiar el multiplicador (spec 059) y el campo en la edición de pesos del panel (`api/admin/models_catalog.py` y `apps/admin`).

  Deja en verde T044.

  _Requisitos: 5.5, 5.6, 5.7_
- [ ] T047 [P] [US3] Actualizar las pruebas de la spec 007 y de la 059 que fijaban tres carriles (`test_metering_end_to_end`, `test_sale_api` y las de `pricing_policy`), con el importe nuevo calculado a mano en el test, no copiado del resultado.

  _Requisitos: 5.5, 5.7_

---

## Fase 5: Cambiar de familia sin degradar el turno (US2, P1)

**Objetivo**: los seis modelos atienden un turno completo con herramientas, la reserva de la otra familia lo termina si hace falta, y nada de lo enviado se edita a mitad de turno.

**Prueba independiente**: la batería en el cable (T050, T051) en CI y la batería real en staging (T064).

- [ ] T050 [P] [US2] Tests en rojo en `apps/worker/tests/unit/test_respond_profiles_on_the_wire.py` (servidor de eco, mapa local), uno por perfil y escenario:
  - **GPT-5.6**: `reasoning_effort: "none"` en el cuerpo, sin desvío a `/responses`; el cierre con `tool_choice: "none"` sale (lo arregla T014); nunca `thinking` ni `output_config`.
  - **Claude 5.5**: `output_config.effort = "low"`, `max_tokens` del perfil, `thinking.block_binding.prefix_mismatch_behavior = "drop_block"` con su beta, sin `temperature`, `top_p`, `top_k`, `reasoning_effort` ni `tool_choice` forzado; `messages` nunca acaba en `assistant`.
  - **Solo se añade**: entre la primera y la última llamada de un turno con Claude, el `system` de arriba, el conjunto de herramientas y los mensajes anteriores son idénticos byte a byte. El cierre es solo `tool_choice: "none"`, y el reintento del freno de reservas no retira nada.
  - **Razonamiento**: el bloque vuelve delante del `tool_use` con la firma intacta, también `redacted_thinking`.
  - **Saneado**: al caer a GPT-5.6 no salen `thinking_blocks`, `reasoning_content`, `provider_specific_fields` ni `tool_calls[].index`.
  - **Cruce**: GPT-5.6 cae a Sonnet 5.5 tras herramientas, y Sonnet sale con `thinking: {"type": "between_tools"}` **sin ningún otro campo** (ni `block_binding` ni su beta) el resto del turno; los bloques de progreso que devuelva se conservan y vuelven a Sonnet; si cae en la primera llamada, con el razonamiento normal.
  - **Rechazo**: `stop_reason: "refusal"`, con y sin texto parcial, no llega al cliente, no se reintenta en el mismo modelo y pasa a la reserva.
  - **Plazo**: el `timeout` de cada perfil.
  - **Caché hacia Claude** (research.md §D14): una marca `cache_control` fija en el último bloque del `system` y la caché de la conversación, 5 minutos. Antes de escribir el rojo, probar en el cable qué forma deja pasar LiteLLM: el campo `cache_control` de arriba (caché automática, no toca los mensajes y no choca con «solo se añade») o, si no pasa, una marca en el último mensaje. La forma elegida no puede romper la igualdad byte a byte de lo anterior que pide «Solo se añade»; si es la marca que se mueve, la batería real en modo estricto (T055) decide si cuenta como edición.

  _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.10, 11.3_
- [ ] T051 [P] [US2] Test en rojo `apps/worker/tests/unit/test_respond_fallback_mid_turn.py`, en las dos direcciones (Opus → Terra y Sol → Sonnet 5.5):
  - la segunda llamada falla y la reserva termina el turno;
  - la tercera sigue con la reserva;
  - ninguna herramienta se ejecuta dos veces;
  - el cliente recibe la respuesta;
  - con todo caído, la frase de siempre;
  - la cadena es elegido → reserva de la otra familia, sin reservas propias de cliente.

  _Requisitos: 4.4, 4.5, 11.1, 11.3, 11.4_
- [ ] T052 [US2] Implementar en `runtime/llm.py`:
  - el perfil del modelo de cada salto en `respond_with_tools`: kwargs, `allowed_openai_params` solo para `thinking`, `output_config` como kwarg, plazo y `max_tokens` (el `tool_choice` hacia OpenAI ya lo resolvió T014);
  - `output_config` en `_ANTHROPIC_ONLY_ON_OPENAI`;
  - en `acomplete_with_tools`, `thinking_blocks` y `ProviderRefused` con `content_filter`;
  - sin bloquear: buscar en LiteLLM una ruta a la respuesta original (un callback de éxito) para registrar los descartes de `drop_block`, porque LiteLLM no devuelve `input_transformations` (research.md §D4.3). Si no la hay, anotarlo en research.md;
  - `_call_with_resilience`, sin reintento de un rechazo;
  - el saneado por destino;
  - `TurnModelPin`, con el cruce sin razonamiento.

  _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.11, 11.3_
- [ ] T053 [US2] Implementar en `runtime/pipeline.py`:
  - `_assistant_tool_message` guarda `thinking_blocks` con su modelo;
  - el cierre por perfil: con Claude, sin `FINAL_ANSWER_NOTE` y con las mismas herramientas; con GPT-5.6, como hoy;
  - el freno de reservas no retira nada en un turno con razonamiento;
  - la cadena con la reserva del perfil;
  - el `TurnModelPin` del turno.

  Deja en verde T050 y T051.

  _Requisitos: 4.3, 4.4, 4.5, 4.10, 11.1, 11.3, 11.4_
- [ ] T054 [P] [US2] Test en rojo y arreglo de la incompatibilidad en ejecución: un agente con Skills o conector MCP de Anthropic y un modelo de OpenAI elegido responde con el siguiente origen que pueda; su reserva es de Anthropic; el `GET` devuelve `notice = "chosen_model_cannot_run_agent"`.

  _Requisitos: 4.8_
- [ ] T055 [US2] Script de la batería real `apps/worker/scripts/respond_compat.py` (research.md §D9.2):
  - un agente de prueba con herramientas simuladas;
  - los escenarios por modelo: sin herramientas, cadena de tres, imagen, cambio entre turnos, reserva a mitad de turno en las dos direcciones, cruce de OpenAI a Sonnet 5.5 tras herramientas, freno de reservas con reintento y turno largo hasta el cierre;
  - `prefix_mismatch_behavior = "error"` durante la batería;
  - informe con resultado, p95, coste y factor de gasto frente a Sol por modelo;
  - se niega a correr con `--env prod`;
  - tres escenarios con nombre, que el servidor de eco no puede probar porque son hechos del proveedor: `openai_cache_write_reported` (GPT-5.6 devuelve `prompt_tokens_details.cache_write_tokens` por Chat Completions a través de LiteLLM), `prompt_tokens_include_writes` (Anthropic y OpenAI cuentan lo escrito dentro de `prompt_tokens`) y `cache_marker_is_not_an_edit` (la forma de caché de T050 no dispara el control de historial en modo estricto).

  _Requisitos: 4.9, 11.3_
- [ ] T056 [P] [US2] Test en rojo y cambio de la puerta de la reserva:
  - la cadena usa la reserva del perfil solo si está habilitada en ese entorno y, si no, Sol, como hoy;
  - `platform_models.default_models()` publica las reservas habilitadas como usos (`respond_fallback_openai`, `respond_fallback_anthropic`), y la 059 no deja retirarlas ni deshabilitarlas.

  En `apps/worker/tests/unit/test_respond_fallback_mid_turn.py` y `test_platform_default_models.py`.

  _Requisitos: 11.1, 11.2, 8.1_

---

## Fase 6: Probar un agente con el modelo elegido (US4, P1)

- [ ] T060 [P] [US4] Test en rojo `apps/worker/tests/unit/test_simulation_uses_agent_model.py`:
  - la simulación responde con el modelo efectivo del agente;
  - `TurnOutcome.model` y `fell_back` son reales;
  - el juez evita la familia que respondió de verdad (`customer.py`, `avoid_model`).

  _Requisitos: 6.1, 5.3_
- [ ] T061 [US4] Implementar en `simulation/runner.py` y `simulation/customer.py` lo que falte para T060.

  _Requisitos: 6.1, 5.3_
- [ ] T062 [P] [US4] Test en rojo y arreglo: el resultado de cada prueba y la respuesta del Playground del agente (`api/console/agent_playground.py`) llevan `model` y `fell_back`, y la consola los enseña.

  _Requisitos: 5.3, 6.1_
- [ ] T063 [P] [US4] Test en rojo: cambiar el modelo no crea trabajos `tests` ni toca `agents.tests_pass_returned_at`, y una pasada lanzada después se cobra por `billing.next_full_pass` (spec 047, requisito 68).

  _Requisitos: 6.2, 6.3_
- [ ] T064 [US4] **Batería real en staging** (única tarea que llama a proveedores, < US$ 1 la pasada):
  1. Desplegar en staging.
  2. `uv run python scripts/respond_compat.py --env staging --models all`.
  3. Anotar el resultado en quickstart.md §3.
  4. Pasar los `estimate_factor` y plazos medidos al registro.
  5. Habilitar en staging los modelos de Anthropic que pasen, desde el panel, con la nota de la pasada.

  En prod se habilitan tras el paso a `main`, con la misma nota y después de T065.

  Anotar también el coste por respuesta de cada modelo frente a Sol con el agente de prueba (CE-006).

  _Requisitos: 1.3, 4.9, 11.2, CE-002, CE-006_

- [ ] T065 [US4] **Humo en prod antes de habilitar**, con el sí de Luis: una llamada mínima por modelo de Anthropic (Opus 5.5 y Sonnet 5.5) con la clave de prod, en una tarea suelta con la definición del runner (vía documentada en la memoria de diagnóstico de prod). Confirma que la cuenta de prod llama a esos modelos. Fuera de un turno, sin cobro a nadie. Anotar el resultado en quickstart.md §3.

  _Requisitos: 1.3, 11.2_

---

## Fase 7: Auphere ve, cambia y habilita desde el panel (US5, P2)

- [ ] T070 [P] [US5] Test en rojo `apps/api/tests/integration/models/test_agent_model_admin.py`:
  - `GET /admin/tenants/{id}/agents/models`;
  - `PUT` con cualquier modelo habilitado para responder en el entorno (esté o no en la lista del partner), `reason` obligatorio, `set_by = 'operator'`, `admin.agent.model.update` e invalidación;
  - la consola enseña ese modelo en `choice` sin incluirlo en `options`.

  _Requisitos: 7.1, 7.2, 7.3_
- [ ] T071 [US5] Implementar `apps/api/src/nexus_api/api/admin/agent_models.py` (montado en `api/admin/__init__.py`) sobre `services/agent_model.py`.

  _Requisitos: 7.1, 7.2, 7.3_
- [ ] T072 [P] [US5] Test en rojo `apps/api/tests/integration/models/test_model_respond_enable.py`:
  - `respond-enable` exige perfil (`409 no_respond_profile`) y nota, escribe `respond_enabled_*`, audita y publica `CATALOG_CHANGED`;
  - `respond-disable` pasa al modelo por defecto las elecciones de partners con ese modelo, con `agent.model_reset`, y da `409 model_in_use` si es una reserva habilitada o el valor por defecto;
  - `GET /admin/models` enseña el estado.

  _Requisitos: 1.3, 1.4, 8.2, 11.2_
- [ ] T073 [US5] Implementar `respond-enable` y `respond-disable` en `apps/api/src/nexus_api/api/admin/models_catalog.py`.

  _Requisitos: 1.3, 1.4, 8.2, 11.2_
- [ ] T074 [P] [US5] Tests en rojo del panel:
  - `tenants/[id]/agent/__tests__/agent-models.test.tsx`: lista por agente con origen, cambio con motivo obligatorio y cinco estados;
  - `models/__tests__/respond-enable.test.tsx`: habilitar con nota y deshabilitar con motivo, con confirmación.

  _Requisitos: 7.1, 7.2, 1.3, 1.4_
- [ ] T075 [US5] Implementar en `apps/admin/src/app/(dashboard)/tenants/[id]/agent/` el bloque «Modelo» por agente, y en `apps/admin/src/app/(dashboard)/models/` «Habilitar para responder» y «Deshabilitar», con `apps/admin/src/lib/backend.ts`. La lista del partner (`partners/[id]/_sections/models*.tsx`) enseña los seis.

  _Requisitos: 7.1, 7.2, 7.4, 1.3, 1.4_

### El modelo por defecto de Auphere (US7, P2)

- [ ] T076 [P] [US7] Test en rojo `apps/api/tests/integration/models/test_agent_respond_default.py`:
  - `GET/PUT /admin/platform/agent-respond-default`: sin `confirm`, `409 confirm_required` con la lista de afectados (solo agentes sin elección ni ajuste de versión);
  - con `confirm`, escribe, audita con el motivo, invalida esos agentes y les devuelve la pasada de pruebas;
  - `422` con un modelo no habilitado;
  - volver a Sol deshace el cambio;
  - un agente con elección propia (el de Jemma, Terra) no cambia;
  - `default_models()` publica `agent_default` y la 059 no deja retirarlo ni deshabilitarlo;
  - cambiar el por defecto no crea ninguna notificación para los partners (requisito 13.6).

  _Requisitos: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_
- [ ] T077 [US7] Implementar el ajuste (la columna llega con T045), el endpoint en `apps/api/src/nexus_api/api/admin/platform_settings.py`, su lectura en `resolve()` por el catálogo cacheado (invalidación con `CATALOG_CHANGED`) y `agent_default` en `platform_models.default_models()`.

  _Requisitos: 13.1, 13.2, 13.3, 13.4, 13.5_
- [ ] T078 [P] [US7] Test en rojo e implementación en el panel (`apps/admin`, Plataforma › Modelos): el modelo por defecto con su selector (solo habilitados), el diálogo con la lista de afectados, el motivo y la confirmación, y los cinco estados.

  _Requisitos: 13.2_
- [ ] T079 [US7] **Paso a Haiku 5.5 en prod (operación, tras el paso a `main`)**, en este orden (research.md §D16):
  1. T064 y T065 en verde, y el cuarto carril (T046) en prod;
  2. habilitar Haiku 5.5 en prod con la nota de la pasada;
  3. con el sí de Luis, elegir Haiku para dos o tres agentes reales de clientes distintos (desde el panel, con motivo) y mirar una semana `llm.respond_fell_back`, derivaciones a persona y quejas;
  4. con el sí de Luis, cambiar el por defecto a Haiku 5.5 confirmando la lista de afectados. Jemma no está en ella.

  Anotar cada paso en quickstart.md.

  _Requisitos: 13.2, CE-008_

---

## Fase 8: Ningún agente sin modelo (US6, P2)

- [ ] T080 [P] [US6] Tests en rojo en `apps/api/tests/integration/models/test_model_usage.py` y `apps/api/tests/isolation/test_model_usage_scan_rls.py`:
  - un modelo elegido por un agente no archivado está en uso, y `retire` / `unavailable` dan `409 model_in_use` con el agente;
  - un agente archivado no cuenta;
  - el barrido sigue leyendo cada cliente con su GUC.

  _Requisitos: 8.1_
- [ ] T081 [US6] `services/model_usage.py` y `services/model_lifecycle.py` (`fixed_deployment`, `scan_agents`) por `resolve()`, con la elección de cada agente.

  _Requisitos: 8.1_
- [ ] T082 [P] [US6] Test en rojo en `apps/api/tests/integration/models/test_agent_model_admin.py`:
  - reescribir la lista de un partner sin Luna pasa al modelo por defecto los agentes con Luna elegida por el partner, y el aviso nombra el modelo con el que responden ahora;
  - una `agent.model_reset` por agente, sin ids internos;
  - no toca las elecciones de Auphere;
  - invalida esos agentes;
  - reconciliar la lista de un partner no toca los agentes de los clientes de otro partner, ni aunque compartan modelo (lo que fijaban las dos pruebas de `test_16_model_binding_scoped.py` que se retiraron con T034).

  _Requisitos: 8.2, 8.3, 10.1_
- [ ] T083 [US6] Implementar la reconciliación de agentes en `core/partner_allowlist.py` (en lugar de `reconcile_bindings` para el rol `respond`, una sesión por cliente), la notificación `agent.model_reset` (kind, vocabulario y texto en la consola) y su llamada desde `api/admin/partner_models.py` y desde `respond-disable`.

  _Requisitos: 8.2, 8.3, 1.4_
- [ ] T084 [P] [US6] Test en rojo: un modelo elegido cuyo `status` deja de ser ejecutable responde con la reserva y deja `llm.respond_fell_back`.

  _Requisitos: 4.4, 8.1_

---

## Fase 9: Cierre

- [ ] T090 Actualizar en el mismo cambio:
  - `docs/modelos-y-router.md`: la elección, la puerta por entorno, la reserva de la otra familia, el turno que solo añade y el requisito 64;
  - `docs/console.md`: Avanzado y la tarjeta de modelo por cliente retirada;
  - `docs/agentes.md`: el modelo que responde;
  - `docs/admin.md`: modelo por agente y «Habilitar para responder»;
  - `docs/billing.md`: pesos de Opus y Sonnet 5.5, el cuarto carril y los tramos;
  - `docs/admin.md`, además: el modelo por defecto de Auphere y la retirada del modelo por cliente.

  Y una nota de enmienda bajo el requisito 64 de `specs/047-la-fabrica-de-agentes/spec.md`.

  _Requisitos: todos_
- [ ] T091 Terraform: `LITELLM_LOCAL_MODEL_COST_MAP=True` en las taskdefs (`infra/terraform/20-services/`). Aplicar **solo en staging**; prod en el paso a `main` (memoria del 2026-11-03). El `setdefault` de T001 lo cubre mientras tanto.

  _Requisitos: 4.12_
- [ ] T092 Puertas de UI sobre el selector y los bloques del panel: `ui-states-checklist`, `a11y-audit`, `responsive-audit` y `design-tokens`, en vivo, con tema claro y oscuro.

  _Requisitos: 2.7, 9.2, 7.1_
- [ ] T093 `/cso` sobre el cambio: toca la autorización entre partners, el transporte de modelos y la configuración de LiteLLM. Ningún hallazgo HIGH abierto.

  _Requisitos: 10.1, 10.2, 10.3, 4.12_
- [ ] T094 Verificación:
  - `./scripts/verify.sh lint`;
  - las suites de los ficheros tocados (worker con `uv run --with lupa`);
  - `tests/isolation/` completa;
  - `./scripts/verify.sh js`;
  - `gh workflow run ci --ref develop` antes del PR a `main`.

  _Requisitos: todos_
- [ ] T095 Playwright en staging siguiendo quickstart.md §2, §4 y §5, con capturas; la prueba de CE-005 antes y después del despliegue; la reserva cruzada (§6) y la conciliación de un día de cobro (§7).

  _Requisitos: CE-001, CE-003, CE-004, CE-005, CE-007_
- [ ] T096 Mensajes de commit para Luis (guion en `.claude/commits/`) y nota de estado en la KB (`decisions/2026-11-19-modelo-por-agente.md`).

  _Requisitos: —_

## Dependencias

- La fase 1 bloquea todo, y va entera en el primer despliegue: **T001 (mapa fijo), T009 (cada uso probado) y T014 (el cierre con GPT-5.6) juntos**, o fijar el mapa rompería algún uso (research.md §D8.1 y §D13). T045 (migración 0239) está en la fase 1, aunque su número venga del bloque de cobro, porque la necesitan T024, T025 y T033.
- La fase 2 se escribe en paralelo tras T005 y T007.
- **US1 (fase 3) es el MVP**, con Sol, Terra y Luna, que la 0238 deja habilitados.
- US3 (fase 4) va tras T025. US2 (fase 5) va tras T042.
- US4 (fase 6) va tras T025 y T042. T064 va tras toda la fase 5 y tras T073, porque habilitar necesita el endpoint.
- US5, US6 y US7 (fases 7 y 8) van tras T021, en paralelo entre sí. T033 y T034 van en el mismo despliegue: migrar sin retirar dejaría dos sitios.
- **El cuarto carril (T044–T047) llega a prod antes de habilitar ningún Claude.** T079 es operación posterior al paso a `main`.
- Fase 9 al final; T091 en cualquier momento tras T001.

## Paralelo por historia

- **US1**: tests T020, T022, T024, T026 y T029 a la vez; después, API (T021, T023), worker (T025), consola (T027, T028) y copiloto (T030).
- **US2**: T050, T051 y T056 a la vez; T052 antes que T053; T054 y T055 en paralelo a T052.
- **US5 y US6**: T070, T072, T074, T080 y T082 a la vez.

## Estrategia

1. Fases 1 y 2, y la fase 3: **MVP por agente con Sol, Terra y Luna, en un solo sitio** (las asignaciones de cliente pasan a sus agentes), con LiteLLM ya determinista.
2. Fase 4: el informe y el cobro dicen la verdad antes de cruzar de familia.
3. Fase 5: el turno entre familias, con la batería en el cable en verde.
4. Fases 6 y 7, y T064: la batería real en staging. Auphere habilita en staging lo que pase y la reserva cruzada empieza a funcionar allí.
5. Fase 8 y fase 9: guardas, documentación, puertas, `/cso`, verificación y commits. En prod, habilitar tras el paso a `main`.
