# Investigación: La agenda desde el agente (spec 057)

Decisiones de diseño. Cada una con lo que se eligió, por qué y lo que se descartó.
Las rutas son del repo a fecha 2026-11-09 (`develop` `ac2fc553`).

## Lo que se encontró en staging (Spa Jemma, 2026-11-08 y 2026-11-09)

Leído de los registros de `/nexus/staging/{api,runner}` y de la base de staging en solo
lectura (`ecs exec` en `nexus-staging-api`). Detalle en la nota de KB
`[[research/2026-11-09-agenda-desde-el-agente]]`.

1. **v1 sin agenda.** El constructor escribió el agente a las 21:47 UTC con Reservas apagado.
   `validator.load_context` cuenta `reservas.*` como sin conectar y `ctx.available_tools()` no las
   da: el modelo las vio «SIN ACTIVAR, no la uses» (`agent_draft._catalog_lines`).
2. **Encender Reservas no llegó al agente.** A las 22:32 `client_access.set_access` →
   `reservations.admin.apply_choice` → `passing.pass_to_reservas(every_agent=True)` preparó la v2
   con las 9 `reservas.*` en `tools` y en `spec.tools`, sin publicar.
3. **El aviso desactualizado.** `agent_draft_routes._spec_and_missing` suma
   `builder_missing(target)` (lo que el constructor guardó en `policies.builder`), que se copia a
   cada versión y no se recalcula.
4. **Con las 9 publicadas, siguió sin reservar (2026-11-09, 11:00 UTC).** Los turnos `book`
   llevan las herramientas (el prompt pasa de ~5.700 a ~7.800 tokens), pero el modelo no las usa:
   la v3 conserva todo lo que el constructor escribió para un agente sin agenda.
   - el procedimiento «Recoger una solicitud de cita» («No ofrezcas huecos ni confirmes la reserva… Pasa la conversación al equipo»);
   - el disparador de escalado «cuando solicitan crear, cambiar o cancelar una cita, porque la agenda no está activa»;
   - dos reglas («Una solicitud de cita no es una reserva confirmada», «No afirmes que una cita fue cambiada o cancelada hasta que el equipo lo confirme»);
   - dos habilidades sin integración cuya alternativa es pasar al equipo (`appointment_request_intake`, `appointment_change_or_cancellation_intake`), que la consola no deja editar (`EDITABLE` en `builder-model.ts:216`);
   - dos respuestas de «Lo que sabe este agente» y la política de cancelación de la ficha.

   El texto del partner, que sí manda reservar, pierde frente a la orden más estricta.
5. **La zona horaria está bien.** `tenants.timezone` y `business_profiles.timezone` son
   `America/Caracas` en los 10 clientes de staging. El «esa hora ya pasó» de las 07:00 locales
   no sale del reloj del turno (`turn_clock.now_note`); sin traza del turno no se puede saber más.

## R1 · El interruptor del alta enciende Reservas antes de construir

**Decisión.** `DraftJobIn` gana `agenda: bool | None` y `reservas: ReservasChoiceIn | None`
(modo y tipo de aforo). Si `agenda` es verdadero y Reservas está apagado, `start_draft` lo
enciende **en la misma petición, antes de encolar el trabajo**, con el servicio común del
requisito 7 (R5). Si falla, responde el error y no crea trabajo ni agente (1.5).

`DraftRequest` gana `agenda: bool`. El constructor:
- **en el mensaje al modelo** dice si el agente gestiona citas (`build_messages`): con agenda,
  que use las `reservas.*` y escriba cómo reservar, mover y cancelar; sin ella, que no las use;
- **en `sanitize`** lo hace cumplir: con agenda añade las 9 que estén disponibles y, si ningún
  procedimiento usa `reservas.create`, el procedimiento fijo de `offline_output`; sin agenda quita
  toda `reservas.*` (1.6, 1.7).

**Por qué en la API y no en el trabajo.** El trabajo corre aparte y su contexto
(`load_context`) se lee al empezar: encender dentro del trabajo obligaría a releerlo y dejaría un
agente a medias si fallara. En la petición, el error se dice al momento y no hay nada que limpiar.

**Descartado.** Dejar que el modelo decida solo por la descripción: es lo que falló con Spa
Jemma (con la agenda «SIN ACTIVAR» el modelo escribió la alternativa).

**`agenda: None`** (clientes antiguos de la API, plantillas sin tocar): se deduce como hoy, por
lo que el constructor proponga; nunca enciende Reservas.

## R4 · Reservas sin terminar: filtro y nota en el turno, leído en cada turno

Informe del runtime (2026-11-09):

- **Dónde.** `pipeline.make_handler_node`, entre `allowed_names(...)` y `get_openai_tools(...)`
  (`pipeline.py:1816-1822`). Es el mismo grafo para canal, playground y pruebas
  (`simulation/runner.run_turn`), y la tupla resultante es también la lista blanca de
  `registry.dispatch`: lo que se quita ni se ve ni se ejecuta.
- **Qué.** Si el agente tiene alguna `reservas.*` y la agenda no está lista, se quitan
  `reservas.find_slots`, `create`, `reschedule`, `join_waitlist` y `answer_offer`. Se dejan
  `services`, `list_mine`, `cancel` y `confirm_attendance`, que sirven con lo que ya hay. Se
  inserta una nota de sistema con el patrón de `_HAND_OFF_NOTE` (`_agenda_not_ready_note_applies`):
  pide servicio, día y hora, llama a `escalate.escalate_to_human` y dice que el equipo escribirá
  para confirmar la hora. La condición es tener la agenda, no la intención: una petición de cita
  clasificada `info` también debe pasar.
- **Cuándo se lee.** En cada turno, con la RLS del cliente, como `_load_tool_policy`. No en el
  bundle cacheado: ninguna escritura de Reservas publica `nexus:agent_config:promote`, así que el
  bundle se quedaría viejo y 4.3 («desde el mensaje siguiente») no se cumpliría.
- **Con qué coste.** `passing.not_ready` recorre 7 días por persona y servicio (`service_warnings`).
  Para el turno se añade `passing.agenda_ready(session)`: encendido + modo elegido + horario + (en
  servicios) alguien en activo y algún servicio reservable, o (en aforo) plazas y franjas. Son
  `session.get` y dos `EXISTS`. `not_ready` sigue siendo la versión completa para la revisión y la
  pantalla. Si la lectura falla, el turno sigue con las herramientas (falla abierta: el servidor de
  Reservas ya rechaza lo imposible).
- **Sin herramienta de derivar.** Si el agente no tiene `escalate.escalate_to_human`, el runtime
  traspasa por el camino del freno de citas (`turn_failure = {"kind": "handoff", "reason":
  "agenda_not_ready"}`), con el motivo nuevo en `_ROUTER_REASONS`, `_SILENCES_THE_AGENT`
  (`dispatcher.py:482-488`) y `contracts/events.md`.
- **El freno de citas.** «el equipo te confirmará tu cita» activa `might_claim`
  (`booking_brake.py:125-131`). La nota pide decir que «el equipo te escribirá para confirmar la
  hora», sin «tu cita». Y el freno no salta en un turno que llamó a `escalate` con la agenda sin
  terminar (`backs`, `booking_brake.py:211-236`).
- **Pruebas del agente.** La suite simula una agenda lista: lo que mide es el texto del agente,
  no la configuración del cliente. Si leyera la real, un cliente sin profesionales suspendería las
  pruebas críticas de reservar y la puerta bloquearía, que es lo que Luis descartó (decisión 1).
  El playground sí lee la real: «así lo verá su cliente». `run_turn` recibe `agenda_ready` (real en
  el playground, `True` en la suite) y el handler lo usa en vez de leerlo.
- **La puerta.** `review.py` deja de bloquear por `no_hours` cuando el agente reserva: pasa a
  `warn`, y se añade un hallazgo `agenda_not_ready` (`warn`) con los motivos de `not_ready` y el
  enlace a Reservas (4.1). `bookable_without_duration` sigue bloqueando: es un servicio mal dado de
  alta (043, requisito 14), no Reservas sin terminar (4.5).

**Lo que cambió al implementarlo** (informe del worker, 2026-11-09):
- el traspaso del runtime sin herramienta de pasar va **antes** del bucle, sin llamar al modelo
  (como `no_model`), con la frase de traspaso de siempre: correr el modelo para tirar su
  respuesta costaría una llamada y podría decir «no hay huecos»;
- un agente sin herramienta de pasar recibe otra nota en las intenciones que no son `book`
  («ahora no puedes dar citas por aquí»), en vez de pedirle llamar a una herramienta que no tiene;
- la agenda dada viaja en un `ContextVar` (`pipeline.agenda_readiness`, como
  `simulated_clock`), y `run_turn(agenda_ready=…)` lo pone;
- el motivo `agenda_not_ready` entra en `WAITING_REASONS` y en `ck_conversations_waiting_reason`
  (0229), con su texto en la Bandeja de la consola y de la app;
- la reescritura del revisor (`_rewrite_claims_a_booking`) también sabe si la agenda está lista.

**Una conversación que ya pasó a una persona** se queda con la persona (Bandeja,
`inbox_lifecycle.mark_waiting`): 4.3 vale para las conversaciones nuevas o las que el equipo
devuelva al agente. Es lo que ya pasa hoy y no se toca.

**Descartado.**
- Meterlo en `activations.tool_policy`: su contrato es de conectores, si falla no quita lo de la
  casa, no puede añadir una nota y mira la versión activa, no el borrador del playground.
- Una guarda en el servidor MCP (`Create.run`): sería una segunda defensa, pero no hace que el
  agente pida los datos y pase a una persona.

## R3 · La propuesta de texto: `proposals` del constructor, por un trabajo medido

Informe de propuestas (2026-11-09): las cuatro vías que hoy proponen cambios a un borrador
acaban en `proposals` (`db/models/agent_spec.py:68-93`, RLS forzada por `app.tenant_id`), con
`apply`/`reject` que revalidan y escriben por `write_spec` (`api/console/agent_builder.py:441-538`)
y la lista `ProposalList` de la consola (`components/builder/proposals.tsx`).

**Decisión.** Al cambiar la agenda de un agente estructurado se encola un trabajo
`agenda_text` que escribe **una** propuesta `agent_spec_patch` de autor `builder`, con un
`summary` que dice qué cambió («Activaste la agenda: así cambian sus citas»):

- **Qué toca.** `/procedures`, `/rules`, `/escalation`, `/skills`, `/instructions` y
  `/services/faqs` (lo que solo sabe el agente: `compiler._agent_layer`). Nunca `/tools`,
  `/identity`, `/voice`, `/ai_disclosure` ni `/model_policy`. Las habilidades entran aunque la
  consola no las edite (`EDITABLE` no las tiene): con Spa Jemma eran dos de las seis piezas que
  mandaban la cita al equipo.
- **Cómo.** El modelo del constructor (`role="build"`) recibe el AgentSpec ya cambiado, la lista
  de lo que el agente puede hacer (`available_lines(ctx, only=spec.tools)`) y la instrucción de
  reescribir solo lo que habla de citas. La salida pasa por lo mismo que el copiloto: el
  validador, `missing.strip_doc` y el rechazo de promesas nuevas sin herramienta
  (`copilot_model.py:106-113`), y además la comprobación nueva de 3.8 (que no quede texto que
  prohíba la agenda). Si no pasa, no hay propuesta y la pantalla lo dice (3.5).
- **Sin modelo** (`llm_use_inmemory`): el procedimiento fijo de `offline_output` y quitar los
  textos que 3.8 marca. Es también el respaldo si el proveedor no responde (3.5).
- **Dónde corre.** En el worker, como `agent_draft`: `JOB_KINDS` gana `agenda_text` (CHECK
  `ck_jobs_kind` en una migración) y un manejador en `jobs/handlers/agenda_text.py`, dentro de
  `usage_turn(source=SOURCE_BUILDER)`. Así cuenta en `partner_build_budget`, nunca en la bolsa del
  cliente (3.6), y lo frena `require_build_room` al encolar.
- **Cuánto vive.** `proposal_state` caduca a los 15 minutos para todos. Esta propuesta espera al
  partner: `propose(..., ttl=...)` gana un plazo por llamada y la de la agenda vive 7 días. Si el
  borrador cambia, queda `stale` como cualquier otra (la huella es el AgentSpec).
- **Antes y después.** `GET …/proposals` añade a cada operación el valor de ahora en ese puntero
  (`before`), calculado al leer sobre el borrador. La consola agrupa por bloque con
  `blockOfPointer`. Los nombres de campo no son de cuerpo de mensaje (`test_console_scope.py`,
  regla 3).
- **Editar.** «Editar» aplica la propuesta y abre el editor del primer bloque cambiado. El
  borrador no está publicado: editar después de aplicar es lo mismo que editar antes, y reutiliza
  el editor de bloques en vez de un segundo editor dentro de la propuesta. «Descartar» es
  `reject`. Nada se aplica solo (3.3).
- **Al apagar la agenda** (3.2), el mismo trabajo con la instrucción contraria. Y como apagar una
  `reservas.*` que usa un procedimiento hoy da `422 tool_in_use`
  (`capabilities_client._refuse_if_in_use`), apagar la agenda entera **no** pasa por esa
  comprobación: quita las 9 y deja que la propuesta quite los procedimientos. Mientras no se
  acepte, 3.8 y el aviso de promesas lo dicen.

**La ficha (3.7).** La propuesta nunca toca la ficha: es de todos los agentes del cliente. Si una
política o una respuesta de la ficha dice que el equipo confirma las citas (los mismos patrones de
`forbids_agenda`), la propuesta lleva `diff.ficha_links = [{"section": "policies", "label": "Cancelación"}]` (sección y
nombre de la política o de la pregunta frecuente)
y la consola lo enseña con un enlace a Negocio. El nombre del campo no es de cuerpo de mensaje
(`notes` está prohibido en `test_console_scope.py`).

Una política cuyo nombre trata de citas (cancelar, cambiar, reservar) se lee frase a frase
como de la cita: la de Spa Jemma dice «el equipo confirmará si el cambio está disponible»,
sin la palabra «cita».

**Tope.** 270 s, como `agent_draft`. Si se agota, el respaldo sin modelo.

**Agentes de instrucciones libres** (2.7): no tienen bloques; no hay propuesta. El aviso de
promesas sigue avisando.

**Descartado.**
- Las Mejoras (`/improvements`): atadas a la semana, al tema, a 5 conversaciones y 5 contactos,
  a la prueba obligatoria y a 30 días de supresión.
- El copiloto tal cual: no se mide (`agent_copilot.py`, sin `usage_turn` ni `require_build_room`)
  y tiene prohibido `/tools`; además es síncrono.
- Reescribir solo con reglas fijas (sin modelo): no sabe qué frase del partner habla de citas.
  Queda como respaldo.

## R6 · El aviso «No tenemos herramienta para» se recalcula al leer

**Decisión.** `builder_missing(target)` deja de sumarse tal cual en `_spec_and_missing`: cada
nota se contrasta con la versión que se lee.
- `kind="action"`: se quita si `actions_of(spec.tools)` cubre `promise.needs` (la misma prueba que
  `uncovered_promises`).
- `kind="module"` (`reservas`): se quita si `reservas_enabled`.
- `kind="integration"`: se quita si la integración está conectada (`ctx.tools[...].connected`).
- `kind="tool"` (`tool_unknown`): se queda.

Se hace en la lectura, no reescribiendo `policies.builder`: los agentes que ya existen se ven bien
sin migración (6.4), y la revisión de publicar, que no lee esa nota, ya dice lo mismo (6.2).
`write_spec` deja de arrastrar las notas que ya no aplican al fusionar (`missing.merge` con lo
que siga faltando).

**«Gestionar citas»** (6.3): la consola añade la acción a los elementos con `key` `book` o
`modify_booking` cuando Reservas se ofrece al cliente; lleva a la fila de la agenda en Conectores
(requisito 2).

## R3.8 · La revisión avisa cuando el texto prohíbe la agenda

**Decisión.** `compiler.incoherences` gana el código `forbids_agenda`: el agente tiene
`reservas.create` y algún texto (`_texts(spec)`, más los disparadores de escalado y la alternativa
de cada habilidad) dice que no reserva, que el equipo confirma la cita, que la agenda no está activa
o que pasa la cita a una persona. Patrones en español, como los de `PROMISES`, probados con las
frases literales de Spa Jemma. En `review.py` sale como `warn` con el puntero de cada texto y la
acción de pedir la propuesta del requisito 3. Es `warn` y no `block`: una frase como «si la clienta
lo pide, pásala a una persona» es legítima y el patrón puede acertar de más.

## R7 · Encender Reservas desde un agente: un servicio bajo la RLS del cliente

Informe de la consola (2026-11-09): `client_access.set_access` reescribe `enabled` y `modules`
enteros, cierra sesiones y toca `console_auth.*`, por eso su ruta usa `declare_tenant` y no
`client_scope`. `reservations.admin.as_tenant` hace `RESET ROLE` en su `finally`: dentro de
`client_scope` devolvería la petición al rol de conexión. `auto_pass.turn_on_reservas`
(`auto_pass.py:157-217`) ya añade solo `reservas` con `ordered_modules(also=…)`, deja `enabled`
como estaba y corre bajo la RLS (`nexus_app` puede escribir `client_access`: política FOR ALL de
0147 y privilegios por defecto de 0004).

**Decisión.** `services/reservations/turn_on.py: turn_on_from_agent(session, *, tenant_id,
partner_id, choice, actor, origin_agent_id, now)`:
- corre **dentro** de `client_scope` / `tenant_scoped_session` (rol `nexus_app`, `app.tenant_id`
  del contexto): sin `as_tenant`, sin `set_access`, sin `read_access`;
- el partner sale de `scope.mapping` (el `PartnerTenant` ya resuelto), nunca del cuerpo;
- toma `pg_advisory_xact_lock` por cliente: dos agentes que encienden a la vez no chocan en la
  clave de `reservation_settings`; el segundo ve el módulo encendido y no hace nada;
- añade `reservas` a `modules` (crea `ClientAccess` con `enabled=False` si no hay fila), llama a
  `apply_choice(prepare_agents=False)` y después a `pass_to_reservas(scope="givers",
  exclude={origin_agent_id})` (R5);
- audita `client_access.updated` con `{"modules", "from_agent", "mode", "capacity_kind"}` y el
  actor `console:<correo>` (7.5).

La parte común con `turn_on_reservas` (añadir el módulo y auditar) se extrae a una función que
usan los dos.

**Permiso.** Las rutas que lo llaman exigen `agents:write` (owner, admin y builder). Apagar no
tiene ruta desde el agente (7.4).

**Descartado.** Llamar a `set_access` desde el agente: exige `client_access:manage`, reescribe
`enabled` y no puede correr bajo `client_scope`.

## R5 · Encender Reservas solo prepara a quien da citas

**Decisión.** `pass_to_reservas(every_agent=True)` pasa a `pass_to_reservas(scope="givers",
exclude=…)`. `prepare_agent_versions` gana el filtro `passing.gives_appointments(cfg)`:
- `version_books_outside(cfg)` (reserva en un conector) o `version_names_booking(cfg)`
  (`booking.*`), como hoy;
- o su texto promete citas: `compiler.promises_in` con las claves `book` o `modify_booking` sobre
  `_texts(spec)`, o sobre `system_prompt_rendered` si no hay AgentSpec.

Lo usan `apply_choice` (Acceso, panel y desde el agente) y nada más; el paso automático del
despliegue no cambia (`only_booking`).

**El aviso (5.3).** «Preparada» = el borrador tiene `reservas.create` y la versión activa no.
- `AgentOut` (`agents_list.py:40-58`) gana `agenda: "none" | "on" | "prepared"`. La tarjeta
  (`agent-cards.tsx:184-227`) pinta el aviso con la acción de revisar.
- La ficha del agente lo lee de `GET …/agenda` (R2).
- Se calcula de las versiones, no de `created_by`: `admin_view` solo cuenta lo de
  `operator:%` (`admin.py:219`) y lo preparado desde la consola no salía. Ese filtro se corrige
  en la misma tarea, para que la pestaña Acceso diga lo mismo.

## R2 · «Agenda (Reservas)» en Conectores: rutas propias, diálogo compartido

El diálogo de herramientas (`ConnectorToolsDialog`) recibe `load` y `save` inyectados. `save`
(PUT `/capabilities?agent=`) sirve tal cual. `load` no: `GET …/integrations/{slug}/tools` exige
una fila `Connector` y las `reservas.*` no tienen conector (0173). La fila del conector necesita
`connection` y `activation`, que la agenda no tiene.

**Decisión.**
- `GET /clients/{ref}/agents/{agent_id}/agenda` (`agents:read`): si se ofrece, si el módulo está
  encendido y con qué modo, si está listo (`not_ready` completo) y qué falta, si la agenda está
  en el borrador y en la versión publicada, la propuesta pendiente y el modo sugerido.
- `PUT /clients/{ref}/agents/{agent_id}/agenda` (`agents:write`), `{enabled, reservas?}`:
  enciende el módulo si hace falta (R7); escribe las 9 de una vez en el borrador
  (`capabilities_client._set_spec_tools`, que generaliza `_set_spec_tool` a un conjunto: una
  validación, una escritura); y encola la propuesta (R3).
- Al apagar quita las 9 y además su nombre de `procedures[].tools`, para que el AgentSpec siga
  validando. Las frases las quita la propuesta.
- Si el modo falta con el módulo apagado: 422 `reservas_mode_required`. Si pasa del máximo:
  422 `too_many_tools` con `max` (2.6). Sin sitio en el presupuesto de construcción, las
  herramientas cambian igual y la respuesta dice `proposal: "build_budget_exhausted"` (3.5).
- `GET …/agenda/tools?lang=`: la misma forma que `ConnectorToolsOut`, para el diálogo.
- En la consola, `AgendaRow` es un componente propio, primero de la lista
  (`agent-connectors.tsx:426-450`), que reutiliza `ConnectorToolsDialog` con su `load`.
  `NEVER_CONNECT` (`builder-model.ts:188`) se queda: la agenda sigue sin «Conectar».

**Descartado.** Una fila `Connector` falsa para Reservas: arrastra conexión, permisos y ajustes
que no existen, y el validador la trataría como conector.

## R1 (cont.) · El alta en la consola

- `DraftOptionsOut` gana `agenda: {offered, module_on, mode, capacity_kind, suggested_mode,
  suggested_kind}`, y `TemplateOptionOut` gana `books` (de `template_tools`).
- El modo sugerido sale de `auto_pass.choose_mode` (restaurante → aforo `restaurant`; el resto,
  servicios), envuelto en `reservations/turn_on.py: suggested_choice(session)` (no en
  `settings.py`: `auto_pass` importa `admin`, que importa `settings`, y sería un ciclo). La pestaña Acceso no sugiere nada hoy, y no cambia.
- `builder-new.tsx` pinta el interruptor bajo «¿Qué tiene que hacer?» y, con el módulo apagado,
  los dos modos (y el tipo de aforo) como en `ReservasFields` (`client-console-card.tsx:267-350`),
  que se extrae a un componente compartido.
- El interruptor se enciende solo, mientras nadie lo toque, si la descripción coincide con
  `BOOKING_WORDS` (la misma expresión que `agent_draft._BOOKING`) o la plantilla tiene `books`.
- «Desde una plantilla» y «En blanco» son síncronos: el encendido va antes de
  `draft_from_template` / `_blank_spec`, en la misma transacción. Con la agenda apagada, una
  plantilla pierde sus `reservas.*` y su nombre en `procedures[].tools`. Con la agenda encendida,
  «En blanco» lleva las 9 y el procedimiento fijo.
- `partner_provisioning.py:255-262` (que rechaza una plantilla con `reservas.*` y el módulo
  apagado) no se toca: es el alta de un partner nuevo, no la de un agente.


## Revisión de seguridad (`/cso` y `tenant-security-audit`, 2026-11-09)

Sin hallazgos altos ni críticos. Los dos LOW, arreglados en el mismo cambio:

- **Coste**: cada cambio encolaba un trabajo `agenda_text`. Ahora hay como mucho uno en cola por
  agente (`agenda._queued`); el trabajo deriva la dirección del borrador, no de su entrada
  (`propose_agenda_text`), y vuelve a mirar la partida de construcción antes de llamar al modelo
  (sin sitio, el respaldo sin modelo).
- **Migración 0229**: `lock_timeout = '5s'` y los `VALIDATE` en `autocommit_block`, fuera de la
  transacción de `env.py`, para no retener el candado sobre `conversations` (la 0223 tenía el
  mismo hueco).

Para Luis (información, no fallos): un builder puede volver a encender Reservas después de que un
owner o admin lo apagara en Acceso (lo permiten 7.1 y 7.4; queda auditado con la persona y el
agente); la propuesta de texto lee la ficha, que puede venir de la web del cliente, vallada y
siempre revisada por una persona antes de aplicarse.

## Revisión de UI (puertas del workspace, 2026-11-09)

Estática (Playwright no conectó). Tres bloqueantes que se arreglaron: el antes y el después por
bloque se pintaba como JSON cortado; la fila no dejaba pedir la propuesta cuando no había trabajo
ni propuesta abierta (el caso de Spa Jemma); y en inglés el nombre accesible de Activar/Desactivar
no contenía su texto (WCAG 2.5.3). `turnos` cuenta en plural, en la consola y en la API.

`no_staff` y `no_capacity` no tienen pantalla del partner: los completa el cliente en Reservas ›
Ajustes, y la consola lo dice con texto, sin enlace (4.1 queda así para esos dos motivos).
