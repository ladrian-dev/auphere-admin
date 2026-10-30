# Modelos y router — spec viva

> Qué existe hoy del catálogo de modelos, el router por tarea y la certificación
> (spec 047, ola 6: historia 12; requisitos 39 a 42). El contrato es
> [`specs/047-la-fabrica-de-agentes/contracts/router-and-catalog.md`](../specs/047-la-fabrica-de-agentes/contracts/router-and-catalog.md);
> las decisiones, `research.md` D19 a D24. Se actualiza en el mismo commit que
> cambia el comportamiento (constitución §IX).

## En una frase

Cada llamada a un modelo lleva una **tarea**; para cada tarea, el router elige
el **despliegue certificado más barato** que cumple lo que exige el cliente, con
dos alternativas en otros proveedores, y lo deja escrito. LiteLLM solo
transporta.

## Las piezas

| Pieza | Dónde | Qué hace |
|---|---|---|
| Catálogo | `model_profiles` (una fila = un despliegue), `model_prices`, `router_taxonomy`, `router_profiles`, `model_task_certifications` | Datos de plataforma, sin RLS. Migración 0180 |
| Por cliente | `agent_model_certifications`, `router_anomalies` | RLS forzada, FK compuestas |
| Lectura tipada, activación y filtro duro | `api/services/router_catalog.py` | `load_snapshot`, `Deployment`, `activation_problems`, `hard_filter` |
| La oferta y lo ejecutable | `api/core/respond_catalog.py` | Vistas de `model_profiles` (ya no listas en el código) |
| El router | `wk/runtime/model_resolver.py` | `chain_for(task, profile, ctx)`, afinidad, escalado, límites, clasificación tipada; `get_catalog_snapshot()` (el catálogo en memoria, 5 minutos como mucho; `invalidate_catalog()` lo fuerza) |
| El transporte | `wk/runtime/llm.py` | `routed(hop)`, argumentos por capacidad, `complete_routed` / `respond_routed` / `complete_structured`, enfriamientos, `llm.route_decision` |
| El más barato (presupuesto) | `wk/metering/pricing.py::cheapest_model` | Con filtros de estado, herramientas, lista permitida y residencia |
| Certificación | `api/services/certification.py`, `wk/certification/` | Batería v1, métricas, almacenamiento, caducidades, por agente, en segundo plano |
| El juez | `wk/runtime/grading_policy.py` (`judge_route`, muestreo del perfil), `wk/guardrails/outcome_grader.py` (`judge_for`) | Siempre de otra familia |
| El router en el grafo | `wk/runtime/pipeline.py` (`_classify_routed`, `_conversation_route`, `_escalate_if_signalled`) | Quién va por el router, el clasificador tipado, el escalado en subllamada, la afinidad en el hilo |
| La política del agente | `api/services/router_catalog.py` (`ModelPolicy`, `model_policy_of`, `default_model_policy`) | Dónde vive hasta el AgentSpec y con qué nace un agente |
| El ciclo de vida | `api/services/model_lifecycle.py`, cron `wk/streams/model_lifecycle_cron.py` | Retiradas, precios con vigencia, «No disponible» |
| El panel de operador | `api/api/admin/{models_catalog,router_policies,certifications}.py`, `adm/{models,router,certifications}/` | [admin.md](admin.md#modelos-router-y-certificaciones-spec-047) |

## La taxonomía (v1)

Quince tareas, sembradas por la 0180 y comparadas con el contrato §1 en
`apps/worker/tests/unit/test_router_policy.py`. Dos son **de conversación**
(`answer` y `tool_turn`): solo ellas fijan modelo por conversación, solo ellas
piden la certificación del agente y solo a ellas se aplica «Fijar un modelo».
Una tarea nueva es una versión nueva de la taxonomía, con su batería.

Una llamada **sin tarea** falla en los tests (`LiteLLMProvider(require_task=True)`
lanza `MissingTask` sin salir al proveedor) y en producción se registra
`llm.task_missing` y la llamada sale. Las llamadas que todavía no van por el
router reciben su tarea por el rol (`llm.TASK_BY_ROLE`: `classify` → `classify`,
`grader` → `judge`, `companion` → `build`, las intenciones del grafo →
`tool_turn` con herramientas y `answer` sin ellas), así que **todo** lo que gasta
llega al medidor con su tarea, y lo enrutado, también con su decisión
(`usage_records.task` y `route_decision_id`).

## Un despliegue y su activación

Una fila de `model_profiles` es un modelo en un proveedor y una ruta. Su clave es
`model_id` (el id de LiteLLM tal cual): la misma cadena que va a
`usage_records.model` y la que guarda `model_policy.deployment` en el AgentSpec.
`Deployment.to_contract()` devuelve la forma del contrato §2.

Las **capacidades** viven en `capabilities` (jsonb). Una capacidad que nadie
declaró es una que no se tiene. Las filas de antes de la 0180 (`{}`) conservan lo
que ya se sabía por las columnas viejas (`supports_tools`, `supports_vision`,
`max_context`, `cache_min_tokens`). Además de las del contrato, el router lee:
`structured_outputs`, `embeddings`, `rerank` (necesidades de la taxonomía),
`tier` (`basic`, `medium`, `top`: la gama del escalado), `quantization` (caduca
la certificación), `cache_key` y `cache_ttl_s` (la clave y la duración de la
caché del proveedor), `provider_jurisdiction` (`eu` para la restricción soberana)
y `cooldown_s` (el enfriamiento tras un fallo, 60 s si no se dice).

**Activar** (`router_catalog.activate_deployment`) exige, y si falta algo lo dice
todo de una vez (`ActivationRejected.missing`, con el texto de
`ACTIVATION_MESSAGES`):

- retención cero, con DPA y diciendo cómo se fuerza (`retention_how`);
- el proveedor dado de alta como subprocesador;
- una licencia leída entera (enlace y fecha) y no excluida: Llama 4,
  Qwen3.8-Flash-Next y cualquier AGPL;
- los tres pesos del medidor;
- certificación por clase en alguna tarea.

## Los perfiles

`router_profiles` guarda la política por tarea de cada perfil (`auto`,
`economy`, `balanced`, `max` y `platform`), versionada, con quién y por qué. Por
tarea: umbral de calidad, techo de coste por llamada, hasta qué gama escala, nivel
de razonamiento, muestreo del juez y **el despliegue de reserva** (`reserve`, para
cuando nada está certificado). Las cifras son datos; en el código solo están los
techos del requisito 40.10 (12 llamadas por turno y 3 escalados por hora), que un
perfil puede bajar y nunca subir.

## La elección

`chain_for(task, profile, ctx)`, en este orden:

1. **Filtro duro** (`router_catalog.hard_reason`): `status` en `active` o
   `retiring` (`SERVABLE_STATUSES`: uno en retirada atiende hasta su fecha); en la
   lista permitida (`ctx.allowed`: la del partner, en las tareas de conversación); con las
   capacidades de la tarea; con la residencia del cliente (`eu_only`); con
   retención cero y subprocesador; dentro de la restricción soberana si la hay
   (residencia UE, pesos abiertos y proveedor europeo); para `judge`, de otra
   familia que la juzgada; y no enfriado.
2. **Calidad**: certificación por clase vigente de la batería en vigor, con nota
   ≥ el umbral; en conversación, además, certificado **para ese agente**; y su p95
   certificada dentro del objetivo del perfil.
3. **Orden**: el más barato con el precio vigente. Sin estimación de tokens
   (`ctx.estimate`) se ordena con una llamada típica y el techo por llamada no se
   comprueba; con ella, lo que lo pasa se descarta (`over_cost`).
4. **Cadena**: el elegido y hasta dos alternativas, cada una en otro proveedor y
   con su misma residencia.

Cada descarte lleva su motivo (`status`, `not_allowed`, `capability:<x>`,
`residency`, `retention`, `subprocessor`, `sovereign`, `same_family`,
`cooldown`, `tier`, `not_certified`, `below_quality`, `agent_not_certified`,
`over_latency`, `unpriced`, `over_cost`).

Sin nadie que pase: el despliegue de reserva de la tarea si pasa el filtro duro
(`reserve_model`), y si no, `no_model`. Las dos piden una fila en
`router_anomalies` (`RouteDecision.anomaly`); `no_model` manda la conversación a
la Bandeja con «Sin modelo disponible» y el turno no sale de la residencia.

Un **modelo tipado** (`ctx.hint`, por ejemplo el clasificador) puede preferir
uno de los que pasaron; nunca añade uno que el filtro descartó.

«**Fijar un modelo**» (`ctx.agent_pinned_deployment`) cubre solo `answer` y
`tool_turn`; se usa mientras pase el filtro duro (la consola comprueba el resto
al guardar). Las demás tareas siguen la política.

## La afinidad

En conversación, el modelo queda fijado por conversación en el checkpoint del
hilo del cliente (`AgentState.pinned_model`, por agente: con «memoria propia» o
con Recepción, dos agentes comparten hilo). Dura al menos una hora (la caché de
Claude; más si el despliegue declara `cache_ttl_s`) y se desliza con el uso.
Solo cambia si:

- el proveedor falla y responde una alternativa (`pin_after(..., served=alt)`);
- caduca (`expired`);
- se publica otra versión del agente (`new_version`);
- el despliegue deja de pasar el filtro, por ejemplo «No disponible» (el motivo
  queda en `RouteDecision.pin_broken`).

## Escalado y límites

`escalation_for(signals, ...)` mira señales **del grafo**, no del texto: una
herramienta rechaza sus argumentos, se repregunta por segunda vez el mismo dato,
el juez da el turno en rojo, el mensaje trae varias intenciones o el bucle pasa de
4 iteraciones. Con señales, una **subllamada aislada** por la tarea `escalate`,
en la gama por encima de la actual y hasta la que permite el perfil; el bucle
principal no cambia de modelo ni de afinidad. «Económico» no escala: pasa a una
persona. Con 3 escalados en la última hora (`AgentState.router_escalations`),
también.

`TurnBudget` (activado con `turn_budget(...)`) cuenta cada intento de llamada y
el coste del turno: al llegar a 12 llamadas o al techo de coste del perfil lanza
`TurnLimitReached` (motivo `turn_limit`).

## El transporte

Una llamada enrutada sale dentro de `routed(hop)`, y `llm.py` la adapta a lo que
el despliegue declara:

- **retención**, antes que nada: `retention_how` se traduce con `RETENTION_WIRE`
  (`store=false` → `store: false`; `data_retention_mode:none` →
  `data_retention_mode: "none"`); un despliegue sin retención cero o con una regla
  desconocida no recibe nada;
- **caché**: las marcas solo con `cache_mode = explicit`; con la implícita
  (Gemini, OpenAI) o ninguna, los mensajes van tal cual; la clave de caché
  (`prompt_cache_key`), donde existe, es por cliente y versión del agente
  (`cache_key_for`, un hash: el proveedor no ve el id del cliente);
- **prefijo estable**: herramientas ordenadas por nombre y JSON con las claves
  ordenadas;
- **nombres con punto**: traducidos a `__` para todo despliegue `no_dots`, no
  solo para GPT-5.6, y devueltos al nombre del catálogo en la respuesta;
- **salidas estructuradas**: estrictas donde existen y `json_object` donde solo
  hay las normales; la validación propia corre **siempre**
  (`complete_structured`, `StructuredOutputInvalid`);
- **razonamiento**: el nivel de la tarea, como `reasoning_effort` o como
  presupuesto de pensamiento según `reasoning_control`.

Lo que no va enrutado —todo el código de hoy— sale exactamente como antes.

**Quién paga cada llamada.** Donde el proxy LiteLLM es obligatorio
(`NEXUS_LLM_PROXY_REQUIRED=true`, hoy staging), cada llamada sale con la clave
virtual de quien la paga, del mapa `LITELLM_PROXY_VIRTUAL_KEYS`, y sin ella no
sale (`LLMProxyUnavailable`, fail-closed):

- **un partner** (`llm_proxy_partner_scope`): la abre quien conoce al cliente. El
  despachador y el reparto al dueño, por turno; `jobs-consumer`, por trabajo, con
  el partner que lee al empezarlo (así los manejadores de `jobs/handlers/` no
  tienen que acordarse); el grader diferido y las sugerencias semanales, con el
  partner de cada cliente; el copiloto, con el de quien pregunta; la paráfrasis
  de una corrección, con el del cliente;
- **Auphere** (`llm_proxy_platform_scope`): lo que no es de ningún cliente y paga
  Auphere —la evaluación del constructor y la calibración del juez del panel de
  operador— sale con la entrada `"platform"` del mismo mapa. Es explícito: una
  llamada sin partner nunca cae en ella por defecto, y dentro del ámbito de
  plataforma no queda ningún partner atado.

Sin el proxy obligatorio (producción, ADR-036) la llamada va al vendor y un
cliente sin partner es legítimo. Dos barridos lo vigilan: el de las fuentes
(`tests/unit/test_llm_proxy_scope_coverage.py`: todo sitio que construye un
`LiteLLMProvider` abre uno de los dos ámbitos o dice por qué no) y el de los
trabajos (`tests/integration/test_jobs_reach_the_model_behind_the_proxy.py`:
cada tipo registrado llega al modelo con la clave de su partner).

`LLMRouter.complete_routed` / `respond_routed` / `complete_structured` recorren
la cadena: dos intentos por despliegue y, si el proveedor falla (error del
servidor, tiempo agotado o límite de peticiones), la siguiente alternativa en el
mismo turno, y el despliegue caído se enfría lo que diga su fila
(`CooldownBook`, por proceso). Un error de la petición pasa a la alternativa sin
enfriar. Si todas fallan, `ProviderChainExhausted` (`provider_failure`); sin
cadena, `NoModelAvailable` (`no_model`). Una decisión de un cliente no sirve para
la llamada de otro (`IsolationViolation`), y no hay lotes: una llamada, una
petición.

Cada decisión usada se registra **una vez** como `llm.route_decision`
(`events.md` §5): cliente, agente, turno o trabajo, tarea, perfil y versión de la
política, descartados con su motivo, elegido, alternativa usada, escalado,
latencia, coste y precio (2,2 veces el coste). Nunca texto del mensaje.

## Certificación

**Por clase** (`wk/certification/`): la batería v1 —los 95 casos del driver de
evaluación, el paquete `es` de τ-bench 2.0 (se carga desde
`NEXUS_TAU_BENCH_ES_PATH`; sin él, `coverage_gaps` lo dice) y el dominio propio
de reservas (`battery_v1/reservas.json`, cinco países con tú y usted)— se pasa
tres veces por caso. Mide pass^3, repreguntas, afirmaciones sin fuente,
argumentos válidos, cambio de idioma y latencias p50 y p95 con y sin
razonamiento; la nota pondera con los pesos del manifiesto (`pass3` manda). El
juez es de otra familia (`SameFamilyJudge`). `record_class_certification` guarda
versión, fecha, cada métrica, el umbral, el juez y la huella del despliegue;
`expire_class_certifications` la caduca si cambian el modelo, el proveedor, la
ruta, la región, la cuantización o la batería. **El precio no está en la huella:
un cambio de precio no la caduca.**

**Por agente**: la suite del agente con el despliegue, tres veces cada prueba
(`certify_agent`, un lote de un solo cliente: `SingleClientBatch`). Certifica si
todas las críticas pasan 3 de 3 y la nota no baja más de 2 puntos frente a la
referencia. `certified_deployments_for_agent` da lo que el router recibe en
`ctx.agent_certified`; lee con la RLS del cliente y nunca ve la certificación de
un agente hermano (test_44). Caduca con otra versión, otra suite o una
certificación por clase caducada (`expire_agent_certifications`).

**En segundo plano** (`certify_in_background`): para un agente con perfil, los
despliegues activos, certificados por clase en las dos tareas de conversación y
más baratos que el suyo pasan su suite; el router solo los usa si pasan.

**Quién paga** (`payer_for`): el partner, en «Construcción y pruebas» (origen
`tests`), si la lanza él al cambiar la calidad; Auphere, si la lanza Auphere
(origen `certification`).

## El router en el grafo (C3)

**Quién va por el router** lo dice cada versión del agente, con su
`model_policy` (`router_catalog.ModelPolicy`):

| Versión | Clasificar | Responder (`answer` / `tool_turn`) |
|---|---|---|
| **Sin `model_policy`**: un agente de hoy | El de hoy (`llm.classify`, la etiqueta suelta) mientras ningún despliegue certificado para `classify` pase el filtro duro; en cuanto uno pasa, el **tipado** por el router (research D24) | **El camino de hoy, byte a byte**: `respond_with_tools` con su modelo propio, su asignación `respond` y la reserva global. Fijado en su modelo de hoy (D24, D44, historia 13) |
| **Con perfil** (`{"kind": "profile", "profile": "auto"}`…) | Tipado, por el router, con el perfil del agente | Por el router: una decisión para todo el bucle ReAct, con su afinidad |
| **«Fijar un modelo»** (`{"kind": "pinned", "deployment": …}`) | Tipado, con «Automático» (39.8) | El despliegue fijado, mientras pase el filtro duro |

La prueba de que un agente de hoy no cambia es
`wk/tests/unit/test_pipeline_router.py::test_an_agent_of_today_calls_its_provider_exactly_as_before`:
el mismo turno con el router fuera de alcance, con el catálogo de hoy y con uno
que sirve manda al proveedor **las mismas llamadas**, sin afinidad, sin
`llm.route_decision` y sin una lectura más por turno (`could_route` mira en
memoria si algún despliegue podría ganar `classify` antes de leer nada del
cliente). Contra la base, `T/integration/models/test_router_in_the_graph.py`.

**El clasificador tipado** (40.5) devuelve `ClassifyResult` —intención, si
necesita herramientas, riesgo, complejidad, idioma y **cuántas peticiones trae**
(`intents`)— y lo deja en `AgentState.classification`. Uno inválido es un turno
`fallback`, como hoy. Un agente con perfil sin catálogo o sin modelo en su
residencia no clasifica: nada sale de la residencia.

**La respuesta** (`_conversation_route`): con `no_model` no hay llamada, el
contacto recibe el texto neutro y el turno termina con
`turn_failure = {"kind": "llm_failed", "reason": "no_model"}`; un fallo de toda la
cadena es `provider_failure`; el techo de 12 llamadas o de coste es `turn_limit`
(texto de traspaso). Las anomalías (`reserve_model`, `no_model`) van a
`router_anomalies` con la RLS del cliente y al log `router.anomaly`.

**El escalado** (40.4) mira señales del grafo: una herramienta rechazó sus
argumentos al validarlos (`_dispatch_tool` marca `error_kind =
invalid_arguments` cuando el `ToolError` viene de un `ValidationError`; lo que
lee el modelo no cambia), el bucle pasa de 4 iteraciones o el mensaje trae
varias peticiones (antes de responder). Una vez por turno como mucho: una
**subllamada aislada** por la tarea `escalate` que recibe un **resumen** (la
intención, las señales, el mensaje del cliente, el borrador y el resultado de las
herramientas; nunca el prompt del agente ni el historial) y devuelve
`EscalationResult` (`guidance`, `handoff`). El consejo entra en el hilo como nota
interna; el bucle principal no cambia de modelo ni de afinidad. «Económico», el
consejero que pide una persona y el tercer escalado de la hora acaban en
`turn_failure = {"kind": "handoff", "reason": "escalated" | "turn_limit"}`.
No están cableadas aún: «repregunta por segunda vez el mismo dato» y «el juez
da el turno en rojo» (el juez corre después del manejador, con su propio bucle
de reescritura).

**La afinidad** sale del manejador en `pinned_model` (por agente, en el
checkpoint del hilo del cliente: `test_47`) solo cuando respondió por el
router o por la afinidad; la reserva y «Fijar un modelo» no fijan. Lo que gasta
el turno viaja de nodo a nodo en `AgentState.router_turn` (`new_state` lo vacía
en cada turno) para que el techo sea del turno entero.

**El juez** de un turno enrutado se elige con el muestreo de su perfil, el
riesgo del clasificador y la familia del despliegue que respondió.

**Para el despachador** (no es de este bloque): hoy convierte
`turn_failure.kind == "llm_failed"` en `provider_failure`. Tiene que leer
`turn_failure.reason` (y aceptar `kind == "handoff"`) para que la Bandeja diga
`no_model`, `turn_limit` o `escalated`.

## La política del agente y con qué nace

**Dónde vive** hasta el AgentSpec (bloque D): en
`agent_configs.policies["model_policy"]`, con la forma exacta del AgentSpec
(`contracts/agent-spec.schema.json`). Va con la versión, así que borrador,
puerta, deshacer y restaurar le valen tal cual (39.1). El bloque D la pasa a
`spec.model_policy`.

**Con qué nace un agente** (T145, 39.2): en la primera versión de un agente
(`AgentConfigService.stage_new_version` sin versión previa), «Automático» si
**«Automático» puede atenderlo** en ese cliente
(`router_catalog.auto_servable`): un agente nuevo no tiene certificaciones
propias, así que en `answer` y `tool_turn` solo le atiende la reserva del perfil,
y en `classify` la reserva o un certificado por clase, todo con el filtro duro
del cliente. Si no —hoy, D44—, nace por el camino de hoy, como los agentes de
hoy: la consola no ofrece lo que no puede servir. Una versión nueva de un
agente que ya tenía versiones nunca recibe `model_policy` sola: el cambio lo
hace una persona (39.11).

## Los modelos los gestiona Auphere (requisito 64)

Enmienda del 2026-10-29 (D55 y D64): hasta que la gestión de modelos, precios y
selección llegue al panel de operador, **la consola no cambia la política de
modelo** de un agente. `PATCH …/draft` con otra `model_policy` y `POST
…/quality/check` responden `409 model_policy_managed`
(`services/agent_spec/model_policy.py`); los agentes siguen con la suya (D44 y
D45). El constructor, «Desde una plantilla» y el panel de operador la ponen como
hasta ahora.

Los trabajos de la plataforma usan el modelo que fija el despliegue, en una sola
tabla (`nexus_worker/platform_models.py`):

| Tarea | Variable | Sin ella |
|---|---|---|
| `build` (borrador y constructor del cliente) | `NEXUS_LLM_BUILD_MODEL` | el de responder |
| `read_source` (la lectura) | `NEXUS_LLM_READ_SOURCE_MODEL` | el de clasificar |
| `sector` (identificar el sector) | `NEXUS_LLM_SECTOR_MODEL` | el de clasificar |
| `customer_sim` (el cliente simulado, T206) | `NEXUS_LLM_CUSTOMER_SIM_MODEL` | el de clasificar |
| `judge` (el juez) | `NEXUS_LLM_JUDGE_MODEL` | el de clasificar |

Todas salen por el proxy de LiteLLM con la clave del partner del cliente: el
consumidor de trabajos abre su ámbito para todo el trabajo. La restricción se
retira en la spec que construya la gestión de modelos (64.4).

El cliente simulado llama con el rol `customer_sim` (tarea `answer` en
`TASK_BY_ROLE`) y se mide con el resto de la pasada en «Construcción y pruebas».
Ni él ni el juez pueden ser el modelo que respondió como agente (61.5): el cliente
pasa al del juez o al de clasificar si coincide; un juez que coincide no cuenta en
esa pasada, y si es de la misma familia (`simulation/customer.family_of`) la pasada
lo dice en `warnings` y en el log `tests.judge_warning`, que es el aviso al
operador mientras no exista la gestión de modelos en el panel.

## El ciclo de vida de los modelos (41.7 a 41.9)

`api/services/model_lifecycle.py`, con el cron `model-lifecycle-cron`
(`wk/streams/model_lifecycle_cron.py::run_model_lifecycle_cron`, cada hora;
todo idempotente):

- **Retirada**: el admin registra la fecha (`announce_retirement`): `retiring`,
  que **sigue atendiendo hasta su fecha**. Los partners con agentes fijados
  —«Fijar un modelo» o un agente de hoy cuyo modelo de hoy (asignación,
  `policies.llm.respond_model` o el global) es ese— reciben `model.retirement`
  (aviso, campana y correo) a 30 días —o en el acto si queda menos— y a 7, con el
  sustituto de cada agente: el certificado para él, de la misma gama y con el
  precio más cercano, o «Automático». En la fecha, cada uno pasa al sustituto (si
  sigue certificado) o a «Automático» con **una versión nueva**
  (`publish_copy`, su historial) y `agent.quality_changed` en la auditoría; el
  despliegue pasa a `retired`. Los agentes con perfil no notan nada.
- **Precio**: entra con su fecha (`add_price`, `model_prices`). Si sube más de
  un 10 % el precio estimado por mensaje de un agente —fijado en él o que lo usó
  los últimos 30 días: con lo que gastó, o con una llamada típica sin tráfico—,
  su partner recibe `model.price_change` **antes** de que entre en vigor (uno por
  cambio). En su fecha, el cron lo pasa a las columnas de `model_profiles` que
  lee el medidor; solo los precios posteriores a la 0180 (`PRICES_FROM`), para
  que uno antiguo nunca pise una columna. Los pesos del medidor no se tocan solos
  (spec 007, R3.3).
- **«No disponible»**: `mark_unavailable`; el router deja de usarlo desde el
  siguiente turno, también en las conversaciones con afinidad (`pin_broken =
  status`).

**Desde el siguiente turno**: quien cambia el catálogo llama a
`router_catalog.catalog_changed()` (este proceso olvida su catálogo:
`model_resolver` se apunta al importarse) y publica `catalog` en
`nexus:agent_config:promote`; el suscriptor de promoción del worker lo oye y
llama a `invalidate_catalog()`.

## Bedrock y Scaleway (T142)

La 0185 los siembra **en `draft`** y sin afirmar nada que nadie haya comprobado:
retención cero `false`, sin DPA ni alta de subprocesador, licencias sin leer, sin
precios ni pesos ni certificación. La puerta los rechaza diciendo todo lo que
falta, el hop no los ejecuta y el router no los elige.

| Despliegue | Ruta | Retención en el cable |
|---|---|---|
| `bedrock/eu.anthropic.claude-haiku-5-5` (básica) y `bedrock/eu.anthropic.claude-sonnet-5-5` (media) | Perfil de inferencia `eu.` desde `eu-south-2` | `data_retention_mode: none` |
| `scaleway/gpt-oss-120b`, `scaleway/gpt-oss-20b` (Apache-2.0), `scaleway/whisper-large-v3` (MIT) | API compatible con OpenAI, París | `store: false` |

**El registro en el proxy** (`router_catalog.litellm_params_for`, para
`POST /model/new`): Bedrock con `aws_region_name` y **sin clave** (el rol IAM de
la tarea del proxy necesita `bedrock:InvokeModel` e
`InvokeModelWithResponseStream` sobre los perfiles `eu.` y sus modelos base en la
UE); Scaleway con `api_base` y `api_key` del entorno del proxy
(`SCALEWAY_API_BASE` y `SCALEWAY_API_KEY` en `nexus/<entorno>/litellm` de Secrets
Manager; con `STORE_MODEL_IN_DB` el proxy guarda el valor al registrar, así que
al rotar la clave hay que volver a registrar). Las reglas de retención de cada
ruta están en `RETENTION_RULES` de `test_50`.

**Antes de activar cualquiera**, por orden: el alta de Bedrock (inferencia) y
de Scaleway como subprocesadores (DPA y lista pública); comprobar en el cable
que el proveedor acepta su parámetro de retención; comprobar las rutas exactas
(`aws bedrock list-inference-profiles --region eu-south-2`) y las cuotas, con su
evidencia en `specs/047-la-fabrica-de-agentes/evidence/`; leer las licencias
enteras; cargar precios y pesos con su fuente; y certificar.

## Lo que falta para que el router atienda turnos de verdad

- **Datos**: la retención cero comprobada de alguna fila (D44). Hasta entonces el
  router no elige nada y todos los agentes siguen por el camino de hoy.
- **El despachador**: que lea `turn_failure.reason` (arriba).
- **Fuera del router todavía**, para un agente con perfil: la reescritura del
  juez, el propio juez (`role=grader`) y la multimedia (`multimodal/processor.py`,
  que ya dice su tarea en cada medida). Con un cliente «Solo UE» deben pasar
  por el router antes de que un agente con perfil atienda a ese cliente.
- **Lanzar certificaciones** desde el admin: la batería por clase no tiene
  trabajo de plataforma y la suite por agente es el `quality_check` de T147.
