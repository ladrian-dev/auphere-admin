# Agentes: AgentSpec, constructor, pruebas, puerta, estados y versiones

Spec 047 («La fábrica de agentes»). Este documento cuenta cómo nace, se prueba, se
publica y vive un agente en la consola nueva, y dónde está cada pieza. El detalle
de cada regla está en `specs/047-la-fabrica-de-agentes/` (requisitos 15 a 27 y 33
a 42).

## 1. El AgentSpec

Cada versión de un agente (`agent_configs`) guarda su **AgentSpec**
(`agent_configs.spec`, `services/agent_spec/schema.py`) y el prompt se compila de
él (`services/agent_spec/compiler.compile_spec`). Mismas entradas, mismos bytes.

- **Dos modos.** «structured» (lo que hace el constructor: identidad, objetivo,
  secciones, reglas, herramientas, escalada, voz, preguntas frecuentes) e
  «instructions» (los agentes de antes: su prompt de hoy, byte a byte). La
  migración 0189 pasó cada prompt propio a «instructions»
  (`services/agent_spec/legacy.spec_from_version`); el ensayo de la consola nueva
  comprueba que sigue compilando los mismos bytes (sección 7).
- **Herramientas de un agente «instructions».** Las manda la versión
  (`agent_configs.tools`), que es lo que construye el runtime y lo que escriben los
  interruptores de Habilidades. La spec guardada lleva una copia de la última
  edición, y `api/console/agent_spec_drafts.spec_of` no la usa: lee la lista de la
  versión (lo que la copia ya nombraba más lo que tiene forma de catálogo). Así la
  ficha, la revisión y la puerta ven lo encendido, y editar las instrucciones no lo
  borra (QA de staging del 2026-11-08). En uno «structured» los interruptores
  escriben la spec y las dos listas son la misma.
- **Validador** (`services/agent_spec/validator.py`): errores que bloquean la
  puerta (herramientas desconocidas, límites, coherencia con la ficha) y avisos.
- **Revisión** (`services/agent_spec/review.py`, `api/console/agent_review.py`):
  incoherencias como prometer algo sin la herramienta que lo hace; las
  bloqueantes paran la puerta.
- **Idiomas** (spec 063, requisito 1). Se deciden en «Cómo habla»
  (`voice.languages`, el primero es el principal; `voice.languages_limited`,
  «Responder solo en estos idiomas», apagado por defecto). Por defecto el agente
  contesta en el idioma del último mensaje del cliente.
  - **Quién lo cambia:** solo una persona puede encender o apagar el límite. El
    validador lo rechaza con `languages_limit_by_builder`, como el aviso de IA.
  - **De dónde lo lee el turno:** al guardar, `voice` se copia a
    `policies.console.languages` como `{primary, allowed, limited}`
    (`api/console/agent_spec_drafts._sync_console`), y eso es lo que lee el turno.
  - **Nadie más lo escribe:** ni los ajustes antiguos (`merge_console_policy`
    conserva los guardados) ni el Companion.
  - **Lo guardado antes:** una lista sin `limited` no limita nada.

### La regla de idioma del turno (spec 063)

`agent_console_policy.language_rule`, que el turno pone como **último mensaje de
sistema**, detrás de la directiva del turno y delante del historial
(`pipeline._build_handler_messages`). Va siempre, también sin política de
consola, y en inglés como el resto de instrucciones. Dice:

- **sin límite:** contesta en el idioma del último mensaje;
- **con límite:** solo en estos, y si no, en el principal;
- **en los dos casos:** si no sabes el idioma, sigue el de la conversación; al
  empezar, el principal.

Nombra las instrucciones que anula («always reply in …», «never answer in …»),
porque dentro del bloque de política perdía ante un prompt con «Never answer in
English» (staging, 2026-11-18). Sola y al final, acertó 10 de 10. Llega a todos
los agentes publicados sin volver a publicarlos. La reescritura del evaluador
(`_RETRY_SYSTEM_TEMPLATE`) conserva el idioma de la respuesta que rehace. Los
textos que el turno envía sin modelo, como el mensaje de espera del número, salen
tal como los escribió el negocio.

## 2. El constructor

Todo lo largo es un **trabajo** (`jobs`, `services/jobs.py`) que corre el worker
(`wk/jobs/handlers/*`) y la consola sigue por `GET /console/jobs/{id}`.

- **Borrador** (`services/builder/agent_draft.py`, `POST
  /console/clients/{ref}/agents/draft-jobs`): «Generar borrador», «Desde una
  plantilla» o «En blanco». Lee la ficha del negocio y devuelve un AgentSpec, sus
  preguntas abiertas, las integraciones que necesita y su batería de pruebas.
- **Cuando el modelo falla al escribir el borrador** (spec 063, requisito 3):
  - **Modo JSON:** la llamada pide `response_format={"type": "json_object"}` si
    LiteLLM dice que el modelo lo admite (`runtime/llm.supports_json_object`).
  - **Cómo terminó:** cada llamada registra `builder.model_output` con
    `json_mode`, `finish_reason` y `output_tokens`, sin nada de lo escrito.
  - **Cortado no es ilegible:** una salida cortada (`finish_reason == "length"`) es
    `truncated`, no `bad_json`.
  - **El detalle del fallo:** `bad_json` lleva en `jobs.agent_draft.unavailable` el
    tipo de error y su posición.
  - **Cómo se lee la salida:** primero entera, y solo después buscando un bloque
    cercado o la primera y la última llave.
  - **Lo que no hace:** reintentar, porque cada intento se paga. Su gasto va
    siempre a «Construcción y pruebas» del partner.
- **Nombres de otros clientes** (garantía 5; 047 15.4; spec 063, requisito 4):
  - **Qué se exime:** no cuenta como ajeno lo que este cliente dio al constructor
    (nombre del agente, descripción, ficha, guía o plantilla;
    `agent_draft._without_own_names`, con `validator.mentions`).
  - **Qué se quita:** lo que el constructor escribe por su cuenta y nombra a otro
    cliente, solo ese elemento (`_drop_at`: una sección, un procedimiento, una
    regla, una habilidad, una pregunta frecuente, el objetivo, el tono, el saludo
    o el mensaje de escalado).
  - **Qué se registra:** código y sitio, nunca el nombre.
  - **Si aun así no vale:** `invalid_draft`. «Desde una plantilla» responde
    entonces `422 draft_invalid`, nunca un 500.
  - **La prueba:** `tests/isolation/test_063_builder_foreign_names.py`.
- **Copiloto** (`services/builder/copilot.py`): propone cambios como
  **propuestas** (`proposals`) con su diff; aceptar es aplicarlas al borrador.
- **Herramientas pendientes de conexión** (enmienda del 2026-10-29, requisito 62,
  D53 y D62): si una habilidad pide una integración que el cliente aún no conectó,
  el borrador **conserva** sus herramientas con su petición en
  `connection_requests`, y el validador las acepta si están en el catálogo y
  permitidas y su integración es un conector con activación. Las de `catalog.*`,
  que dependen del catálogo de Meta del canal, no entran sin él. Ese catálogo se
  enlaza en Canales y nunca da «Conectar» (65.3). El turno no las ve hasta que la conexión exista y esté activada para
  el agente (`activations.tool_policy`, barrido en `test_44`). Activar la conexión
  (o cambiar su permiso) deja desactualizadas las pruebas del agente.
- **Agentes sugeridos** (requisito 60.6, D61): el constructor del cliente
  (`docs/ficha-del-negocio.md`) propone agentes que se guardan en
  `suggested_agents` y la pestaña Agentes enseña como «Sugerido». No se crean
  solos: «Crear este agente» abre «Nuevo agente» con su nombre y su descripción.
- **El sector**: las pruebas del sector y el constructor leen el sector guardado
  en la ficha (`services/business/sector.py`), nunca el nicho (57.6).
- **Guía del sector, patrones de papel y ficha** (enmienda del 2026-10-29,
  requisito 58, D47, D66 y D67; `services/builder/guides/`). El constructor recibe,
  además de la descripción y la ficha valladas:
  - la **guía del sector guardado**: qué preguntar, procedimientos típicos, lo que
    hay que pasar a una persona y las herramientas que el oficio suele usar. Las
    seis de Auphere salen de las plantillas verticales (`guides.yaml`; sus
    herramientas son las `tools.required` de sus plantillas, sin `booking.*`). Un
    cliente de «otro» recibe la que Auphere convirtió para su etiqueta normalizada
    (`sector_guides`, 0207) o, si no la hay, una **generada para él** con sus 12
    pruebas «Generada» (`generated_guides`, RLS): la genera el trabajo del borrador
    solo con la etiqueta y la guía genérica de Auphere, la valida, la reintenta una
    vez y, si no vale, guarda la genérica. La guía va siempre vallada: es un
    ejemplo de oficio, no órdenes ni datos del negocio;
  - los **patrones de papel** que encajan con la descripción (Recepción, Ventas,
    Cobros, Soporte; todos si ninguno encaja). Son ejemplos combinables, no papeles
    fijos: no deciden herramientas ni pruebas, y no nombran acciones que ninguna
    herramienta hace (no hay herramienta de enlaces de pago);
  - el **catálogo** con lo que hace cada herramienta (`capability_names`) y si este
    cliente la tiene. Las de un nombre que el AgentSpec no admite (Composio, en
    mayúsculas) no se enseñan.
- **Los datos de la persona del turno** (enmienda del 2026-11-16, requisito 70).
  Ninguna herramienta busca ni elige a un cliente final (garantía 8). Las del
  inventario cerrado de `validator.SERVER_SIDE_ARGS` (razonado en
  `tests/isolation/test_51`), como `quedate.register_me` o
  `payments.request_review`, **escriben** los datos que la persona del turno da de
  sí misma. Así funciona:
  - El catálogo del constructor marca esas herramientas con
    `[escribe los datos de la persona del turno]` (`agent_draft.OWN_DATA_MARK`). El
    prompt le dice que las use con lo que la persona escribe, y su teléfono lo pone
    el sistema.
  - El catálogo no enseña las que el constructor no puede poner, porque dejan elegir
    a un cliente final fuera del inventario (`validator.end_customer_picks`). Son
    `quedate.create_host` y las de operador. Antes se enseñaban, el saneado las
    quitaba y la tarea que las citaba se quedaba sin herramienta.
  - Si el borrador lleva una del inventario, el saneado quita la regla que prohíbe
    pasar a las herramientas el nombre, el documento, el correo o el teléfono
    (`agent_draft.forbids_own_data`). Se quedan la que prohíbe buscar a otra persona y
    la que pone una condición al alta («sin el correo confirmado»).

  En staging, «Anfitriones Quédate» salió con esa regla y no daba de alta a nadie.
- **La agenda solo con Reservas encendido** (D67): `validator.load_context` da las
  `reservas.*` por conectadas solo si el cliente tiene el módulo Reservas
  (`ClientAccess.reservas_on` y su modo elegido). Apagado, cuentan como sin
  conectar y sin activación: el constructor las ve «SIN ACTIVAR», `sanitize` las
  quita (`tool_not_connected`) y la puerta las rechaza; el playground y las pruebas
  responden «Reservas no está activo», como el turno.
- **La agenda desde el agente** (spec 057, requisitos 1 a 3 y 7; reabre D67). El módulo
  sigue mandando, pero el agente puede encenderlo:
  - **En el alta**, «Gestiona citas» (`DraftJobIn.agenda`, y `reservas` con el modo si
    el módulo está apagado). Con el interruptor encendido, la ruta enciende Reservas en
    la misma transacción y **antes** de encolar o de escribir el borrador
    (`services/reservations/turn_on.py: turn_on_from_agent`), así que el constructor ve
    la agenda. El constructor lo obedece (`DraftRequest.agenda`): el bloque `<agenda>`
    del mensaje y, en `sanitize`, las nueve `reservas.*` disponibles, los
    procedimientos fijos de reservar y de cambiar (`AGENDA_PROCEDURES`) si el modelo no
    los escribió, y fuera todo texto que prohíba la agenda (`compiler.forbids_agenda`).
    Apagado, ninguna `reservas.*`. Sin interruptor (`null`), como antes. Plantilla y en
    blanco igual. `draft-options` dice si se ofrece, el modo del cliente y el sugerido
    por su sector (`turn_on.suggested_choice`: restaurante → aforo).
  - **En Conectores**, la fila «Agenda (Reservas)» (`api/console/agenda.py`, `GET`/`PUT
    …/agents/{id}/agenda` y `…/agenda/tools`). Activar enciende el módulo si hace falta
    (con el modo, tras confirmar en la consola) y pone las nueve de una vez en el
    borrador (`capabilities_client.set_agent_tools`); desactivar las quita (también de
    `procedures[].tools`) y nunca apaga el módulo ni toca reservas. Una a una, como
    cualquier herramienta (`PUT …/capabilities`).
  - **Encender desde un agente** corre bajo la RLS del cliente (`nexus_app`), sin
    `as_tenant` ni `set_access`: añade `reservas` a los módulos sin tocar `enabled`,
    crea los ajustes con su modo, prepara la agenda a los **otros** agentes que dan
    citas (`passing.gives_appointments`) y lo audita con la persona y el agente. Lo
    puede quien edita agentes (`agents:write`); apagar sigue en Acceso.
  - **La propuesta de texto** (requisito 3): cada cambio de la agenda en un agente
    estructurado encola el trabajo `agenda_text` (0229), que escribe una propuesta del
    constructor (`services/builder/agenda_text.py`) sobre procedimientos, reglas,
    escalado, habilidades, instrucciones y `services.faqs`, nunca `/tools`. Con modelo
    (`role="build"`, medido como construcción) o, si su salida no pasa las
    comprobaciones o el proveedor falla, el respaldo sin modelo. Vive 7 días; la
    siguiente de la agenda deja `stale` la anterior. Lo de la ficha que dice que el
    equipo confirma las citas se señala en `diff.ficha_links` y no se toca. `GET
    …/proposals` añade a cada operación su `before`.
- **«Desde una plantilla»** (58.6, `agent_draft.draft_from_template`): como el
  constructor, sin modelo: un AgentSpec estructurado salido de la guía del sector de
  la plantilla y de sus herramientas (las que el cliente tiene), con las pruebas del
  caso y las del sector del cliente. Ya no monta el prompt de la plantilla en modo
  «instrucciones». De la plantilla toma solo las herramientas que el cliente tiene,
  y la descripción que escribe no promete lo que no podrá hacer. Las rutas de la
  consola de antes que montaban la plantilla —`POST /console/clients` con
  `seed_template`, `…/agent/from-seed` y `POST …/agents` con `seed_template`—
  responden `seed_template_retired` a un partner con la consola nueva (D75).
- **La evaluación del constructor** (58.7, `services/builder/evaluation.py`, banco
  `eval_bank_v2.json`): 120 descripciones, cada una con su negocio (nombre,
  servicios y horario), 20 de sectores sin guía. Cada borrador recibe su guía; se
  mide el validador a la primera y si pasa sus pruebas del sector, también por
  separado con guía y sin guía (`by_guide`).
- **Partida «Construcción y pruebas»**: todo el constructor, las pruebas y el
  playground cuentan en ella y se paran al agotarla (`402
  build_budget_exhausted`; ver `docs/billing.md`). La edición a mano sigue.
  Desde la T217 (revisión de seguridad del 2026-10-30) también «Volver a leer»
  (`POST …/business/read`) responde `402`; identificar el sector sin partida usa
  la regla de respaldo, sin modelo; y una suite en marcha vuelve a mirar la
  partida antes de cada prueba: agotada, las que faltan no empiezan, la empezada
  termina sus tres pasadas, la pasada queda `failed` con `stopped:
  build_budget_exhausted` y `not_started`, y el trabajo falla con ese código.
- **Quién paga las pruebas** (requisito 68, `services/testing/billing.py`): la primera
  pasada de todas las pruebas de cada agente, Auphere. Después, guardar no las repite y
  otra pasada entera sale de la bolsa del cliente, cada vez con confirmación
  (`confirmed_tests`: sin ella, `409 charge_not_confirmed`; si ahora son más pruebas, `409
  charge_changed`) y con 1,5 veces lo estimado en la bolsa (si no, `402
  client_bag_not_enough`; sin precio, `409 charge_unknown`). Mide con `source = tests_client`, cobra
  un asiento `debit_tests` por pasada y sale en Consumo como «Pruebas a cargo del
  cliente». No cuenta para el tope del agente ni para los días que le quedan a la bolsa.
  Si lo que queda baja de lo que cuestan 2 pruebas, las que faltan no empiezan
  (`client_bag_low`). Repetir una prueba, las que no pasan (`scope: failed`) o las
  desactualizadas si no son todas sigue en la partida. Un cliente con consumo ilimitado,
  o un partner sin bolsas, también. Una pasada que se paró, o que solo dejó «No sé», no gasta
  la de Auphere.

### Solo lo que tenemos (enmienda del 2026-10-30, requisito 65)

Un cliente puede crear un agente para cualquier cosa que necesite, siempre que
tengamos las herramientas. Ningún papel, plantilla ni sector decide las
herramientas, las pruebas ni las reglas del validador. Decisiones en
`research.md`, D72 a D77; contrato en `contracts/console-api.md` §11.

- **Disponible** (65.2, `validator.Context.usable`). Una herramienta está
  disponible si cumple todo esto:
  - existe en el catálogo, se ofrece y no está retirada;
  - el AgentSpec admite su nombre, así que Composio queda fuera;
  - su conector está conectado o tiene activación;
  - su módulo está encendido.

  Un **conector ofrecido** (`offered_connectors`) es una integración con
  activación y al menos una herramienta disponible. Conectar Stripe por Composio
  no le da nada a un agente estructurado, así que no cuenta.
- **Lo que no tenemos no entra** (65.3 y 65.4; `sanitize` y
  `services/agent_spec/missing.py`). Sale como **capacidad que falta**, nunca como
  «Conectar {X}»:
  - una integración que no es un conector ofrecido (`integration_unknown`);
  - el módulo Reservas apagado (`module_off`);
  - el catálogo de Meta sin enlazar (`not_linked`);
  - una herramienta inventada (`tool_unknown`);
  - un procedimiento o una regla que prometen lo que ninguna herramienta del
    agente hace (`no_tool`).

  El borrador las lista en `missing_capabilities`: el resultado del trabajo y
  `GET …/draft`. Lo que el constructor dejó fuera se guarda en
  `policies["builder"]`; las promesas del AgentSpec se calculan en cada lectura.
  **Lo guardado también se contrasta al leer** (spec 057, requisito 6:
  `missing.still_missing`): una promesa que ya cubre una herramienta del agente, un
  módulo ya encendido o una integración ya conectada dejan de salir, en el borrador y
  en lo publicado. Es lo que pasó con Spa Jemma: la v1 se escribió sin agenda y el
  aviso «No tenemos herramienta para: reservar citas» siguió con las nueve publicadas.
  Un borrador de antes de la enmienda con una integración así se lee y se edita sin
  ella, y nada se rechaza por eso: la consola no edita habilidades (D72).
- **Las promesas, por lo que hace cada herramienta** (65.5,
  `capability_names.TOOL_ACTIONS` y `compiler.PROMISES`). Una promesa la cumple
  una herramienta que hace esa acción, nunca una que comparte el prefijo:
  `payments.request_review` revisa un comprobante, no cobra ni factura;
  `reservas.services` lista servicios, no reserva. Cubre:
  - reservar, cambiar o cancelar citas;
  - cobrar, y cobrar con tarjeta o con enlace;
  - emitir facturas;
  - tomar, cambiar o cancelar pedidos;
  - enviar documentos, fotos o ubicaciones;
  - programar recordatorios;
  - enseñar el catálogo.

  No es promesa lo negado («no cobramos»), el deseo del cliente («si quieren
  reservar»), un propósito («para reservar, pasa al equipo») ni un sustantivo («su
  reserva»). En un agente estructurado **bloquea** la puerta (su hallazgo trae el
  puntero para «Arreglar en el borrador»). En uno de antes («instructions») avisa
  (D73).
- **Los límites del prompt** (65.6, `compiler._limits`). Todo agente estructurado
  lleva la sección fija «Lo que no haces»:
  - solo hace acciones con sus herramientas;
  - si le piden otra cosa, lo dice y pasa la conversación a una persona;
  - cada habilidad lleva su alternativa (la de por defecto, pasar a una persona).

  Un agente de antes no cambia (CE-009).
- **Lo que reciben el constructor, el copiloto y las sugerencias** (65.7). Los tres
  reciben las herramientas disponibles con lo que hace cada una
  (`agent_draft.available_lines`).
  - El copiloto con modelo quita lo que no tenemos de lo que propone y no propone
    un cambio que añade una promesa sin herramienta.
  - Una regla sin modelo que promete algo así no se propone: «No tenemos
    herramienta para: …».
  - El constructor del cliente no sugiere un agente cuya descripción necesita algo
    que el cliente no tiene. Si no queda ninguno, sugiere el que atiende con la
    ficha y pasa al equipo (`client_profile.feasible_agents`).
  - El papel de una sugerencia es opcional y cualquier otro llega como `null`.
- **Ficha o instrucciones que faltan** (65.12). Si la ficha no se puede leer, el
  trabajo falla con `facts_unavailable` («Desde una plantilla» responde 503).
  Si el modelo no devuelve instrucciones, `builder_unavailable`. En ningún caso se
  escribe un borrador genérico.
- **Herramientas solo por el AgentSpec** (65.10). `PUT /console/clients/{ref}/tools`,
  `PATCH …/draft` con `tools` y, desde la T217, `POST …/agent/versions` con `tools`
  dan `409 structured_agent` a un agente estructurado. `PUT …/capabilities`
  (encender o apagar una herramienta, a la que llevan las citas del copiloto)
  sigue abierta, pero en un agente estructurado edita su AgentSpec y pasa por el
  validador, como `PATCH …/draft` (D79).
- **El bloqueo por herramienta que no se lee cierra** (T217, garantía 2): si el
  turno no puede leer `tenant_connector_tool_overrides` (`blocked` o
  `needs_approval`), no ofrece ninguna herramienta, ni las de la casa
  (`pipeline.without_gated`), como la política de herramientas (D76).

## 3. Pruebas

- **Batería por agente** (`agent_test_suites`, `agent_tests`;
  `services/testing/suites.py`): pruebas «case» con su primer mensaje, su plan, el
  estado esperado y sus criterios; las **críticas** tienen que pasar 3 de 3.
- **Catálogo del sector** (`sector_test_catalog`, 12 por sector, editable en el
  admin) y el **juez** (`services/testing/judge.py`), calibrado desde el admin.
  Las 12 de un agente salen de su guía (`sector_catalog.add_sector_tests`): las del
  catálogo bajo la clave del sector o de la guía convertida, o las de su guía
  generada (`generated_guide_id`; la consola las marca con `origin: "generated"`).
  Cada prueba declara lo que necesita hacer el agente (`needs`, las acciones de
  `capability_names`; 0208 lo escribe en la versión 1). Una prueba sin `needs` lo
  deduce de su estado esperado: una cita necesita reservar. Al añadirlas, la que
  necesita algo que las herramientas del agente no hacen queda «No aplica» con su
  razón, sin que nadie la marque (65.8, D74).
- **Varios turnos con un cliente simulado** (enmienda del 2026-10-29, requisito 61,
  D52; `wk/simulation/customer.py`, `wk/jobs/handlers/agent_tests.py`). Cada pasada
  es una conversación: el cliente simulado sigue la persona y el plan de la prueba
  (vallados), responde a lo que pregunta el agente y no inventa datos fuera del
  plan. Para al cumplir el plan, al despedirse, al pasar a una persona o a los 8
  turnos del cliente, y ese tope es un fallo con su motivo. Se comprueba el estado
  final: la cita en la agenda simulada de Reservas (servicio, día y hora), el
  escalado (a quién y por qué) y si se pidió un pago. Cada pasada empieza con la
  agenda sembrada de nuevo. La conversación y por qué terminó (`transcript`,
  `stop`) se guardan en el resultado y `GET …/agents/{id}/tests` las sirve con
  todas las pasadas (`attempts`) para «Por qué falló». El cliente simulado
  (`NEXUS_LLM_CUSTOMER_SIM_MODEL`, rol `customer_sim`) y el juez
  (`NEXUS_LLM_JUDGE_MODEL`) no son el modelo que responde: el cliente cambia de
  modelo si coincide; el juez que coincide no cuenta, y si es de la misma familia
  la pasada lo avisa (`warnings` en el resumen y `tests.judge_warning` en el log).
  Sin cliente simulado (en local, en memoria), una pasada es un turno.
- **Si un modelo no responde, no se le apunta al agente** (bug
  `el-probador-tapa-los-fallos-del-modelo`; `wk/simulation/failures.py`). Si no
  responde el modelo del agente, el del cliente simulado o el del juez cuyo veredicto
  hacía falta, la pasada queda sin decidir, con `stop: model_failed`. Una prueba con
  alguna así y ninguna en rojo es «No se pudo probar» (`status: model_failed`, con
  `why_untested`): no entra en la nota ni en «Arreglar» y queda desactualizada, así que
  «las afectadas» y «Guardar» la repiten. Si ninguna pasada tuvo modelo, la pasada queda
  `failed` con `stopped: model_unavailable` y el trabajo falla con ese código; si alguna
  lo tuvo, el trabajo termina y `summary.model_failed` dice cuántas pruebas no. En la
  puerta, una crítica sin probar se salta como `critical_test_untested`; una normal se
  avisa (`test_untested`). Un turno que agota sus 120 s sigue contando como fallo del
  agente: no se sabe de qué lado está.
- **Ninguna pasada sobrevive a su trabajo** (bug
  `pasadas-huerfanas-tras-fallar-el-trabajo`): si una lanza, las demás se cancelan antes
  de que el trabajo quede `failed`, y la pasada se cierra con `stopped: internal` o
  `interrupted`. Si siguieran, llamarían al modelo a la vez que el «Reintentar».
- **Una pasada viva por agente** (T217): con un trabajo `tests` del agente en cola
  o en marcha, `POST …/test-runs` la devuelve (`202` con su `job_id`, su `run_id`
  y cuántas pruebas lleva) y no encola otra, como «Volver a leer». «Guardar» corre la
  misma suite y se paga igual, así que se ven: `POST …/test-runs` con la de «Guardar» en
  marcha responde `409 suite_running`, y «Guardar» con otra viva falla con ese código.
  Quien lanza una pasada toma antes el bloqueo de la fila del agente
  (`runs.lock_agent`) y pregunta a `runs.live_run`, que mira el trabajo y no
  `AgentTestRun.status`, porque esa columna no se entera de una caducidad.
- **El coste, antes** (61.8, enmendado por el 66.5): `POST …/test-runs` con
  `dry_run: true` responde `200` con la estimación (`services/testing/estimate.py`,
  calibrada con 20 pasadas de staging: 3 llamadas del agente con la mayor parte del
  prompt en caché, 2 del clasificador, 2 mensajes del cliente simulado y el juez, por 3
  pasadas, a precio), quién la paga (`payer`), cuánto y cuánto queda (`charge`, `left`,
  en cien milésimas y en la moneda de quien paga) y si llega (`fits`), sin encolar nada.
  `estimate` sigue en millonésimas de dólar: la consola no compara importes. Pregunta
  siempre si paga la bolsa y, si paga Auphere, solo si no cabe. Un precio que no se
  conoce no es cero: `charge: null` y `unknown_prices`.
- **Una suite que merece lo que cuesta** (requisito 66): el constructor deja como mucho
  4 pruebas del caso, solo de lo específico del agente; de la batería de 12 del sector
  entran todas las críticas que aplican y, hasta 8 entre las dos, las demás. Una del caso
  que ya cubre una del sector no entra (`covers`: misma pregunta, mismo estado esperado,
  y una crítica solo la sustituye otra crítica). `reconcile_suite`
  (`services/testing/sector_catalog.py`) recalcula «No aplica» al guardar el borrador y,
  antes de cada pasada, archiva lo que sobra contra esa versión. No toca lo que tocó una
  persona (`created_by_kind`).
- **Lo que una prueba puede esperar** (66.8, `judge.CHECKABLE_STATE`): `escalated`,
  `booking.created`, `booking.count`, `payment.requested` y `escalation.to`, lo único que
  dice `World.final_state`; lo fija `wk/tests/unit/test_checkable_state_contract.py`. Otra
  clave se quita al guardar (`suites._test_row`) y, si ya está guardada, no cuenta. Por la
  API, `422 unknown_state_key`. Lo demás se escribe en `criteria`, y el juez lo compara
  con la ficha (66.9): recibe los datos del negocio en `<ficha>`, los mismos que el agente,
  y en `<agente>` lo que sabía el agente en esa conversación (bug
  `el-juez-solo-mira-la-ficha`): el prompt de la versión probada sin «Datos vigentes del
  negocio» (sus instrucciones y sus preguntas propias) y el conocimiento de cada mensaje
  del cliente simulado (`judge.agent_reference`). Un dato de cualquiera de los dos es
  correcto; si contradice la ficha, manda la ficha. Los dos bloques son dato (`inert`).
- **Con qué modelo responde** (spec 065): la elección del agente (`agents.respond_model_profile_id`,
  con `respond_model_set_by` `partner` u `operator`), si no el ajuste de su versión
  (`policies.llm.respond_model`), si no el modelo por defecto de Auphere de ese entorno
  (`platform_settings.agent_respond_default`, Sol al desplegar). Una sola resolución,
  `nexus_api.core.respond_model.resolve`, para el turno, la consola, el panel y el uso de
  la 059. Si el elegido no puede con lo que el agente usa (Skills o conector MCP de
  Anthropic), responde el siguiente que pueda y la consola lo avisa
  (`chosen_model_cannot_run_agent`). Es un ajuste vivo: vale desde el turno siguiente, sin
  publicar versión ni lanzar pruebas, y no toca la pasada de pruebas. El Playground y las
  pruebas responden con el mismo modelo y dicen con cuál respondió (`model`, `fell_back`).
  La asignación `respond` del cliente (`tenant_model_bindings`) ya no decide nada: la 0240
  la pasó a sus agentes.
- **Cómo sale cada llamada y quién la termina si falla** (spec 065, T052-T056): el turno
  va por `LLMRouter.respond_with_tools` sin router, y cada salto lleva el perfil de **su**
  modelo (`nexus_api.core.respond_profiles`, `llm.respond_hop_extra`): con Claude 5.5,
  esfuerzo bajo (`output_config`), razonamiento adaptativo con
  `block_binding.prefix_mismatch_behavior = "drop_block"` y su beta, `max_tokens` 8192, la
  caché de la conversación (`cache_control` arriba) y su plazo (Opus 90 s, Sonnet 60 s,
  Haiku 45 s); con GPT-5.6, lo de antes (30 s). Un modelo sin perfil (Sonnet 4.6, Haiku
  4.5) sale byte a byte como antes. La cadena (`pipeline.turn_model_pin`,
  `respond_model.respond_reserve`) es el modelo del agente y la **reserva de la otra
  familia** de su perfil (OpenAI → Sonnet 5.5, Anthropic → Terra) si está habilitada para
  responder en ese entorno; si no, la de hoy (`llm_respond_model`, Sol). Un agente con
  Skills o conector MCP de Anthropic solo cae a Sonnet 5.5, y sin ella no tiene reserva.
  Cuando la reserva responde una llamada, el resto del turno sigue con ella
  (`TurnModelPin`). Un rechazo del proveedor (`content_filter`, el `refusal` de Claude) es
  un fallo: sin su texto, sin reintento en el mismo modelo, a la reserva. Con un modelo
  que razona el turno **solo añade**: los bloques de razonamiento vuelven, firmados, al
  modelo que los escribió y a ningún otro (`llm.messages_for` sanea por destino), el
  cierre es la misma llamada con `tool_choice: "none"` (sin la nota del cierre y con las
  mismas herramientas, `code_execution` incluida) y el reintento del freno de reservas no
  retira nada. Si GPT-5.6 cae a Sonnet tras llamar a herramientas, Sonnet sigue con
  `thinking: {"type": "between_tools"}` y nada más. Cada caída deja
  `llm.respond_fell_back` con `chosen`, `served` y `reason` (`error`, `timeout`,
  `refusal`, `rate_limit`). Lo prueba en el cable
  `wk/tests/unit/test_respond_profiles_on_the_wire.py`; la batería real, a mano en
  staging, es `apps/worker/scripts/respond_compat.py` (se niega con `--env prod`).
- **Quién clasifica** (requisito 69): Claude Haiku 5.5 (`llm_classify_model`), sin
  razonamiento y con 32 tokens de salida, porque devuelve una palabra. Si falla, cae al
  de responder. La lectura de webs y el sector no lo usan: van con `llm_extract_model`.
- **Quién simula y quién juzga** (`platform_models.py`): el cliente simulado y el juez
  usan `llm_simulation_model` (Terra por defecto, `NEXUS_LLM_CUSTOMER_SIM_MODEL` y
  `NEXUS_LLM_JUDGE_MODEL` mandan). Si el juez es un modelo que respondió en esa
  conversación, juzga otro de la plataforma (`_judge_for`): saltárselo dejaba en «No
  sé» toda prueba sin estado final, y una crítica en «No sé» bloquea la puerta.
- **El plazo del constructor**: `BUILD_CALL_TIMEOUT_S` (120 s) sin reintentos del SDK,
  no los 30 s de un turno de chat, que el borrador no cabe en ellos.
- **Pasadas** (`agent_test_runs`, `services/testing/runs.py`): todas, las
  afectadas, las que no pasan o una. Un cambio de la ficha o del conocimiento deja
  desactualizadas las afectadas y no las pasa (`business/writes.mark_tests_stale`,
  requisito 68.9). Tampoco las marca cambiar el nombre, el tono, el trato o el saludo
  (`agent_spec_drafts._changes_behaviour`, 68.10).
- **Playground** (`api/console/agent_playground.py`): sobre el borrador o una
  versión, con hora y agenda simuladas; el «cliente» lo escribe la propia persona
  del partner. Corre como el agente del canal (sus activaciones de conectores, su
  conocimiento, su memoria) y **nada sale del mundo simulado**
  (`simulation/registry.py`, requisito 20.1): una herramienta de un conector
  (Composio o con `connector_id`) no se ejecuta, tampoco la que solo lee —el
  agente recibe un resultado vacío marcado como simulado y la pantalla «Consultar
  …»—, y «Preguntar antes de escribir» no pregunta al dueño: queda «Preguntar al
  dueño antes de …» y el turno sigue como si hubiera dicho que sí. Lo mismo en
  las pruebas, que usan el mismo registro, y en el playground de antes (dry-run):
  con `dry_run` el grafo nunca abre una consulta al dueño. Si el modelo no responde,
  `200` con `turn.failure: {reason}` (`llm_failed`, `no_model` o `empty_response`): la
  burbuja es el texto de emergencia que recibiría un cliente, se guarda en la
  conversación y la pantalla lo dice, con lo escrito todavía en la caja para repetirlo.
  El error del proveedor se queda en el registro (`simulation.model_failed`).

## 4. La puerta

`services/publishing.py`. Publica solo si:

1. el validador da 0 errores;
2. las pruebas críticas pasan 3 de 3 (si un modelo no respondió,
   `critical_test_untested`), y un agente estructurado tiene al menos una prueba que
   aplica (`no_applicable_tests`, que nadie salta; 65.9);
3. la tasa global no baja más de 2 puntos frente a la versión activa;
4. el aviso de IA está decidido;
5. la revisión no tiene bloqueantes;
6. si la versión cambia de modelo o de calidad, ese cambio está comprobado
   (`model_policy_unchecked`, sección 6).

**La agenda en la revisión** (spec 057, requisitos 3.8, 4.1 y 4.5):

- `no_hours` con un agente que reserva es un **aviso**, no un bloqueo;
- `agenda_not_ready` avisa, con los motivos de `passing.not_ready` y el enlace a
  Reservas, de que al cliente le falta algo para tomar una cita. Se publica igual: el
  turno pasa esas citas a una persona (sección 11);
- `forbids_agenda` avisa cuando el agente tiene `reservas.create` y un texto suyo
  dice que no reserva, que el equipo confirma la cita, que la agenda no está activa o
  que pasa la cita a una persona (`compiler.agenda_forbidding_texts`, con el puntero
  de cada texto, también los disparadores de escalado y la alternativa de las
  habilidades). Es el caso inverso de «promete sin herramienta». Lo que el equipo
  **no** hace («El equipo no confirma las citas») no cuenta: es una negación del
  equipo, no una orden al agente;
- `contradicts_business` compara precios por su importe («30 USD», «$30» y «30,00 USD»
  son el mismo; la moneda no se compara) y horas solo cuando un rango parece una hora
  en una frase del horario (no «de 2 a 4 personas» ni «24 a 48 horas de antelación»),
  contra el horario del negocio, el «Horario propio» de cada sede y las fechas
  especiales (bug `la-revision-ve-lo-que-no-hay`);
- `bookable_without_duration` sigue bloqueando: es un servicio mal dado de alta.

El aviso de IA lo decide una persona en la pantalla del agente, en su bloque
«Aviso de IA» (en el primer mensaje de cada conversación o solo si le preguntan,
con sus palabras opcionales); «Arreglar en el borrador» del hallazgo lo abre. El
constructor no lo deja decidido (16.6). Ninguna propuesta que no sea de una persona
lo cambia: ni el constructor, ni el copiloto, ni una sugerencia, ni una corrección
(70.6). `validate_spec(…, base=)` compara el aviso entero con el del estado sobre
el que se propone. Por eso el copiloto sigue proponiendo y aplicando en un agente
con el aviso ya decidido. Sin `base` (un borrador nuevo), un aviso decidido se
rechaza (70.7).

El validador y el aviso de IA no se saltan nunca. Una prueba normal en rojo deja
«Guardar igualmente»; una crítica, la regresión o un bloqueante solo los salta un
owner, un admin o Auphere, con motivo (queda en la versión y en la auditoría). La
usan los tres sitios que publican: la consola, el admin y la API de partners. Cada
decisión deja el evento `gate.decision` (`outcome`: `published`, `blocked`;
`blocking`: los códigos).

**Lo que ninguna prueba arregla se dice antes de pagarlas**
(`publishing.stopped_before_testing`, requisito 68.13). Si el validador, el aviso de IA o la
calidad sin comprobar cierran la puerta, o la revisión tiene un bloqueante y nadie dio un
motivo para saltarlo, el trabajo `publish` falla con `gate_blocked` sin pasar las pruebas: un
borrador que no puede salir no gasta la pasada que paga Auphere. Con un motivo, las pasa.

**Un cambio que hace Auphere por su cuenta devuelve la pasada** (`billing.return_the_pass`,
requisito 68.14). El paso a Reservas y apagar el módulo reescriben las herramientas del agente
y dejan sus pruebas desactualizadas sin que el cliente haya pedido nada, así que las pasadas de
antes de ese cambio (`agents.tests_pass_returned_at`) ya no cuentan: la siguiente la paga Auphere,
y guardar la vuelve a pasar una vez.

**«No se probó» no es «pasa»**, mientras el agente no haya gastado su pasada: una
versión con pruebas y sin una pasada suya no pasa (`tests_not_run`, en la condición
de las críticas, y se salta como una crítica). Después ya no bloquea: la pantalla dice que
guardar no las repite y queda `version_not_tested` en el veredicto. El último resultado de
cada prueba sigue contando, sea de la versión que sea, así que descartar el borrador o
restaurar otra versión no borra una crítica en rojo; se arregla repitiéndola, sin coste
para el cliente (requisito 68.3). «Guardar» no lo ve nunca —la primera vez, el trabajo `publish` pasa
las pruebas antes de decidir, y `publish-preview` lo dice con `tests_on_save`—; lo ven
quienes publican en la petición: la ruta de antes de la consola (`…/agent/versions/{v}/publish`, que
sigue viva porque el Companion publica por ella) y el panel de operador. El
**promote del panel de operador** es siempre un salto auditado: sin `reason`,
`422 reason_required`; con él, salta lo que salta un owner y el motivo queda en
la versión y en la auditoría. Un agente que crea la API de partners al
aprovisionar pasa la misma puerta (nace sin pruebas).

**Después de publicar**: el siguiente mensaje usa la versión nueva; hay 10 minutos
para deshacer; restaurar una versión la trae como borrador y vuelve a pasar la
puerta. El rollback de antes (consola y panel de operador) solo vuelve a una
versión que estuvo activa: a un borrador responde `409
rollback_target_never_published`, con la ruta para publicarlo. Una versión
activa que deja de serlo guarda cuándo empezó (`promoted_at`, o su creación si
nació activa), y así se distingue de un borrador descartado.

## 5. Estados

Lo que se guarda (`agents.lifecycle`): `draft`, `published`, `paused` con motivo
(`manual`, `no_balance`, `agent_cap`, `client_paused`, `client_archived`) y
`archived`. Lo que se enseña se deriva en un solo sitio
(`services/agent_lifecycle.py`) y lo leen la consola, la lite, la app y el Panel:
`archived`, `paused`, `draft`, `serving` («Atendiendo»), `testing` («En prueba»)
y `ready_no_channel` («Listo · sin canal»). Un canal en pausa o con problemas no
cuenta como canal que atiende.

- Pausar y reanudar: `services/agent_states.py`. Las pausas del sistema
  (`no_balance`, `agent_cap`) las quita el sistema (al volver el saldo, al subir el
  tope o el día 1); las de una persona, solo una persona.
- La regla única de «necesita atención» (`services/attention.py`) la usan la lista
  de clientes, el Panel del partner y ⌘K.

## 6. Calidad y modelo

`services/agent_quality.py` y `api/console/agent_quality.py`: el precio por
mensaje de cada perfil de calidad (a precio, coste × 2,2), los modelos que se
pueden fijar según la UE, lo soberano y lo que permite el partner, y «Comprobar
este cambio» (una pasada de certificación con la política nueva). El router y el
catálogo están en `docs/modelos-y-router.md`.

**Suspendido en la consola** (enmienda del 2026-10-29, requisito 64, D55 y D64):
hasta que la gestión de modelos llegue al panel de operador, la consola no cambia
la política de modelo. `PATCH …/draft` con otra política y `POST …/quality/check`
responden `409 model_policy_managed` (`services/agent_spec/model_policy.py`).

## 7. Conocimiento, integraciones y memoria

- **Capas** (`services/knowledge/`): la del negocio (`agent_id` NULL) la ven todos
  los agentes del cliente; la de un agente, solo él. Búsqueda híbrida exacta
  (texto y vectores `halfvec(1024)` en `knowledge_chunk_vectors`, RRF k=60).
  «Enseñar» (`teach.py`) escribe en la capa que se elija y deja desactualizadas las
  pruebas de quien lo ve. Las fuentes de cada respuesta quedan en `turn_sources`.
- **Activaciones** (`services/activations.py`): una conexión por cliente y una
  activación por agente con su permiso (`read`, `ask_before_write`,
  `read_write`). El turno solo ve las herramientas de sus activaciones;
  «Preguntar antes de escribir» pide permiso al dueño (`tool_approvals.py`). Si la
  política no se puede leer, el turno **no ofrece ninguna herramienta de conector**
  (`ToolPolicy.closed`, `activations.allowed_names`), solo las de la casa
  (`NATIVE_TOOLKITS`, una lista de permitidos). `test_44` barre el catálogo para
  comprobarlo (65.11, D76).
- **Memoria del contacto**: por agente (`agent_memories.agent_id`).

## 8. La consola nueva, la de todos

`services/console_v2.py`. Hasta el 2026-10-29 Auphere la activaba partner a
partner tras un ensayo limpio desde el panel. Ya no: la migración
`0204_console_v2_for_all` la encendió para todos los que seguían en la de antes,
escribiendo antes la audiencia de sus números sin configurar con la regla de la
0192 («Solo mi equipo» con los números de prueba del agente, o «A todos»), y un
partner nuevo nace con ella (`born_on_new_console`). El dinero no se mueve solo:
las bolsas siguen esperando a que el partner confirme el reparto. Los informes
de ensayo que ya había quedan en `migration_reports`.

## 9. El freno de citas (spec 056, requisito 1)

Ninguna respuesta da por hecha una cita sin una reserva real detrás. Vale para
todos los agentes, legados y estructurados, y no depende de lo que diga su
prompt. Vive en `apps/worker/src/nexus_worker/runtime/booking_brake.py` y lo
llama el manejador (`pipeline.make_handler_node`) justo después del bucle ReAct,
dentro del propio manejador: así el reintento conserva los sobres del turno y no
repite herramientas (`tool_once`).

**Cómo decide**, de lo más barato a lo más caro:

1. **Un filtro de palabras** sin tildes, en es, en y pt («confirmad», «reservad»,
   «tu cita», «te esperamos», *booked*, *confirmed*, «seu horário»…), sobre el
   texto y sobre el componente interactivo (cuerpo, botones, filas). Sin acierto,
   la respuesta sale sin ninguna llamada.
2. **Lo que la respalda en este turno**, herramienta a herramienta. La lista sale
   de `capability_names.TOOL_ACTIONS` (reservar o cambiar una cita, sin las
   cancelaciones), más las tres de Google Calendar: desde la enmienda de la 043
   (R11.9) no están en `TOOL_ACTIONS`, porque Google ya no es donde reserva un
   agente, pero un agente que aún no pasó a Reservas las sigue usando (R11.2) y
   su evento respalda la cita (`booking_brake._CONNECTOR_STILL_BOOKS`):
   - `reservas.create` y `reservas.reschedule`: solo con `booking` y sin
     `refused`. Contestan `status: ok` también al rechazar;
   - `reservas.answer_offer`: solo con `result: booked`;
   - `booking.create_appointment` / `modify_appointment`, Google Calendar
     (`CREATE_EVENT`, `QUICK_ADD`, `UPDATE_EVENT`) y `CALENDLY_POST_INVITEE`:
     `status: ok`;
   - una cita que sigue en pie: `reservas.list_mine` con reservas y
     `reservas.confirm_attendance`;
   - el playground de antes (`skipped:dry_run`) y el reintento de un turno
     (`replayed`);
   - **no** respaldan un error, un `approval_*` ni el enlace de un solo uso de
     Calendly (con él reserva el cliente).

   Con una reserva hecha en el turno, la respuesta sale sin cambios y sin
   llamadas. **La agenda simulada** del Playground y de las pruebas
   (`simulation/registry.py`) contesta con la forma de la herramienta de verdad,
   hecha con sus mismos modelos de salida (`booking`, `refused`, `first_fit`…):
   el freno la lee como la del canal. Lo que la agenda rechaza es `refused` con
   `status: ok`, y lo que la herramienta no acepta, un error; las `booking.*`
   retiradas fallan siempre con error, como las de verdad. Una prueba unitaria
   (`apps/worker/tests/unit/test_booking_brake_simulation.py`) pasa al freno los
   sobres que produce el propio registro simulado, para que las dos formas no
   vuelvan a separarse. Desde el fallo
   `la-reserva-del-turno-siguiente-pierde-los-ids` (2026-11-08) también
   `find_slots` y `join_waitlist` tienen la forma de verdad, y el servicio va por
   id o por nombre con los mismos rechazos (`unknown_service`, `ambiguous_service`)
   y las mismas opciones; `docs/reservas.md`, «El agente».
3. **Turnos anteriores de esa conversación**, solo si el filtro acertó: una
   reserva viva de Reservas con su `conversation_id`, o el éxito de un calendario
   conectado o de `booking.*` en sus salidas desde `attended_at`. De Reservas
   manda la agenda: un `ok` viejo pudo cancelarse. En el Playground y en las
   pruebas la agenda es la simulada, cuyas citas no llegan a `reservations`: una
   cita en pie en ella respalda (`MCPRegistry.simulated_booking_stands`, que el
   registro simulado responde con su mundo). Si en este turno se intentó una
   reserva y no salió, lo de antes no la cubre: la respuesta puede estar dando
   por hecha la nueva, y el clasificador recibe la pregunta estrecha (solo cuenta
   una cita hecha, confirmada o cambiada ahora).

   **Spec 080:** también respalda una reserva viva **del cliente de la
   conversación** con un evento `created` o `moved` desde que empezó el ciclo
   (`coalesce(context_from, attended_at)`). La hace quien sea: el agente, una
   persona desde la agenda o el cliente (`booking_brake.load_customer_backing`).
   Es el caso de Jemma del 23-nov: una persona reservó desde la agenda, sin
   conversación en la reserva, devolvió la conversación, y el «gracias» siguiente
   se frenaba. El `customer_id` sale de la fila de la conversación, nunca del
   turno (garantía 8, `tests/isolation/test_080_booking_brake_customer_cycle.py`).
   La reserva de otro cliente, una cancelada o una de antes del ciclo sin moverse
   no respaldan.
4. **Una llamada `classify`**, solo con acierto y sin respaldo: «¿afirma o da a
   entender que hay una cita hecha, confirmada, cambiada o en pie? YES/NO». El
   borrador va como mensaje `user`, como dato (§III). Si la llamada falla, vuelve
   vacía o no dice YES ni NO, cuenta como afirmación: falla cerrado.

**Qué hace** con una afirmación sin respaldo (D1):

- **Un reintento.** El bucle vuelve a correr una vez, con sus herramientas y
  `MAX_TOOL_ITERATIONS` de nuevo, tras la nota `BOOKING_BRAKE_NOTE` como `system`
  (§III): no se envió, resérvala con tu herramienta o di la verdad. **Sin el
  borrador**: como `assistant`, el hilo acabaría en él (LiteLLM sube todo `system`
  a la cabecera de Anthropic) y el modelo lo continuaría. Así el último mensaje
  sigue siendo el del cliente, como con la nota de memoria de herramientas. En un
  turno enrutado sigue dentro de su `turn_budget`; si se agota, es el
  `turn_limit` de siempre.
  **Con un modelo que conserva su razonamiento** (los Claude 5.5, spec 065, T102)
  la nota va como `user`, al final, y no como `system`. Subida a la cabecera, el
  `system` cambiaba a mitad de turno y Anthropic invalidaba el razonamiento
  anterior. La primera batería real recibió `Invalid `signature` in `thinking`
  block` en modo estricto; con `drop_block`, en producción, ese razonamiento se
  habría tirado. Con GPT-5.6 sigue como `system`, como antes.
  Como `user` va **marcada** (`BOOKING_BRAKE_USER_NOTICE`, T104): dentro de
  `<aviso_del_sistema>` y con una línea que dice que el cliente no lo escribió ni lo
  ve. Sin la marca, Claude la tomaba por palabras del cliente y le contestaba («No
  la he reservado dos veces»).
- **Si vuelve a afirmarla**, la conversación pasa a una persona:
  - el contacto recibe la frase de traspaso, sin componente interactivo;
  - `turn_failure = {"kind": "handoff", "reason": "booking_unbacked"}`;
  - el despachador la marca con `booking_unbacked` («El agente dio por hecha una
    cita que no existe»). No es de puerta: no la libera la siguiente respuesta;
  - con Bandeja, el agente se calla en esa conversación, como en un bucle de
    Recepción. Sin Bandeja, avisa a los destinatarios de escalado del canal.
- **El revisor de resultados** reescribe sin herramientas: si su borrador nuevo
  afirma una cita sin respaldo, sale `GRADER_FALLBACK_RESPONSE`.

**Constancia, sin texto**: el evento de log `booking.brake` (`retried`,
`handed_off`, `classifier_failed_closed`, `grader_fallback`) y, en un turno de
canal, la fila de auditoría `agent.booking_brake` con el agente, el turno y el
resultado (`specs/047-la-fabrica-de-agentes/contracts/events.md` §2, §4 y §5). La
llamada `classify` se cobra dentro del turno, como la del clasificador del grafo
(`docs/modelos-y-router.md`).

**Pruebas**: `apps/worker/tests/unit/test_booking_brake.py` (el filtro y la tabla
de respaldo), `test_pipeline_booking_brake.py` (el reintento y el traspaso, en un
agente legado y en uno estructurado), `apps/api/tests/integration/test_booking_brake_turn.py`
(el turno de verdad: motivo, auditoría, cobro y pausa con Bandeja),
`apps/api/tests/isolation/test_056_booking_brake_same_conversation.py` (garantía
8: solo cuenta la conversación del turno), `test_080_booking_brake_customer_cycle.py`
(garantía 8: del cliente, solo lo suyo y solo en el ciclo) y la de punta a punta
contra staging, `apps/api/tests/release/test_booking_brake_staging.py`
(`manual_only`, no corre en CI).

### Herramientas por intención (spec 080, requisito 2)

La etiqueta del clasificador elige qué herramientas recibe el turno
(`pipeline._INTENT_CATEGORIES`). Desde la 080, **saludo o agradecimiento
(`fallback`) y paso a persona (`escalate`) llevan también las nueve `reservas.*`**
que tenga el agente: catálogo, disponibilidad, citas del cliente, reservar, mover,
cancelar, confirmar, lista de espera y ofertas.

Antes, un «gracias» justo después de que una persona reservara, o un «no me gusta
cómo me atiende X» a mitad de reserva, dejaban al agente sin poder comprobar ni
seguir, y solo podía pasar a una persona (Jemma, 2026-11-23). Ahora es la regla del
negocio, leída por el modelo, la que decide si se pasa a una persona.

Lo que no cambia:

- La lista blanca del agente sigue siendo el techo (garantía 2).
- Los conectores siguen fuera de `escalate`.
- `info` sigue sin `find_slots`.

**Coste:** no hay llamadas nuevas. Esos turnos llevan más definiciones de
herramientas: en Jemma, unos 2.400 tokens de entrada más, casi todos en caché. Se
cobran en la bolsa del cliente como cualquier turno.

**Pruebas:** `apps/worker/tests/unit/test_intent_tool_filter.py`, con el barrido de
`VALID_INTENTS` contra la lista blanca.

## 10. Una corrección para todos los agentes (spec 056, requisito 9)

Cuando la persona del cliente corrige una **regla** con «Todo el negocio», la
propuesta no va solo al agente que respondió: va a cada agente activo del
cliente (`published` o `paused`, sin mirar el papel), con su propuesta y su
prueba, unidas en un lote por `inbox_corrections.batch_id` (migración 0226). El
agente en el que la regla no valida se salta (`after_json.skipped`). El partner
ve el lote en las mejoras de cada agente (`batch {id, agents_count}`) y lo
acepta o lo descarta de una vez
(`POST /console/clients/{ref}/corrections/{batch_id}/accept|discard`). Con «Solo
este agente», una propuesta y sin lote, como antes. El detalle está en
[consola-lite.md](consola-lite.md#la-bandeja-dice-la-verdad-spec-056-requisitos-6-a-9-y-133).

**Pruebas**: `apps/api/tests/integration/improvement/test_corrections.py` y
`test_correction_batch_accept.py`.

## 11. La agenda sin terminar en el turno (spec 057, requisito 4)

Un agente con la agenda puede publicarse aunque al cliente le falten horario,
profesionales, servicios reservables o capacidad (decisión de Luis del 2026-11-09).
Mientras falte algo, el turno no dice «no hay huecos»: pasa la cita a una persona.

- **Dónde**: `pipeline.make_handler_node`, después de `allowed_names` y antes de
  `get_openai_tools`. Si el agente tiene alguna `reservas.*`, se lee
  `passing.agenda_ready` una vez por turno con la RLS del cliente (encendido y con modo,
  horario y, en Servicios, alguien en activo y algún servicio reservable; en Aforo,
  plazas y franjas). No va en el bundle cacheado: ninguna escritura de Reservas lo
  invalida, y el agente tiene que reservar desde el mensaje siguiente a completar
  Reservas, sin publicar.
- **Qué**: salen `find_slots`, `create`, `reschedule`, `join_waitlist` y
  `answer_offer` (de lo que ve el modelo y de la lista blanca de `dispatch`); quedan
  `services`, `list_mine`, `cancel` y `confirm_attendance`. Una nota de sistema, en
  cualquier intención, pide el servicio, el día y la hora, llamar a
  `escalate.escalate_to_human` y decir que el equipo escribirá para confirmar la hora,
  sin «tu cita» (lo leería el freno). Registro: `agenda.not_ready_turn`.
- **Sin herramienta de pasar** y con intención `book`: traspasa el runtime antes del
  bucle, sin llamar al modelo, con `waiting_reason = agenda_not_ready` (0229), que
  silencia al agente en esa conversación como `booking_unbacked`. Con otra intención,
  una nota dice que ahora no puede dar citas por aquí.
- **Si la lectura falla**, el turno sigue con todas las herramientas
  (`agenda.ready_read_failed`): el servidor de Reservas ya rechaza lo imposible.
- **El freno de citas** (sección 9) no salta en un turno que pasó la cita a una
  persona con la agenda sin terminar, ni en el manejador ni en la reescritura del
  revisor (`booking_brake.backs(agenda_pending=…)`).
- **Simulación**: el playground usa la agenda real del cliente (así lo verá); la suite
  del agente la da por lista (`run_turn(agenda_ready=True)`), porque mide su texto y no
  la configuración del cliente.

