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
- **Validador** (`services/agent_spec/validator.py`): errores que bloquean la
  puerta (herramientas desconocidas, límites, coherencia con la ficha) y avisos.
- **Revisión** (`services/agent_spec/review.py`, `api/console/agent_review.py`):
  incoherencias como prometer algo sin la herramienta que lo hace; las
  bloqueantes paran la puerta.

## 2. El constructor

Todo lo largo es un **trabajo** (`jobs`, `services/jobs.py`) que corre el worker
(`wk/jobs/handlers/*`) y la consola sigue por `GET /console/jobs/{id}`.

- **Borrador** (`services/builder/agent_draft.py`, `POST
  /console/clients/{ref}/agents/draft-jobs`): «Generar borrador», «Desde una
  plantilla» o «En blanco». Lee la ficha del negocio y devuelve un AgentSpec, sus
  preguntas abiertas, las integraciones que necesita y su batería de pruebas.
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
- **La agenda solo con Reservas encendido** (D67): `validator.load_context` da las
  `reservas.*` por conectadas solo si el cliente tiene el módulo Reservas
  (`ClientAccess.reservas_on` y su modo elegido). Apagado, cuentan como sin
  conectar y sin activación: el constructor las ve «SIN ACTIVAR», `sanitize` las
  quita (`tool_not_connected`) y la puerta las rechaza; el playground y las pruebas
  responden «Reservas no está activo», como el turno.
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
- **Una pasada viva por agente** (T217): con un trabajo `tests` del agente en cola
  o en marcha, `POST …/test-runs` la devuelve (`202` con su `job_id`, su `run_id`
  y cuántas pruebas lleva) y no encola otra, como «Volver a leer».
- **El coste, antes** (61.8): `POST …/test-runs` con `dry_run: true` responde `200`
  con la estimación (`services/testing/estimate.py`: de media 4 turnos del agente,
  4 mensajes del cliente simulado y el juez, por 3 pasadas, a precio) sin encolar
  nada. Un precio que no se conoce no es cero: `estimate: null` y `unknown_prices`.
- **Pasadas** (`agent_test_runs`, `services/testing/runs.py`): todas, las
  afectadas o una; un cambio de la ficha deja desactualizadas las afectadas y las
  vuelve a pasar en segundo plano en los agentes publicados
  (`business/writes.mark_tests_stale`). Si esa pasada deja pruebas en rojo, el
  partner recibe `agent.tests.failing` (una vez por agente y día,
  `wk/jobs/handlers/agent_tests.tell_failing`, requisito 13.7).
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
  con `dry_run` el grafo nunca abre una consulta al dueño.

## 4. La puerta

`services/publishing.py`. Publica solo si:

1. el validador da 0 errores;
2. las pruebas críticas pasan 3 de 3, y un agente estructurado tiene al menos una
   prueba que aplica (`no_applicable_tests`, que nadie salta; 65.9);
3. la tasa global no baja más de 2 puntos frente a la versión activa;
4. el aviso de IA está decidido;
5. la revisión no tiene bloqueantes;
6. si la versión cambia de modelo o de calidad, ese cambio está comprobado
   (`model_policy_unchecked`, sección 6).

El aviso de IA lo decide una persona en la pantalla del agente, en su bloque
«Aviso de IA» (en el primer mensaje de cada conversación o solo si le preguntan,
con sus palabras opcionales); «Arreglar en el borrador» del hallazgo lo abre. El
constructor no lo deja decidido (16.6).

El validador y el aviso de IA no se saltan nunca. Una prueba normal en rojo deja
«Guardar igualmente»; una crítica, la regresión o un bloqueante solo los salta un
owner, un admin o Auphere, con motivo (queda en la versión y en la auditoría). La
usan los tres sitios que publican: la consola, el admin y la API de partners. Cada
decisión deja el evento `gate.decision` (`outcome`: `published`, `blocked`;
`blocking`: los códigos).

**«No se probó» no es «pasa»**: una versión con pruebas y sin una pasada suya no
pasa (`tests_not_run`, en la condición de las críticas, y se salta como una
crítica). «Guardar» no lo ve nunca —el trabajo `publish` pasa las pruebas antes
de decidir, y su vista previa no lo cuenta—; lo ven quienes publican en la
petición: la ruta de antes de la consola (`…/agent/versions/{v}/publish`, que
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
  «Enseñar» (`teach.py`) escribe en la capa que se elija y vuelve a pasar las
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
