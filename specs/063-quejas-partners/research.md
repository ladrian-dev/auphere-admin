# Research — 063, las quejas de los partners del 2026-11-18

Evidencia y reproducciones. La spec dice el qué; aquí van el dónde y las pruebas.
Todo lo que viene de producción se leyó con autorización de Luis (2026-11-18), en
modo solo lectura y solo de `estetica-spa-demo`, sin teléfonos ni textos de
clientes finales.

## 0. Paridad entre develop/staging y prod

- `main` contiene todo `develop`. Tras el PR 28, `develop` es igual a `main`
  (`2cc44b30`), así que el arreglo de la spec 062 ya está también en staging.
- La consola de prod está en el último commit de `main` (Vercel, `auphere-console`).
- Ninguna de las cuatro quejas es de despliegue: las cuatro se reproducen igual en
  staging.

## 1. El idioma

### Dónde se fija el español

| Sitio | Qué hace |
|---|---|
| `apps/api/src/nexus_api/services/agent_console_policy.py:78-88` | `LanguagesPolicy`: `primary="es"` y `allowed=[]` por defecto. El validador mete el principal en la lista y la deja en `["es"]`. |
| `agent_console_policy.py:253-257` | Lo que va en cada turno: «Languages: reply in es by default; allowed: es. If the customer writes in an allowed language, answer in it; otherwise use the default.» |
| `apps/api/src/nexus_api/api/console/agent_spec_drafts.py:114-131` (`_sync_disclosure`) | Al decidir el aviso de IA, que es obligatorio para publicar (047, 16.6), se crea `policies.console`. Desde entonces la política existe con los idiomas por defecto. |
| `apps/worker/src/nexus_worker/runtime/console_context.py:133-157` | Pinta el bloque solo si hay `policies.console`. Sin política, no hay línea de idioma. |
| `apps/worker/src/nexus_worker/runtime/pipeline.py:1602` | El bloque entra en cada turno, detrás del prompt del agente. Ese orden es el que hace que la regla del turno mande sobre el prompt. |
| `apps/api/src/nexus_api/services/agent_spec/compiler.py:108-111` | Compila «- Idiomas: es (principal), …» en el prompt a partir de `voice.languages`. Esa lista no llega a la política del turno. |
| `apps/api/src/nexus_api/services/builder/agent_draft.py:675` | El constructor pone `["es"]` si el modelo no dice otra cosa. |
| `apps/api/src/nexus_api/services/templating/seeds/*.yaml` | Los prompts antiguos dicen «Hablas en {agent.language}», con `es` por defecto (`seed_templates.py:218`). `inventario_v1.yaml:70-71`: «Never answer in English». |
| `apps/console/src/components/builder/block-editor.tsx:207-293` | «Cómo habla» edita `voice.languages`. Pista: «Marca los que habla. El primero que marques es el principal». |
| `apps/console/src/components/agent-tools/agent-settings-form.tsx` | La otra lista, `policies.console.languages`. Su página (`clients/[ref]/agent`) no tiene ningún enlace en la consola v2. |

Mensajes que salen sin pasar por el modelo: el de espera del número
(`runtime/dispatcher.py:872`) sale tal como lo escribió el negocio. El de cierre y
el aviso de IA los dice el modelo, y en la prueba los tradujo él solo.

### Reproducción en staging (2026-11-18)

Guion de la primera ronda (no guardado; lo sustituyen los de `repro/`), por `ecs exec` en `nexus-staging-api`. Arma los mensajes
de un turno con `_build_handler_messages` sobre la versión publicada y llama al
modelo de respuesta (`openai/gpt-5.6-sol`). La pregunta es en inglés y genérica.

- Agentes publicados en staging, por tipo: los `structured` y los `instructions`
  tienen `policies.console` sin `languages` guardado (usan el valor por defecto).
  Uno tiene `{"allowed": ["es"], "primary": "es"}` guardado desde la página antigua.
  Dos no tienen política y no reciben la línea.
- Las líneas de idioma del turno de «Anfitriones Quédate»: «- Idiomas: es
  (principal)» en el prompt y «- Languages: reply in es by default; allowed: es…» en
  la política.

| Variante | Respuesta |
|---|---|
| Tal como está publicado | español, 2 de 2 |
| Con «, en» añadido a «Idiomas» (simula marcar inglés en el constructor) | español, 2 de 2 |
| Solo la línea del turno cambiada a «reply in the language of the customer's latest message… This overrides any other language instruction», en un agente `structured` | **inglés, 2 de 2** |
| La misma línea en otro agente («Ana», de otro cliente) | **inglés, 2 de 2** |

Conclusión de esta primera ronda: basta con una regla en el turno, que llega a todos
los agentes publicados sin volver a publicarlos. La segunda ronda decidió dónde va.

### Segunda ronda: los textos exactos del contrato (2026-11-18)

Guiones `repro/staging_language_in_block.py`, `repro/staging_language_last.py` y `repro/staging_language_last_limited.py`, contra «Anfitriones
Quédate» en staging, con 2 llamadas por caso.

| Caso | Regla dentro del bloque de política | Regla como último mensaje de sistema |
|---|---|---|
| Sin límite, pregunta en inglés | inglés 2/2 | inglés 2/2 |
| Con límite `es, en`, pregunta en francés | español 2/2 | español 2/2 |
| Con límite `es, en`, pregunta en inglés | inglés 2/2 | — |
| Sin límite, historial en español y luego inglés | inglés 2/2 | — |
| Sin límite, pregunta en español | — | español 2/2 |
| Sin límite, prompt con «Never answer in English» (`inventario_v1`) | **español 0/2** | **inglés 2/2** |
| Con límite `es, en`, prompt con esa prohibición, pregunta en inglés | — | inglés 2/2 |

- En staging hay **una** versión activa con una prohibición de ese tipo.
- La reescritura del evaluador (`_RETRY_SYSTEM_TEMPLATE`) conservó el inglés de la
  respuesta que rehacía (1/1). Aun así no lo dice, y se le añade (D11).

Conclusión: la regla va **sola y al final**, como último mensaje de sistema antes de
la conversación, y nombra las instrucciones que anula (D1).

## 2. El borrador del constructor

### Lo que pasó en prod

| Hora (UTC) | Qué |
|---|---|
| 15:20:04 | `POST …/agents/draft-jobs` (job `c73c2dfb`) |
| 15:20:53 | `llm.call_complete` `openai/gpt-5.6-sol`, `prompt_tokens=4940`, `completion_tokens=5264` → `jobs.agent_draft.unavailable why=bad_json cause=JSONDecodeError` |
| 15:25:02 | otro intento (job `f24310fb`), la misma entrada (`same_input=True`) |
| 15:25:50 | `prompt_tokens=4940`, `completion_tokens=5216` → `bad_json` otra vez |
| 15:28:39 | tercer `draft-jobs`, desde plantilla → nace «Ana» (`49081fd9`) |

Los dos `usage.published` del constructor van en `source=builder`: la partida
«Construcción y pruebas» del partner, nunca la bolsa del cliente
(`apps/worker/src/nexus_worker/metering/collector.py:81-88`). Al cliente no se le
cobró nada.

### Por qué no dice nada más

- `apps/worker/src/nexus_worker/jobs/handlers/agent_draft.py:69-87`. La llamada va
  sin `response_format` y sin reintentos, por decisión: repetir paga otra vez.
- `apps/api/src/nexus_api/services/builder/agent_draft.py:401-417` (`parse_output`).
  Busca un bloque cercado y luego cuenta del primer `{` al último `}`. Si
  `json.loads` falla, lanza `BuilderUnavailable("bad_json")`. No se guarda ni la
  posición, ni el `finish_reason`, ni la salida.
- `apps/worker/src/nexus_worker/runtime/llm.py:1395-1408`. `extra` pasa tal cual a
  LiteLLM, así que `response_format` se puede pedir sin tocar el proveedor. La ruta
  con salto ya lo hace según las capacidades del despliegue (`llm.py:608-619`).

### Repetición con la entrada real (tarea suelta del `runner` de prod)

Guion `r063_replay.py`, de solo lectura, fuera de un turno (`record_llm_usage` no
factura). La entrada: nombre de 3 caracteres y descripción de 184, sin comillas,
llaves ni saltos. La ficha tiene 4805 caracteres, también sin comillas ni llaves.

| Llamada | Modo JSON | `finish` | Tokens de salida (razonamiento) | ¿Se lee? |
|---|---|---|---|---|
| 0 | no | `stop` | 5807 (2324) | sí |
| 1 | no | `stop` | 5642 (1877) | sí |
| 2 | **sí** | `stop` | 5385 (1917) | sí |

La entrada de hoy da 4924 tokens frente a los 4940 de las 15:20. La guía del
cliente cambió después (hoy es la de la plantilla). No se puede saber con qué parte
de la salida falló el JSON, porque ni el proveedor (retención cero) ni nosotros la
guardamos. El fallo es intermitente. El modo JSON funciona con este modelo y
este prompt, sin coste extra.

## 3. Nombres de otros clientes y la plantilla

### Lo que pasó en prod

Cliente `fulano` (partner `auphere-acme`), con el usuario de Luis, a las 15:35:13,
15:35:28 y 15:35:53. Tres `POST …/agents/draft-jobs` desde plantilla:
`builder.draft.problems codes=["foreign_text"]` y **500 Internal Server Error** las
tres veces.

### La cadena

1. `apps/api/src/nexus_api/services/agent_spec/validator.py:542-556`. Los nombres
   «de otro cliente» son los `client_name` de los demás clientes del partner.
2. `validator.py:406-418`. Busca cada nombre de 6 o más letras, como palabra entera
   y sin distinguir mayúsculas, en **todo** el texto del borrador: también en
   `identity.description`, que escribió el partner, y en lo que viene de la guía.
3. `agent_draft.py:728-736`. Ante un problema en `/rules/` o en `/instructions/`,
   quita `rules`, incluso cuando el problema está en una instrucción. Vuelve a
   validar, y si sigue fallando lanza `BuilderUnavailable("invalid_draft")`.
4. `apps/api/src/nexus_api/api/console/agent_builder.py:299-316`. El camino de
   plantilla captura `SeedTemplateNotFound`, `FactsUnavailable`, `DraftInputInvalid`
   y `AgentError`, pero no `BuilderUnavailable`, así que sale como 500.

### Reproducción en local (`repro/local_foreign_names.py`, sin base)

| Caso | Resultado |
|---|---|
| Otro cliente se llama como este («Fulano» / «Fulano») | borrador |
| El nombre de otro cliente es una palabra corriente («Peluquería») y la descripción la usa | **`invalid_draft`** |
| El nombre propio contiene el de otro («Estetica & Spa demo» / «Estetica & Spa») | borrador |
| Nombres ajenos al texto | borrador |

El nombre exacto que disparó el fallo en `auphere-acme` no se leyó (no estaba
autorizado), pero el mecanismo es el mismo.

## 4. La configuración del canal

### Lectura de prod (`estetica-spa-demo`)

- Agente «Ana» (`49081fd9`): `is_default=True`, publicado, creado a las 15:28:39.
- Canal de WhatsApp `518d01c0`: `agent_id=None`, `audience_mode=unset` («Sin
  configurar»), creado a las 16:00:38 desde la página Canales del cliente.

El número sí sale en la pestaña Canales de Ana, pero el partner nunca fue allí. Lo
conectó desde Cliente → Canales y recargó esa página hasta las 16:11. Con la
audiencia en «Sin configurar», el número **no responde a nadie** (047, 32.9).

### La misma ruta en los dos entornos (Chrome de Luis, solo mirando)

Cliente → Agentes → el agente:

| | Staging (Meta Review Demo → Ava) | Prod (Estetica & Spa- demo → Ana) |
|---|---|---|
| Estado en la tarjeta | «Serving» | «Listo · sin canal» |
| Línea de canales en la tarjeta | «No channel» | «Sin canal» |
| Al pulsar la tarjeta | `/clients/meta-review-demo/agents/<id>`, en Rendimiento | **`/clients/estetica-spa-demo/channels`**, la página Canales del cliente |

- La página del agente es igual en los dos entornos. A la de Ana se llega por URL, y
  su pestaña Canales enseña el número con ⋯ → Configuración.
- La causa está en `apps/console/src/components/builder/life-model.ts:37`, `cardHref`:
  con `opens == "channels"` devuelve `channelsHref(refId)`
  (`quality-model.ts:234`), que es la página del cliente.
- `opens` lo decide `agents_list.py:64-69`: `ready_no_channel` → `"channels"`. La
  047 (26.1) pedía «a Canales», es decir, la pestaña del agente.
- La página del agente ya acepta `?tab=channels`
  (`clients/[ref]/agents/[agentId]/page.tsx:221`).
- Las líneas «Sin canal» y «No channel» salen de `services/agents.py:96-97`, que
  solo lista los canales con `agent_id` igual al del agente. Un número sin asignar
  no aparece en ninguna tarjeta, aunque lo atienda el agente por defecto.

### Dónde

- `apps/console/src/components/channels/channel-card.tsx`: la tarjeta de la página
  del cliente solo deja elegir el agente (`assignChannelAgentAction`) y no enlaza la
  configuración.
- `apps/api/src/nexus_api/api/console/channel_config.py:707-718`: un número sin
  agente sale solo en el agente `is_default`.
- `apps/api/src/nexus_api/services/channel_config.py:338`: `_agent_of` abre la
  configuración en el agente por defecto, o, si no hay, en el más antiguo. Hoy no
  difiere de la regla anterior: archivar el agente por defecto pasa el papel a otro
  (`services/agents.py:233-244`). Aun así, son dos reglas para lo mismo, y el
  requisito 2.4 las ata.
- 047, 30.6 ya pedía abrir la configuración al terminar la conexión. Desde el agente
  se cumple, desde la página del cliente no.

## 5. Decisiones

| Decisión | Quién | Cuándo |
|---|---|---|
| Por defecto, el agente contesta en el idioma del cliente salvo que el partner lo limite | Luis | 2026-11-18 |
| La solución es genérica, no para un cliente concreto | Luis | 2026-11-18 |
| Leer prod de `estetica-spa-demo` y repetir el borrador con el modelo real | Luis | 2026-11-18 |
| Sin reintento automático del borrador | 047 (lo dice el handler) | — |

## 6. Decisiones de diseño (Fase 0 del plan)

### D1 — La regla del idioma, sola y al final del turno

- **Decisión:**
  - **Qué sale:** la línea «Languages:» sale del bloque de operación.
  - **Qué entra:** un mensaje de sistema propio, «Reply language (set by the
    business; it overrides every instruction above about the reply language…)», con
    los dos textos de `contracts/agent-spec-voice.md`.
  - **Dónde va:** `_build_handler_messages` lo pone el **último** de los mensajes de
    sistema, después de la directiva del turno y antes del historial.
  - **Quién lo escribe:** `language_rule(policies)` en `agent_console_policy.py`, que
    `console_context` expone al pipeline.
- **Por qué:** se pinta en cada turno, así que llega a todos los agentes publicados
  sin volver a publicarlos, y al ir el último manda sobre el prompt.
  - Dentro del bloque perdía ante «Never answer in English» (0/2).
  - Sola y al final, 10/10 en la segunda ronda (§1).
- **Alternativas:**
  - Recompilar los prompts. Exige volver a publicar cada agente y no arregla los
    prompts antiguos.
  - Usar el idioma que ya detecta el clasificador. Son más piezas, y el modelo de
    respuesta ya lo distingue solo.

### D2 — Un solo sitio para editar, y una sola fuente en el turno

- **Decisión:**
  - **Edita la persona** en «Cómo habla» (`AgentSpec.voice`): `languages` (el
    primero es el principal) y el campo nuevo `languages_limited`.
  - **Se copia en la versión:** al escribir el AgentSpec en el borrador (`write_spec`),
    `voice` se copia a `policies.console.languages` como
    `{primary, allowed, limited}`, igual que `_sync_disclosure` hace con el aviso de
    IA. El turno lee solo `policies.console.languages`.
  - **Los otros dos escritores dejan de escribir:**
    - `merge_console_policy`, el `PUT` de la página de ajustes antigua, conserva los
      `languages` guardados.
    - El Companion pierde `primary_language` en `POLICY_FIELDS`.
- **Por qué:** el turno ya lee `policies`. Copiar al guardar es el patrón que ya
  existe, y el turno no necesita el AgentSpec.
- **Alternativas:**
  - Que el turno lea `spec.voice`: habría dos fuentes según el modo del agente.
  - Una migración que rellene `languages` en las versiones publicadas: las versiones
    no se reescriben.
- **Consecuencia aceptada:** un agente publicado antes, con un principal distinto de
  `es`, contesta igualmente en el idioma del cliente. Solo usa `es` donde no sepa el
  idioma, hasta su próxima publicación.

### D3 — `limited`, apagado por defecto

- **Decisión:** `LanguagesPolicy` gana `limited: bool = False` y `Voice` gana
  `languages_limited: bool | None = None`.
- **Por qué:** cumple 1.7 sin migración. Una lista guardada sin el campo
  (`{"allowed": ["es"], "primary": "es"}`, desde la página antigua) se lee sin
  límite, que es lo que decidió Luis.

### D4 — La regla de idioma va siempre

- **Decisión:** `language_rule` trabaja con `policies.console.languages` o, si la
  versión no tiene política, con los valores por defecto (sin límite, principal
  `es`). La regla va en todos los turnos. El bloque de operación no cambia en lo
  demás.
- **Por qué:** sin política no habría ninguna regla de idioma, y el prompt antiguo
  diría «Hablas en es» (1.4). En staging hay dos agentes publicados así.

### D5 — El borrador: modo JSON, «cortado» y detalle sin contenido

- **Decisión:**
  - **Modo JSON:** el `complete` del constructor pasa
    `extra={"response_format": {"type": "json_object"}}` si
    `litellm.get_supported_openai_params(model)` lo incluye. Lo comprueba
    `supports_json_object(model)` en `runtime/llm.py`. Los dos prompts que pasan por
    ese `complete` (el borrador y la guía generada) ya piden JSON, como exige el modo.
  - **Cómo terminó el modelo:** un método público nuevo, `acomplete_detailed`, devuelve
    `(text, finish_reason, output_tokens)`. Con `finish_reason == "length"` salta
    `BuilderUnavailable("truncated")`.
  - **El detalle del fallo:** `parse_output` adjunta a `BuilderUnavailable` un
    `detail` con `{error: exc.msg, pos, line, col, chars}`. El handler lo registra en
    `jobs.agent_draft.unavailable`, junto a `finish_reason` y `output_tokens`.
    `exc.msg` es el texto fijo de `json`, del tipo «Expecting ',' delimiter», sin nada
    de la salida.
  - **Leer la salida entera primero:** `parse_output`, y también `_json` de la guía
    generada, prueban `json.loads` sobre la salida entera antes de buscar un bloque
    cercado o la primera y la última llave. Hoy, un JSON válido que lleva «```» dentro
    de una cadena se recorta mal, y el modo JSON no evitaría ese fallo.
  - **Se registra si se pidió el modo JSON**, en cada llamada del constructor
    (`builder.model_output json_mode=…`). Si el mapa de LiteLLM de la imagen no
    conociera el modelo, el arreglo estaría apagado sin que nadie lo supiera, y
    CE-004 no probaría nada.
- **Por qué:** el proveedor garantiza que la sintaxis es válida, y se probó con la
  entrada real (§2). Si llega otro fallo, el registro dirá cuál fue.
- **Alternativas:**
  - `json_schema` estricto: la salida del borrador es grande y laxa, y bastaría un
    campo mal tipado para que fallara entera.
  - `json-repair`: una dependencia nueva que tapa el fallo en vez de evitarlo.
  - Reintentar: la 047 lo descarta, porque se paga dos veces.
- **Comprobación del modelo:** con el mapa local de LiteLLM y el transporte real,
  en un subproceso (memoria del 2026-11-05). `get_supported_openai_params` da
  `response_format` para `openai/gpt-5.6-sol`, `anthropic/claude-sonnet-5-5` y
  `anthropic/claude-haiku-5-5`.

### D6 — Los nombres de otros clientes

- **Decisión:**
  - **Qué se exime:** `sanitize` recibe también la guía usada y filtra
    `ctx.foreign_names` antes de validar. Quita los nombres que aparecen, con el
    mismo emparejador del validador, en el nombre del agente, la descripción, la
    ficha (`render_facts`) o el texto de la guía o plantilla. La exención vale solo
    para ese borrador.
  - **Qué se quita:** con un `foreign_text` en una ruta del modelo (`/instructions/
    sections/N`, `/procedures/N`, `/rules/N`, `/skills/N`, `/identity/goal`, …) se
    quita **ese elemento** y no siempre `rules`, que es el fallo de hoy. Luego se
    valida otra vez.
  - **Qué se registra:** `builder.draft.problems` anota código y ruta, sin el nombre.
  - **El error de plantilla:** `agent_builder.py` captura `BuilderUnavailable` en el
    camino de plantilla y responde `422 draft_invalid`. La consola lo pinta con
    nombre: «No se pudo crear desde esta plantilla», con «Probar otra plantilla» y
    «Empezar en blanco».
- **Por qué:** el constructor solo recibe datos de este cliente y guías de Auphere.
  Un nombre que viene en su entrada no puede ser una fuga. La guarda sigue
  cubriendo lo que importa: que el modelo invente o arrastre el nombre de otro
  cliente.
- **Fuera:** las propuestas del constructor sobre un agente ya creado (`agent_spec_patch`).
  Pasan por el mismo validador, pero nadie se ha quejado, y su base es el borrador
  del propio agente. Queda anotado.

### D7 — El número, desde la página del cliente

- **Decisión:**
  - **El resumen trae la audiencia:** `GET /console/clients/{ref}/channels/overview`
    añade `audience_mode` a cada canal. Es la audiencia **efectiva**
    (`client_overview.channel_audience`), no la columna tal cual: Instagram,
    Messenger y un número que no es estricto guardan `unset` y responden con la del
    agente publicado (lo encontró la revisión final).
  - **La tarjeta** (`channel-card.tsx`) gana «Configurar», que lleva a
    `/clients/{ref}/channels/{id}`. Esa ruta ya existe y redirige a la configuración
    dentro del agente.
  - **Con `audience_mode == "unset"`**, la tarjeta dice «No responde a nadie» y su
    acción principal es «Decidir a quién responde», hacia el mismo enlace.
  - **Sin agentes en el cliente**, «Necesita un agente que lo atienda», con un enlace
    a crear uno.
  - **Al terminar la conexión** (`whatsapp-connect.tsx`), la consola navega a ese
    enlace con el `channel_id` que devuelve la conexión. Si antes ofrece el catálogo,
    navega cuando se cierra la oferta.
- **Por qué:** reutiliza la ruta y la página que ya funcionan en prod (comprobado en
  el Chrome de Luis: Ana → Canales → ⋯ → Configuración).
- **El mismo texto en los dos sitios:** la pestaña del agente dice hoy «sin
  configurar: todavía no responde» (`channels-proto.row.unset`). Pasa a «sin
  configurar: no responde a nadie», igual que la tarjeta del cliente (2.3).

### D8 — Una sola regla para «qué agente atiende un número»

- **Decisión:** la regla que ya existe y usa el turno, `agents.principal_agent_id` / `agent_for_channel`, en las dos partes (en la implementación no hizo falta una función nueva, que el plan llamaba `serving_agent`):
  - **Qué devuelve:** el agente asignado; si no hay, el vivo marcado por defecto; y si
    ninguno lo está, el vivo más antiguo.
  - **Quién la usa:** `_agent_of` (la página del canal) y `agent_channels` (la pestaña
    Canales de cada agente). Esta última adopta la caída al más antiguo, que antes
    no tenía.
- **Por qué:** `agents.py` admite clientes con agentes vivos y ninguno marcado («sin
  marca, manda el más antiguo»). Quitar la caída dejaría sus números sin pestaña.
  - En staging no hay ninguno: 0 clientes así, con 68 números sin agente asignado.
  - En prod no se ha leído.

  Ir en esta dirección no rompe nada en ninguno de los dos entornos.

### D9 — La prueba de aislamiento

- **Decisión:** `apps/api/tests/isolation/test_063_builder_foreign_names.py`, con dos
  clientes del mismo partner.
  - La salida del constructor para A nombra a B, sin que B esté en la entrada de A:
    el borrador de A llega sin ese trozo, y ni el AgentSpec guardado ni la respuesta
    de la API llevan el nombre.
  - El nombre de B en la descripción de B no exime a A.

### D10 — «Listo · sin canal» cuando el número está sin configurar

- **Decisión:**
  - **El dato:** `visible_state` (`services/agent_lifecycle.py`) sigue dando
    `ready_no_channel` cuando ningún número responde. Si alguno está «unconfigured»,
    le pone `reason="unconfigured"`.
  - **El rótulo:** la consola pinta «Listo · número sin configurar» y no «Listo · sin
    canal».
  - **Lo que no cambia:** no hay código de estado nuevo, así que los recuentos y la
    atención no se tocan.
- **Por qué:** en prod, la cabecera de Ana dice «sin canal» y su pestaña Canales
  enseña el número. Es la misma confusión de la queja 4 (requisito 2.6).

### D11 — La reescritura conserva el idioma

- **Decisión:** `_RETRY_SYSTEM_TEMPLATE` añade «Keep the language of the reply you are
  rewriting.».
- **Por qué:** es el otro camino por el que un texto del modelo llega al cliente.
  - Los únicos que hay son el bucle del turno (`pipeline.py:1952`) y esta reescritura
    (`pipeline.py:3062`).
  - El consejo de escalado del router (`complete_structured`) no llega al cliente.

### D12 — La tarjeta del agente lleva a su pestaña Canales

- **Decisión:**
  - `cardHref` lleva `opens == "channels"` a `agentHref(ref, id) + "?tab=channels"`.
  - `channelsHref(ref, agentId?)` (`quality-model.ts`) hace lo mismo con agente. Lo
    usan «Guardar y conectar un canal» cuando no hay pestaña a mano
    (`publish-bar.tsx`) y el arreglo «canal» de la revisión y de las pruebas
    (`reviewFixLink`), que llevaban a Canales del cliente. Su propio comentario
    decía: «Cuando el agente tenga su propia pestaña de canales (historia 10),
    cambia aquí».
  - La lista de canales de cada agente en las tarjetas (`services/agents.py`) usa
    la regla del principal (D8): un número sin asignar sale en el agente que lo atiende.
- **Por qué:** es la causa del bucle de la queja 4 y lo que pedía la 047 (26.1).
  Con este cambio, el partner llega a la pestaña donde conecta el número dentro del
  agente (047, 30.1), así que el número nace asignado a él.

