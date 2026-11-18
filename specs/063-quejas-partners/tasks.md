---

description: "Tareas de la spec 063 — las quejas de los partners del 2026-11-18"
---

# Tasks: Las quejas de los partners del 2026-11-18

**Input**: Design documents from `/specs/063-quejas-partners/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/agent-spec-voice.md](contracts/agent-spec-voice.md), [contracts/console-api.md](contracts/console-api.md), [quickstart.md](quickstart.md)

**Tests**: obligatorios (constitución §VII). Cada bloque de tests se escribe y se
ve en rojo antes de su implementación. Las reproducciones de `research.md` son ese
primer rojo.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: rojo antes que implementación.
- **Aislamiento (§I)**: la spec declara la garantía 5, rozada por el requisito 4. Va en T036.
- **Licencias (§VIII)**: no entra ninguna dependencia.
- **Medidor**: nada nuevo. T029 fija que un borrador fallido sigue en «Construcción y pruebas» y no sale de la bolsa del cliente (3.5).
- **Suites de una en una**: dos a la vez comparten base y dan rojos falsos.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: la historia de la spec (US1 idioma, US2 canal, US3 borrador, US4 nombres)

---

## Phase 1: Setup

**Propósito**: saber que el punto de partida está en verde, para que cualquier
rojo posterior sea de este cambio y no de antes.

- [x] T001 Correr en `develop` (`2cc44b30`), de una en una, las suites que ya cubren lo que se toca, y anotar aquí el resultado:
  - `apps/worker/tests/unit/test_console_context.py`
  - `apps/api/tests/unit/test_agent_spec_validator.py`
  - `apps/api/tests/unit/test_agent_spec_contract.py`
  - `apps/api/tests/unit/test_057_builder_agenda.py`
  - `apps/api/tests/unit/test_companion_actions.py`
  - `apps/api/tests/unit/test_builder_guides.py`
  - `apps/api/tests/integration/builder/test_agent_draft_job.py`
  - `apps/worker/tests/unit/test_classifier_reaches_the_provider.py`
  - y en la consola, `pnpm vitest run` sobre `components/channels/__tests__/channel-card.test.tsx`, `whatsapp-connect.test.tsx`, `components/builder/__tests__/block-editor-voice.test.tsx` y `builder-new.test.tsx`

  _Requisitos: 1.4, 2.2, 3.1, 4.1_

  Resultado (2026-11-18, `develop` `2cc44b30`, base `nexus_test_063`), todo en verde:
  - worker (`test_console_context`, `test_classifier_reaches_the_provider`): 36;
  - API unitarias: 118;
  - `test_agent_draft_job`: 16;
  - consola (los cinco ficheros, incluido `life-model.test.ts`): 67.

---

## Phase 2: Foundational

Sin tareas. Las cuatro historias son independientes. US3 y US4 comparten
`agent_draft.py`, pero en funciones distintas (`parse_output` y `sanitize`). Si se
hacen en paralelo, que sea en ramas que se juntan antes de T043.

---

## Phase 3: User Story 1 — El agente contesta en el idioma del cliente (Priority: P1) 🎯 MVP

**Goal**: todo agente publicado contesta en el idioma del último mensaje del cliente, salvo que el partner limite los idiomas, sin volver a publicarlo, aunque su prompt fije otro idioma.

**Independent Test**: un agente publicado sin tocar nada, con un prompt que dice «Never answer in English», recibe una pregunta en inglés y contesta en inglés. Limitado a `es` y `en`, recibe francés y contesta en español.

### Tests for User Story 1 ⚠️ (rojo primero)

- [x] T002 [P] [US1] Crear `apps/worker/tests/unit/test_063_language_rule.py`:
  - `language_rule` sin límite y con límite tiene que dar, carácter a carácter, los textos de `contracts/agent-spec-voice.md`.
  - `{"allowed": ["es"], "primary": "es"}` guardado sin `limited` da la regla **sin** límite, y una versión **sin** `policies.console` también, con principal `es`.
  - `_build_handler_messages` pone la regla como **último** mensaje de sistema: detrás de la directiva del turno y antes del historial. Tiene que ser así también cuando el prompt dice «Never answer in English».
  - El bloque de operación ya no lleva «Languages:».
  - `_RETRY_SYSTEM_TEMPLATE` termina con «Keep the language of the reply you are rewriting.».

  _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7_
- [x] T003 [P] [US1] Crear `apps/api/tests/unit/test_063_language_policy.py`:
  - `LanguagesPolicy().limited is False`.
  - `merge_console_policy` conserva los `languages` guardados aunque el cuerpo traiga otros.
  - `POLICY_FIELDS` del Companion ya no tiene `primary_language`.

  _Requisitos: 1.6, 1.7_
- [x] T004 [P] [US1] Crear `apps/api/tests/unit/test_063_voice_limit.py`:
  - `Voice` acepta `languages_limited` y el contrato JSON lo describe como `boolean` opcional.
  - `validate_spec` con `author="builder"` da un problema si `languages_limited` cambia respecto a la base, y con `author="person"` no.
  - `sanitize` no deja pasar `languages_limited` aunque el modelo lo escriba en `voice`.

  _Requisitos: 1.6, 1.9_
- [x] T005 [US1] Crear `apps/api/tests/integration/test_063_languages_sync.py`:
  - Al guardar el AgentSpec en el borrador (`write_spec`), `voice` se copia a `policies.console.languages` como `{primary: languages[0], allowed: languages, limited}`, sin perder `ai_disclosure`.
  - Sin `voice.languages`, se quita `languages`.
  - Publicar lleva la copia a la versión.
  - `PUT …/agent-settings` con otros idiomas no los cambia.

  _Requisitos: 1.6, 1.7_
- [x] T006 [P] [US1] En `apps/console/src/components/builder/__tests__/block-editor-voice.test.tsx`:
  - El interruptor «Responder solo en estos idiomas» empieza apagado.
  - La línea de resumen dice los dos textos de `contracts/agent-spec-voice.md` según el estado.
  - Encenderlo guarda `languages_limited: true`.

  En `apps/console/src/components/agent-tools/__tests__/agent-settings-form.test.tsx`: el formulario ya no tiene campo de idiomas.

  _Requisitos: 1.6, 1.8_

### Implementation for User Story 1

- [x] T007 [US1] En `apps/api/src/nexus_api/services/agent_console_policy.py`:
  - `LanguagesPolicy.limited: bool = False`.
  - `language_rule(policies)` devuelve el texto del contrato. Sin política, usa los valores por defecto.
  - `render_operating_policy` deja de pintar «Languages:».
  - `merge_console_policy` conserva `languages` de lo guardado (D1–D4).

  _Requisitos: 1.1, 1.2, 1.3, 1.5, 1.7_
- [x] T008 [US1] En el worker:
  - `apps/worker/src/nexus_worker/runtime/console_context.py` expone `language_rule` para el bundle.
  - `apps/worker/src/nexus_worker/runtime/pipeline.py`: `_build_handler_messages` añade la regla como último mensaje de sistema, y `_RETRY_SYSTEM_TEMPLATE` gana su frase final (D1, D11).

  _Requisitos: 1.4, 1.5_
- [x] T009 [US1] En `apps/api/src/nexus_api/services/agent_spec/schema.py`, `Voice.languages_limited: bool | None = None` (con `SkipJsonSchema[None]`, como los demás campos). Añadirlo a `specs/047-la-fabrica-de-agentes/contracts/agent-spec.schema.json`. Regenerar los tipos de la consola si salen del esquema.
  _Requisitos: 1.6_
- [x] T010 [US1] En `apps/api/src/nexus_api/services/agent_spec/validator.py`, con `author != "person"` y `voice.languages_limited` distinto del de la base, dar el problema `languages_limit_by_builder` en `/voice/languages_limited`, como `ai_disclosure_decided_by_builder`.
  _Requisitos: 1.9_
- [x] T011 [US1] En `apps/api/src/nexus_api/api/console/agent_spec_drafts.py`, ampliar `_sync_disclosure` a `_sync_console(policies, spec, actor)`, que copia también los idiomas (D2).
  _Requisitos: 1.6_
- [x] T012 [P] [US1] En `apps/api/src/nexus_api/companion/tools/proposals.py`, quitar `primary_language` de `POLICY_FIELDS`, y de la descripción y las pruebas de la herramienta que lo citen.
  _Requisitos: 1.6_
- [x] T013 [US1] En `apps/console/src/components/builder/block-editor.tsx` («Cómo habla»):
  - Añadir el interruptor y la línea de resumen.
  - Cambiar la pista a «Marca los que habla. El primero es el principal: lo usa cuando no sabe en qué idioma le escriben.»
  - Textos en `apps/console/src/i18n/lanes/agent-proto.ts`, en `es` y `en`.
  - Añadir `languages_limited` al tipo del AgentSpec de la consola.

  _Requisitos: 1.6, 1.8_
- [x] T014 [P] [US1] En `apps/console/src/components/agent-tools/agent-settings-form.tsx`, quitar el bloque de idiomas, que ya no hace nada (constitución §V).
  _Requisitos: 1.6_

**Checkpoint**: T002–T006 en verde. El agente contesta en el idioma del cliente desde el turno, sin volver a publicarlo.

Resultado (2026-11-18): T002–T014 en verde.
- Worker: `test_063_language_rule` y `test_console_context`, 18.
- API: `test_063_language_policy`, `test_063_voice_limit`, `test_063_languages_sync`, `test_companion_actions`, `test_agent_spec_contract` y `test_agent_spec_validator`, 113.
- Consola: `block-editor-voice` y `agent-settings-form`, 20. `tsc` limpio.
- Pruebas que dependen del orden de los mensajes del turno (`test_now_note`, `test_next_message_uses_ficha`, `test_reception_handoff`, `isolation/test_44`, `isolation/test_48`): en verde.

Ajustes que hizo falta hacer:
- `test_console_context` fijaba la línea vieja dentro del bloque, y ahora fija que ya no está.
- En «Cómo habla», la línea «Principal: …» la sustituye el resumen de 1.8, que ya nombra el principal.
- T005 no publica: publicar copia las políticas del borrador tal cual, como antes.

---

## Phase 4: User Story 2 — Encontrar y decidir la configuración de un número (Priority: P1)

**Goal**: quien conecta un número desde Canales del cliente llega a su configuración, y un número «Sin configurar» dice en todas partes que no responde a nadie, también en el estado del agente.

**Independent Test**: un agente nuevo, sin número, se abre desde Agentes y llega a su pestaña Canales. Además, conectar un número desde Canales del cliente sin número de prueba.
- Se abre su configuración.
- De vuelta en la lista, la tarjeta dice «No responde a nadie» y «Configurar» lleva al mismo sitio.
- El agente se ve «Listo · número sin configurar».

### Tests for User Story 2 ⚠️

- [x] T015 [P] [US2] Crear `apps/api/tests/integration/test_063_channel_reach.py`:
  - `GET …/channels/overview` trae `audience_mode` en cada canal.
  - El agente que atiende (regla del principal, `agents.principal_agent_id`): con agente asignado, ese; sin asignar, el vivo por defecto; sin ninguno marcado pero con agentes vivos, el vivo más antiguo; sin agentes vivos, ninguno.
  - En los tres primeros casos, la página del canal se abre en el mismo agente que lo enseña en `agent_channels` y que lo lista en su tarjeta (`GET …/agents`).
  - Un agente `ready_no_channel` sale con `opens: "channels"`.

  _Requisitos: 2.3, 2.4, 2.5, 2.7_
- [x] T016 [P] [US2] Crear `apps/api/tests/unit/test_063_agent_state_unconfigured.py`:
  - `visible_state` de un agente publicado cuyo único número está «unconfigured» da `ready_no_channel` con `reason="unconfigured"`.
  - Sin números, sin `reason`.
  - Los recuentos de `agents_summary` no cambian.

  _Requisitos: 2.6_
- [x] T017 [P] [US2] En `apps/console/src/components/channels/__tests__/channel-card.test.tsx`:
  - «Configurar» enlaza a `/clients/{ref}/channels/{id}`.
  - Con `audience_mode: "unset"`: «No responde a nadie» en lugar de «Activo», y la acción principal «Decidir a quién responde», al mismo enlace.
  - Sin agentes en el cliente: «Necesita un agente que lo atienda» con enlace a crear uno, y sin «Configurar».

  En el test de la fila de Canales del agente: «sin configurar: no responde a nadie».

  _Requisitos: 2.2, 2.3, 2.5_
- [x] T018 [P] [US2] En `apps/console/src/components/channels/__tests__/whatsapp-connect.test.tsx`:
  - Al terminar la conexión, navega a `/clients/{ref}/channels/{channel_id}`.
  - Si se ofrece el catálogo, navega al cerrar la oferta, la acepte o no.
  - Sin agentes, navega igual: la ruta devuelve a la lista, donde la tarjeta dice que necesita un agente.

  _Requisitos: 2.1, 2.5_
- [x] T019 [P] [US2] En `apps/console/src/components/builder/__tests__/life-model.test.ts`:
  - `cardHref` de un agente con `opens: "channels"` es `/clients/{ref}/agents/{id}?tab=channels` y nunca `/clients/{ref}/channels`.
  - `ready_no_channel` con `reason: "unconfigured"` se pinta «Listo · número sin configurar», y sin `reason`, «Listo · sin canal».

  _Requisitos: 2.6, 2.7_

### Implementation for User Story 2

- [x] T020 [US2] Añadir `audience_mode` a `ChannelDetailOut` en `apps/api/src/nexus_api/api/console/schemas_channels.py` y rellenarlo en el resumen de `apps/api/src/nexus_api/api/console/channels.py`. Tipo: `"unset" | "team_only" | "everyone"`.
  _Requisitos: 2.3_
- [x] T021 [US2] En `apps/api/src/nexus_api/services/channel_config.py`, aplicar la regla del principal: el asignado; si no hay, el vivo por defecto; y si ninguno lo es, el vivo más antiguo. La usan `_agent_of`, `agent_channels` (`apps/api/src/nexus_api/api/console/channel_config.py:707`), que adopta así la caída al más antiguo, y la lista de canales de las tarjetas de agentes (`apps/api/src/nexus_api/services/agents.py:96`) (D8, D12).
  _Requisitos: 2.4_
- [x] T022 [US2] En `apps/api/src/nexus_api/services/agent_lifecycle.py`, `visible_state` pone `reason="unconfigured"` en `ready_no_channel` si algún número está sin configurar. Que la `reason` llegue a la consola donde ya viaja el estado visible del agente (D10).
  _Requisitos: 2.6_
- [x] T023 [US2] En la consola:
  - Añadir `audience_mode` al tipo `ChannelDetail` en `apps/console/src/lib/backend/channels.ts`.
  - En `apps/console/src/components/channels/channel-card.tsx` y `channels-list.tsx`: «Configurar», el estado «No responde a nadie» en vez de «Activo» y el estado sin agente, que la página ya sabe por `agentChoice`.
  - En `apps/console/src/i18n/lanes/channels-proto.ts`, `channels.proto.row.unset` pasa a «sin configurar: no responde a nadie».

  _Requisitos: 2.2, 2.3, 2.5_
- [x] T024 [US2] En `apps/console/src/components/channels/whatsapp-connect.tsx`, `router.push` a la configuración con el `channel_id` de la conexión, después de la oferta del catálogo si la hay.
  _Requisitos: 2.1_
- [x] T025 [US2] En `apps/console/src/components/builder/life-model.ts`:
  - `cardHref` lleva `opens: "channels"` a `${agentHref(refId, agent.id)}?tab=channels` (D12).
  - Donde se pinte el estado (`agent-builder.tsx`, la lista de clientes v2), usar «Listo · número sin configurar» cuando llega `reason: "unconfigured"`. Textos en `apps/console/src/i18n/lanes/business.ts`.

  _Requisitos: 2.6, 2.7_

**Checkpoint**: T015–T019 en verde.

Resultado (2026-11-18): T015–T025 en verde.
- API: `test_063_channel_reach` (5, con el canal del probador fuera de toda tarjeta), `test_063_agent_state_unconfigured` (4), y las de estado, atención, lista de clientes, ciclo de vida, menú del canal y enlace del dueño (119, `test_visible_state` incluido).
- Consola: builder, canales, ajustes y clientes, 884. `tsc` limpio.

Cómo se hizo, distinto de lo escrito:
- **D8 sin función nueva.** La regla única ya existía: `agents.principal_agent_id` / `agent_for_channel`, que es la del turno. La usan ahora `_agent_of`, `agent_channels` y las tarjetas.
- **El destino de los canales del agente** cambió también en `channelsHref(ref, agentId)`, que usan «Guardar y conectar un canal» (`publish-bar`) y el arreglo «canal» de la revisión y de las pruebas (`review-panel`, `tests-box`). La spec (2.7) lo recoge.
- **«Tiene agentes»** llega a la tarjeta como `hasAgents`, desde `agentChoice().total`. Con un solo agente, `agentChoice` devuelve la lista vacía a propósito.
- **T018** está en `whatsapp-connect-063.test.tsx`, porque necesita su propio `useRouter` con `push`.

Pruebas antiguas actualizadas porque fijaban lo que la spec cambia:
- `test_visible_state` (la fila sin configurar ahora lleva su motivo);
- `life-model`, `agent-cards` y `publish-bar` (el destino de los canales);
- `channel-connect` (el texto nuevo, «no responde a nadie»).

---

## Phase 5: User Story 3 — El borrador no se pierde por el formato (Priority: P2)

**Goal**: el constructor pide la salida en JSON, lee bien un JSON válido, distingue «cortado» de «JSON ilegible» y deja el porqué en el registro, sin contenido y sin reintentos.

**Independent Test**: con un modelo de prueba que devuelve JSON roto, el fallo queda clasificado en el registro sin una palabra de la salida. Con el transporte real, la llamada lleva `response_format`, y el registro dice que se pidió.

### Tests for User Story 3 ⚠️

- [x] T026 [P] [US3] Crear `apps/worker/tests/unit/test_063_agent_draft_output.py`, con `complete_factory` y un proveedor de prueba:
  - Con un modelo que lo admite, la llamada lleva `extra={"response_format": {"type": "json_object"}}`; con uno que no, sin `extra`. En los dos casos se registra `builder.model_output json_mode=…`.
  - `finish_reason="length"` → `jobs.agent_draft.unavailable why=truncated`.
  - Un JSON roto → `why=bad_json` con `error`, `pos`, `line`, `col`, `chars`, `finish_reason` y `output_tokens`, y ninguna subcadena de la salida en el registro.
  - Una sola llamada al modelo por intento.

  _Requisitos: 3.1, 3.2, 3.3, 3.4_
- [x] T027 [P] [US3] Crear `apps/worker/tests/unit/test_063_json_mode_reaches_provider.py`, con el patrón de `test_classifier_reaches_the_provider.py`: `LiteLLMProvider` real contra un servidor HTTP local y `LITELLM_LOCAL_MODEL_COST_MAP=True`, en un subproceso.
  - El cuerpo de la petición de `acomplete_detailed` para `openai/gpt-5.6-sol` lleva `response_format`.
  - `supports_json_object` es verdadero para los tres modelos que usa hoy la plataforma.

  _Requisitos: 3.1_
- [x] T028 [P] [US3] Crear `apps/api/tests/unit/test_063_parse_output_detail.py`:
  - Un JSON roto da `BuilderUnavailable("bad_json")` con `detail`, y sin texto de la salida en `str(exc)` ni en `detail`.
  - Un JSON válido que lleva «```» y llaves dentro de una cadena se lee entero, en `parse_output` y en `_json` de `guides/generated.py`.

  _Requisitos: 3.2_
- [x] T029 [P] [US3] En `apps/api/tests/integration/builder/test_agent_draft_job.py`, añadir que un borrador que falla por `bad_json` publica su uso con `source=builder` y no mueve la bolsa del cliente.
  _Requisitos: 3.5_

### Implementation for User Story 3

- [x] T030 [US3] En `apps/worker/src/nexus_worker/runtime/llm.py`:
  - `supports_json_object(model) -> bool`, que pregunta a `litellm.get_supported_openai_params` y da `False` si LiteLLM no conoce el modelo.
  - `LiteLLMProvider.acomplete_detailed(...) -> Completion(text, finish_reason, output_tokens)`, sobre `_raw_complete`.

  _Requisitos: 3.1, 3.2, 3.3_
- [x] T031 [US3] En la API:
  - `apps/api/src/nexus_api/services/builder/agent_draft.py`: `BuilderUnavailable` gana `detail: dict[str, Any] | None`. `parse_output` prueba antes la salida entera y rellena `detail` en `bad_json` con `exc.msg`, `pos`, `lineno`, `colno` y la longitud.
  - `apps/api/src/nexus_api/services/builder/guides/generated.py`: `_json` prueba antes la salida entera.

  _Requisitos: 3.2_
- [x] T032 [US3] En `apps/worker/src/nexus_worker/jobs/handlers/agent_draft.py`, `default_complete`:
  - Usa `acomplete_detailed` con el `extra` de T030 y registra `builder.model_output` con `json_mode`, `finish_reason` y `output_tokens`, sin contenido.
  - Con `finish_reason == "length"` lanza `BuilderUnavailable("truncated")`.
  - El handler registra `detail` en `jobs.agent_draft.unavailable`.
  - Sin reintentos.

  _Requisitos: 3.1, 3.2, 3.3, 3.4_

**Checkpoint**: T026–T029 en verde.

Resultado (2026-11-18): T026–T032 en verde.
- Worker: `test_063_agent_draft_output` (4), `test_builder_call_budget` (5) y `test_063_json_mode_reaches_provider` (1, transporte real y mapa local de LiteLLM: `gpt-5.6-sol`, Sonnet 5.5 y Haiku 5.5 admiten el modo JSON).
- API: `test_063_parse_output_detail`, `test_063_draft_failure_is_named`, `test_agent_draft_job` y `test_builder_guides`, 31.

Cómo se hizo:
- **T029** es un fichero nuevo, `tests/integration/builder/test_063_draft_failure_is_named.py`. Junta el registro con nombre y el cobro en una sola prueba.
- **El handler** lee lo que dejó la última llamada (`last_output(complete)`) para registrarlo junto al fallo, porque `bad_json` salta luego, en la API.

---

## Phase 6: User Story 4 — Ni el constructor ni la plantilla se caen por un nombre (Priority: P2)

**Goal**: un nombre que el cliente dio al constructor no cuenta como «de otro cliente». Lo que el constructor escribe por su cuenta y nombra a otro se quita trozo a trozo. La plantilla nunca da 500.

**Independent Test**: los cuatro casos de `research.md` §3 dan borrador. Una instrucción del modelo que nombra a otro cliente sale sin ese trozo.

### Tests for User Story 4 ⚠️

- [x] T033 [P] [US4] Crear `apps/api/tests/unit/test_063_builder_foreign_names.py`:
  - Los cuatro casos de `research.md` §3 dan borrador.
  - Un nombre ajeno que esté en el nombre del agente, la descripción, la ficha o la guía no da problema.
  - Una sección de instrucciones, un procedimiento, una regla o el objetivo escritos por el modelo con un nombre ajeno que no está en la entrada se quitan, solo ese elemento, y el resto llega.
  - `builder.draft.problems` registra código y ruta, sin el nombre.
  - Si tras quitarlo sigue sin valer, `BuilderUnavailable("invalid_draft")`.

  _Requisitos: 4.1, 4.2, 4.3_
- [x] T034 [P] [US4] Crear `apps/api/tests/integration/builder/test_063_template_named_error.py`: «Desde una plantilla» con un borrador que no se puede sanear responde `422 {"code": "draft_invalid"}`, no 500, y no crea ningún agente.
  _Requisitos: 4.4_
- [x] T035 [P] [US4] En `apps/console/src/components/builder/__tests__/builder-new.test.tsx`:
  - `draft_invalid` enseña «No se pudo crear desde esta plantilla», ofrece «Probar otra plantilla» y «Empezar en blanco», y conserva lo escrito.
  - `builder_unavailable` sigue ofreciendo «Intentar de nuevo», «Desde una plantilla» y «En blanco».

  _Requisitos: 3.4, 4.4_
- [x] T036 [US4] Crear `apps/api/tests/isolation/test_063_builder_foreign_names.py` (D9), con dos clientes del mismo partner:
  - La salida del constructor para A nombra a B sin que B esté en la entrada de A: el AgentSpec guardado de A y la respuesta de la API no llevan el nombre de B.
  - El nombre de B en la descripción de B no exime a A.

  _Requisitos: 4.5_

### Implementation for User Story 4

- [x] T037 [US4] En `apps/api/src/nexus_api/services/builder/agent_draft.py`, `sanitize`:
  - Recibe la guía usada (`guide: ResolvedGuide | None = None`).
  - Quita de `ctx.foreign_names` los nombres que aparecen, con el emparejador del validador, en el nombre, la descripción, `render_facts(facts)` y la guía.
  - Ante un `foreign_text`, quita el elemento de su ruta (`/instructions/sections/N`, `/procedures/N`, `/rules/N`, `/skills/N`, `/identity/goal`) en vez de `rules`.
  - Registra código y ruta, sin el nombre.
  - `build_agent_draft` y `draft_from_template` le pasan su guía (D6).

  _Requisitos: 4.1, 4.2, 4.3_
- [x] T038 [US4] En `apps/api/src/nexus_api/api/console/agent_builder.py`, el camino de plantilla captura `BuilderUnavailable` y responde `_error("draft_invalid", 422)`.
  _Requisitos: 4.4_
- [x] T039 [US4] En la consola:
  - `apps/console/src/components/builder/builder-new.tsx` y `apps/console/src/lib/action-error.ts` tratan `draft_invalid`;
  - textos en `es` y `en` en `apps/console/src/i18n/lanes/builder.ts`;
  - el código va en `apps/console/src/lib/backend/builder-types.ts`.

  _Requisitos: 4.4_

**Checkpoint**: T033–T036 en verde. T036 bloquea el merge.

Resultado (2026-11-18): T033–T039 en verde.
- API: `test_063_builder_foreign_names` (12, junto al validador, la agenda, «solo lo que tenemos» y el banco de evaluación: 91), `test_063_template_named_error` (2) e `isolation/test_063_builder_foreign_names` (1).
- Consola: `builder-new` y `lib`, 173. `tsc` limpio.

Cómo se hizo:
- **La exención** usa `validator.mentions`, el mismo criterio que la guarda.
- **Lo que se quita**, además de lo de la spec: también `voice.tone`, `voice.greeting`, `escalation.message`, `services.faqs` y `connection_requests`, que son todo lo que escribe el modelo.
- **Lo que no cambia:** los demás problemas siguen quitando `rules`, como antes.
- **Vaciar las secciones de instrucciones no deja el borrador inválido**, porque el esquema lo admite. Por eso 4.3 se prueba con un problema que no se puede quitar.
- **El `422 draft_invalid`** lo pinta «Nuevo agente» junto a las plantillas, que siguen abiertas, con «En blanco» a mano.
- **C3** (`builder_unavailable` sigue ofreciendo las alternativas) lo cubría ya «si el borrador no se puede escribir…», en `builder-new.test.tsx`.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T040 [P] Actualizar `docs/agentes.md` en el mismo commit que el código:
  - §1, «Cómo habla»: idiomas, límite y la regla de idioma del turno (último mensaje de sistema, por qué va ahí);
  - §2, el constructor: modo JSON, `truncated`, el detalle del fallo y la regla de los nombres de otros clientes;
  - el error de plantilla `draft_invalid` y el rótulo «Listo · número sin configurar».

  _Requisitos: 1.5, 1.6, 2.6, 3.2, 4.1, 4.4_
- [x] T041 [P] Actualizar `docs/canales.md`: «Configurar» y «No responde a nadie» en Canales del cliente, la conexión que abre la configuración, y la regla del principal (D8).
  _Requisitos: 2.1, 2.2, 2.3, 2.4_
- [x] T042 [P] Llevar los cambios a los contratos de la 047:
  - `specs/047-la-fabrica-de-agentes/contracts/console-api.md`: `audience_mode`, `422 draft_invalid` y la `reason` `unconfigured`, según `contracts/console-api.md` de esta spec;
  - en `specs/047-la-fabrica-de-agentes/spec.md`, una línea «Enmendado por la spec 063» en 15.4, 15.8, 16.1, 25, 26.1, 30.6 y 32.9.

  _Requisitos: 1.6, 2.1, 2.3, 2.6, 2.7, 4.1, 4.4_
- [x] T043 Correr `./scripts/verify.sh lint` y `./scripts/verify.sh js` (mypy `--strict`, consola, `next build`), y después, de una en una, las suites de T001 más las nuevas de esta spec. Anotar el resultado aquí.
  _Requisitos: 1.4, 2.4, 3.1, 4.5_

  Resultado (2026-11-18, base `nexus_test_063`, suites de una en una):
  - `verify.sh lint`: ruff limpio en todo. `mypy --strict` también, tras corregir ocho errores de tipos de esta spec (API: 599 ficheros, worker: 146).
  - `verify.sh js`: consola, `@nexus/ui`, companion-ui, escritorio y `next build` en verde.
  - **El panel** (`apps/admin`) falló en typecheck y vitest solo porque el worktree era nuevo: sus paquetes `@nexus/ucm-*` se compilan en el `prebuild` de `next build`, que va después. Repetidos tras compilarlos: `tsc` limpio y 634 en verde. Esta spec no toca el panel.
  - Python:
    - worker tocadas, 65;
    - API unitarias tocadas, 289;
    - API integración tocadas (`builder/` y `channels/` enteras), 376;
    - **`tests/isolation/` entera, 3962** (1 `skipped` que ya estaba).

  Segunda ronda, tras la revisión final (2026-11-18):
  - **Arreglos:**
    - el resumen de canales da la audiencia **efectiva** (`channel_audience`), con una prueba para Instagram;
    - `client_overview` usa el principal con el marcado por defecto primero;
    - `_agent_of` vuelve a filtrar por el tenant del canal.
  - **Ejecuciones:**
    - API unitarias enteras: 3314 en verde (690 `skipped` que ya estaban). Falló `test_endpoint_console_agent_tools`, que fijaba que los ajustes antiguos cambian los idiomas; actualizada a 1.6, 12 en verde.
    - Worker unitarias enteras: 1028.
    - Integración (`test_console_draft_diff`, `test_console_capabilities`, `test_recompile_keeps_agent_layer`, `test_dispatcher_058_audience_first`, `test_063_channel_reach`, `channels/`, `clients/`, `agents/`): 291.
    - Aislamiento 058 y 063: 3.
  - **Lo que no cambió:**
    - Archivar el principal no rechaza un destino para un número sin agente: `archive` solo pide y aplica los de los números asignados. En un cliente antiguo sin agente marcado, el diálogo pediría un destino para el número sin agente que luego no se aplica. Queda anotado.
    - Una guía generada cortada (`truncated`) cae a la genérica, porque `generate` captura cualquier fallo.
    - El copiloto conserva el límite al cambiar el trato: copia `voice` entera.
- [ ] T044 Después de fusionar en `develop`, la comprobación en staging de `quickstart.md`, y anotar aquí el resultado:
  - idioma: los casos de CE-001, incluido el prompt con «Never answer in English»;
  - el probador;
  - el canal, el estado del agente y a dónde lleva su tarjeta;
  - el borrador;
  - la plantilla.

  _Requisitos: 1.1, 1.2, 1.4, 1.5, 2.1, 2.3, 2.6, 2.7, 3.1, 4.4_
- [ ] T045 Después del paso a `main`, vigilar durante dos semanas `jobs.agent_draft.unavailable`, `builder.model_output json_mode` y los `500` de `POST …/agents/draft-jobs` en prod (CE-004, CE-005). Cerrar la nota de KB `bugs/2026-11-18-quejas-partners-prod` con el resultado.
  _Requisitos: 3.1, 3.2, 4.4_

---

## Dependencies & Execution Order

- **T001** va antes que todo.
- **US1 (T002–T014), US2 (T015–T025), US3 (T026–T032) y US4 (T033–T039)** son
  independientes entre sí. US3 y US4 comparten `agent_draft.py`, pero en funciones
  distintas: T031 toca `parse_output` y `BuilderUnavailable`, y T037 toca `sanitize`.
- Dentro de cada historia, primero los tests, en rojo, y luego la implementación.
  - **US1:** T007 antes que T008. T009 antes que T010 y T011.
  - **US2:** T022 antes que T025.
  - **US3:** T030 antes que T032.
- **Polish:**
  - T040–T042 cuando estén las historias que documentan.
  - T043 al final del código.
  - T044 tras desplegar en staging.
  - T045 tras el paso a producción.

## Parallel Example

```text
# Los rojos de las cuatro historias, a la vez (ficheros distintos):
T002 test_063_language_rule.py      T015 test_063_channel_reach.py
T003 test_063_language_policy.py    T017 channel-card.test.tsx
T004 test_063_voice_limit.py        T026 test_063_agent_draft_output.py
T006 block-editor-voice.test.tsx    T033 test_063_builder_foreign_names.py
```

Las suites de pytest que comparten base se **ejecutan** de una en una, aunque se
escriban a la vez.

## Implementation Strategy

1. **MVP: US1, y dentro de ella T002, T007 y T008.** Por sí solas arreglan la queja del
   idioma para todos los agentes publicados, porque el resto de US1 es el límite y el
   sitio único donde se editan los idiomas. Se puede desplegar sola.
2. **US2:** lo siguiente. Un número que no responde a nadie y que el partner no sabe
   arreglar es la otra queja P1.
3. **US3 y US4:** pueden ir juntas en un segundo PR. Comparten fichero y flujo.
4. Nada llega a `main` sin T043 en verde y T036 en verde.
