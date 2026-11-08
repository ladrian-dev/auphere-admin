# Reservas

Spec [`043-reservas`](../specs/043-reservas/spec.md). Un módulo de la consola del
cliente (y de la app) con **dos formas de reservar**, que elige el admin de
Auphere:

- **Servicios**: una cita con una persona del equipo (peluquería, clínica,
  asesoría). Limita la agenda de cada persona.
- **Aforo**: sitio para N personas a una hora, sin mesas (restaurante, bar,
  clases, tours, salas, spa). Limita cuántas personas caben a la vez.

El agente reserva, mueve y cancela por WhatsApp con las herramientas
`reservas.*`; el negocio lo ve y lo corrige en su consola o en la app; el
sistema confirma, recuerda, libera y ofrece los huecos a la lista de espera.

**Reservas es la fuente de la verdad** (Luis, 2026-11-04; spec 043, requisitos 11 a
14). La cita de un agente nace aquí, lleva sus recordatorios y nadie puede ocupar esa
hora. Google Calendar es un espejo: cada profesional conecta el suyo desde Ajustes, su
ocupado bloquea huecos y sus reservas salen allí como «Ocupado». Sus herramientas no son
de ningún agente nuevo: todas las `GOOGLECALENDAR_*` están retiradas, con su sustituta si la
tienen (`agent_spec.retired`), y el paso automático las cambia. El turno se las quita a quien ya
pasó (`activations.tool_policy`) y deja como estaba al agente de un cliente que todavía no puede
reservar: quitárselas sin darle Reservas lo dejaría sin agenda. Ese agente se puede seguir editando
y publicando con lo que ya nombra (`Context.held_tools`), y no añadir nada nuevo. **Calendly**: donde Reservas está
encendido tampoco reserva (conectarlo no da herramientas, y encender Reservas o el paso automático
dejan un borrador sin él, que no se publica solo); sin Reservas sigue como estaba.

**Reservas es la única agenda de los agentes** (spec
[`048-retirar-agendapro`](../specs/048-retirar-agendapro/spec.md)). AgendaPro se
retiró del todo; `booking.*` —la agenda de antes, que escribe en
`appointments` y que el negocio no ve— está **retirada**: el catálogo la marca
`deprecated`, el constructor, el copiloto, la consola y las plantillas no la
ofrecen, y el validador rechaza un borrador que la traiga con `tool_retired` y su
sustituta (`replacement`). Los agentes que aún la nombran pasan solos a Reservas
en cada despliegue ([abajo](#el-paso-automático-a-reservas-spec-048)). El runtime
la sigue ejecutando para las versiones que ya la tienen, hasta el borrado final
(requisito 5, otra entrega).

| `booking.*` | `reservas.*` |
|---|---|
| `check_availability` | `find_slots` |
| `create_appointment` | `create` |
| `modify_appointment` | `reschedule` |
| `cancel_appointment` | `cancel` |
| `get_appointments` | `list_mine` |

Lo que reservaba fuera, además: `GOOGLECALENDAR_FIND_FREE_SLOTS` → `find_slots` y
`GOOGLECALENDAR_CREATE_EVENT` → `create`, siempre; `CALENDLY_POST_INVITEE` y
`CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK` → `create`,
`CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES` → `find_slots` y `CALENDLY_LIST_EVENT_TYPES` →
`services`, donde Reservas está encendido (`passing.CONNECTOR_TOOLS`).

## Activarlo (panel de operador)

Pestaña **Acceso** del cliente: se marca «Reservas» y se elige el modo (y en
Aforo el tipo de negocio). Es la misma llamada que los módulos:
`PUT /admin/tenants/{id}/client-access` con `reservas: {mode, capacity_kind,
on_live}` (contrato: [`admin-api.md`](../specs/043-reservas/contracts/admin-api.md)).

- La primera activación crea `reservation_settings` con los valores de partida
  del modo y del tipo (tabla en [`data-model.md`](../specs/043-reservas/data-model.md)).
- **Cambiar de modo con reservas futuras vivas** responde 409
  `live_reservations` con cuántas. Con `on_live: cancel_and_notify` se cancelan
  (`cancel_cause = mode_change`), cada cliente con teléfono recibe el aviso y el
  modo cambia, todo en una transacción. Nunca conviven dos modos.
- Cambiar solo el tipo de Aforo cambia las palabras, no los números.
- Activar o desactivar **prepara el borrador** de cada agente activo (el único
  que tiene, spec 047): con `reservas.*` y sin `booking.*` ni lo que reserva en un
  conector, o sin `reservas.*`. **No lo promueve**: se publica por la puerta; la pestaña
  enlaza a la pestaña Agente (`agents_pending_promotion`) y dice quién **sigue reservando
  fuera** hasta publicar su borrador (`agents_with_other_calendar`). Activar es además
  **pasar el cliente a Reservas** (abajo): el AgentSpec y el texto también, y las citas
  futuras.
- Desactivar el módulo no borra ajustes ni reservas; las futuras siguen
  recibiendo sus recordatorios.
- **Reservas no depende del acceso de las personas** (spec 048, decisión 16 de
  su `plan.md`). Está encendido si `reservas` está en `client_access.modules` y
  hay `reservation_settings`, con `enabled` encendido o apagado: lo miran las
  herramientas del agente, las ofertas del worker y esta pestaña
  (`ClientAccess.reservas_on`). `enabled` solo dice si las personas del cliente
  pueden entrar en la consola y en la app; apagarlo ya no apaga Reservas.

La parte de Reservas de esa llamada corre **bajo la RLS del cliente dentro de la
transacción del admin** (`services/reservations/admin.py: as_tenant`: cambia al
rol `nexus_app` y vuelve con `RESET ROLE`): la sesión del admin trabaja sin RLS y
las consultas del dominio no filtran por tenant a mano.

## El paso automático a Reservas (spec 048)

Para los clientes que todavía reservan con `booking.*`. **Nadie hace nada a
mano**: corre en cada despliegue, en la tarea de migración, después de `alembic
upgrade head` y del sembrado de conectores (`scripts/release.sh` →
`scripts/pass_booking_to_reservas.py` → `services/reservations/auto_pass.py`).
No hay pantalla ni rutas para hacerlo a mano (requisito 3.8).

- **Quién.** Cada cliente con algún agente activo cuya versión activa o cuyo
  borrador nombra `booking.*` o una herramienta de Google Calendar (herramientas,
  AgentSpec o texto) o, si ya tiene Reservas, reserva con un conector. Un cliente sin
  Reservas que solo usa Calendly no se toca. **Con Google, solo pasa si el cliente ya puede
  reservar** (`passing.not_ready`: módulo, horario, equipo y servicios, o aforo). Si no, no se
  enciende ni se publica nada: el agente sigue como está, se registra
  `reservations.auto_pass_not_ready` con las razones, se avisa al partner
  (`reservas.pass_not_ready`) y el panel de operador lo enseña en Acceso. El siguiente despliegue
  vuelve a mirar. Se decide agente por agente: otro con `booking.*` pasa igual, y solo entonces se
  enciende el módulo. Un borrador de Calendly que alguien descartó no vuelve mientras siga la misma
  versión activa. La lista de
  clientes se lee con el rol de migraciones (solo sus ids); cada cliente pasa
  después en **su propia transacción, bajo su RLS** (`admin.as_tenant`), contra
  la base directa. Un cliente sin agentes con `booking.*` se salta: el segundo
  despliegue no encuentra a nadie.
- **Reservas, si no lo tenía.** Se activa primero, con los valores de partida del
  modo (`admin.apply_choice`): **Aforo de restaurante** si el negocio es un
  restaurante —el sector guardado de la ficha (`sector_key`, solo se lee: ni se
  identifica ni se llama a un modelo durante el despliegue) o, sin sector, la
  plantilla de la que viene su agente (`restaurante_v1`)—, y **citas por
  persona** en cualquier otro caso. Se añade `reservas` a los módulos del
  cliente sin tocar `enabled`: no abre el acceso de sus personas ni invita a
  nadie. Un cliente que ya tenía Reservas conserva su modo; uno con los ajustes
  y el módulo quitado recupera el módulo con su modo.
- **La versión activa se publica** con `reservas.*` en `tools`, en el AgentSpec
  (`tools` y procedimientos) y en el texto, con el mapa de arriba, y gana
  además solo `reservas.services` (sin ella no sabría los ids). Nada más: un
  agente que solo miraba la agenda (`booking.check_availability`) no sale
  pudiendo reservar, cancelar ni mover citas (R3.3; plan de la 048, decisión 26,
  que sustituye en esto a la 19). El borrador que nombra `booking.*` se reescribe
  igual. Activar Reservas desde Acceso sí sigue dando las nueve, en un borrador
  que pasa la puerta. Lo demás es igual a la activa. Es un cambio de la plataforma, no del partner: nace de la
  **activa**, nunca del borrador, y se publica **sin la puerta de pruebas**
  (`AgentConfigService.publish_platform_copy`), firmada por
  `platform:reservas-pass`, con su nota («Paso automático a Reservas») y su
  motivo en `override_reason` y en la auditoría (`agent_config.promote` y
  `agent.publish` con `origin: platform`). Sin ventana de deshacer. Las pruebas
  del agente quedan desactualizadas.
- **El borrador del partner**, si nombra `booking.*`, se reescribe igual y **no
  se publica**: conserva sus otros cambios y sigue siendo el único borrador del
  agente. Su revisión avanza una vez, como con cualquier escritura, así que una
  pestaña que lo estaba editando se entera (412 con el cambio de Auphere). Un
  agente sin borrador no recibe uno.
- **Las citas futuras** (reservadas o confirmadas) de `appointments` pasan a
  `reservations` como confirmadas, sin mensaje a nadie (la persona ya sabe de su
  cita), cuando su servicio casa por nombre con un servicio de Reservas y su
  barbero (el nodo del grafo) con una persona del equipo — sin tildes ni
  mayúsculas. La reserva guarda la cita de origen en su clave
  (`appointment:<id>`): nada se duplica. Las que no casan se quedan en
  `appointments` y salen en el informe con su motivo: `capacity_mode` (en Aforo
  una cita no dice para cuántos), `service_missing`, `service_not_bookable`,
  `staff_missing`, `staff_not_found`, `staff_cannot_do_service`, `slot_taken`.
  Un cliente recién activado empieza sin servicios ni personas, así que sus citas
  salen como `service_missing` y no se pierden.
- **El informe**, en la auditoría del cliente: `reservations.passed`, con
  `automatic: true`, el motivo, la activación (`activated: {mode,
  capacity_kind, from}` con `from` = `sector`, `template`, `default` o
  `existing`; `null` si ya lo tenía), las versiones publicadas (`published`),
  los borradores reescritos (`agents`), las importadas, las ya importadas y las
  que no, con su motivo. Si hubo que activar el módulo, también
  `client_access.updated` con `automatic: true`.
- **Si un cliente falla**, se deshace solo el suyo (activación, versiones,
  borrador, citas e informe) y queda en el registro
  `reservations.auto_pass_failed` con `tenant_id` y el tipo de error (sin datos
  de nadie); los demás siguen. Al final, una línea
  `reservations.auto_pass_done` con `passed`, `failed`, `failed_tenants`,
  `activated`, `published`, `drafts`, `imported`, `already_imported` y
  `not_imported`. El guion sale con 0 aunque falle un cliente, y `release.sh`
  sigue aunque el guion entero reviente: **el despliegue no se para aquí**. El
  runtime sigue ejecutando `booking.*` para quien la tenga (requisito 5.3), y el
  borrado final (T030) se niega en voz alta mientras alguien la nombre.
- **El historial y las comisiones** (`client.get_history`, `commission.*`)
  leen las dos agendas: las reservas y las citas que no se importaron, sin
  contar dos veces una importada (`nexus_mcp/_agenda.py`).

Activar Reservas desde la pestaña **Acceso** sigue haciendo el paso a su manera
(requisito 3.9): el borrador de **cada** agente activo gana `reservas.*`, no se
publica (va por la puerta) y las citas futuras se importan con su informe
(`reservations.passed`, `automatic: false`, firmado por el operador).

Qué mirar en el registro del despliegue y cómo repetir el paso: `RUNBOOK.md`,
«Paso automático a Reservas».

## El dominio (`apps/api/src/nexus_api/services/reservations/`)

| Fichero | Qué |
|---|---|
| `engine.py` | El motor de disponibilidad, **puro**: franjas de turnos o franjas (la última llegada incluida), presencia, `capacity_fit`, `first_fit`, huecos de Servicios. Lo usan la API, las herramientas y el worker |
| `core.py` | Contexto del cliente, crear/mover/cancelar con **candado + revalidación**, transiciones de estado y `allowed_actions`, historial, outbox, avisos al negocio |
| `waitlist.py` | Lista de espera y ofertas: candidatos, plazos (5 min Servicios, 15 min Aforo), aceptar a tiempo o tarde |
| `views.py` | La forma `Booking` del contrato, listado, ocupación por franja, resumen |
| `settings.py` | Valores de partida por modo y tipo; validación de lo que el negocio cambia |
| `admin.py` | La activación desde el admin |
| `passing.py` | Pasar a Reservas (spec 048): reescritura `booking.*` → `reservas.*` de borradores y versiones, publicación sin puerta desde la activa, importación de citas, informe y quién sigue con `booking.*` |
| `auto_pass.py` | El paso automático de cada despliegue (spec 048): activar Reservas por sector o plantilla, un cliente por transacción bajo su RLS, y sus registros `reservations.auto_pass_*` |
| `calendar.py`, `calendar_sync.py` | P3: choques con Google Calendar, la conexión de cada profesional y la sincronización |

**Sin doble reserva.** No hay `EXCLUDE` en la base (el aforo es una suma, y
`btree_gist` no está garantizado en Aurora). Las escrituras toman
`pg_advisory_xact_lock` por persona (Servicios) o por día (Aforo) y revalidan
con el mismo motor que ofrece los huecos. La prueba
`tests/integration/reservas/test_concurrency.py` lanza peticiones simultáneas
por la API y por la herramienta; sin el candado, falla.

**Sin pisar lo que cambió otro.** Mover, cancelar y cada transición releen la
fila bajo candado (`core._fresh`) antes de decidir; la API además comprueba
`If-Match` sobre esa lectura. Así una confirmación no resucita una reserva que
el cron acaba de liberar (y cuyo sitio ya ofreció). Los crons cogen filas con
`SKIP LOCKED`: lo que la API tiene cogido queda para la pasada siguiente.

**Reglas que conviene recordar**:

- **Un solo horario, el de la ficha** (spec 047, T056; research D15). Reservas lo
  lee de `services/business/hours.py` (`business_schedules` + `business_shifts` y
  `business_special_dates`), el mismo que dicen el agente, «¿abierto ahora?» y la
  app: turnos nocturnos (un cierre igual o anterior a la apertura es del día
  siguiente; el tramo de después de medianoche cuenta en el día siguiente) y
  fechas especiales (un festivo cerrado no tiene huecos; la fecha manda desde la
  apertura del turno de ese día). Las horas son de reloj, en la zona del negocio,
  también el día del cambio de hora. `Ctx.day_ranges(día)` da los tramos abiertos
  de ese día; uno que llega a medianoche acaba en `time.max`
  (`engine.until` lo lee como las 00:00 del día siguiente).
- Sin horario, no se ofrece ni se reserva nada (`hours_missing`). Un cliente que
  aún no tiene el horario en la ficha se lee de `tenants.business_hours` (la
  migración `0186_migrate_hours_to_ficha` los pasa a la ficha); desde entonces
  esa columna es solo una **proyección** que el servicio de horario escribe en la
  misma transacción (los días en la forma canónica, los nocturnos partidos a
  medianoche, y la frase «Así lo dirá el agente» como `label`). El negocio lo
  edita en Ajustes de Reservas (`PATCH /business-hours`, que escribe en la ficha) o
  en Negocio de la consola de partners (`PUT /console/clients/{ref}/business/hours`).
- **Servicios no reservables** (spec 047, T058): un producto, un menú o una
  consulta no llevan duración (`bookable = false`, `duration_minutes` nulo). No
  tienen huecos (`not_bookable`) y Reservas no los lista: son de la ficha. Uno
  reservable dura de 5 a 480 min, en pasos de 5. El precio tiene tipo: sin precio,
  gratis o un importe (`price_kind`). Un servicio cambiado aquí es un cambio de la
  ficha: los agentes lo usan desde el siguiente mensaje.

### Las reglas de la ficha (spec 056, requisito 5)

Ajustes de Reservas y la ficha del partner aceptan y rechazan **los mismos**
valores. Viven en `services/business/rules.py` (y su espejo
`apps/console/src/lib/business-rules.ts`): de 0 a 6 turnos por día, horas en
pasos de 5 minutos con 24:00 como cierre, nocturnos sin pisar el día siguiente,
duración de 5 a 480 en pasos de 5, precio `none`/`free`/`amount`, importe de 0 a
10¹² unidades menores, categoría de 40 y nombre de 1 a 120.

- **Horario, solo lo tocado.** `GET /settings` trae `hours` con la forma de la
  ficha (`hours_view`: revisión, layout y días con `overnight`) y
  `location_hours` (cada sede y si tiene horario propio, con su frase). La consola
  edita con el mismo componente que la ficha (`business/sections/week-editor.tsx`),
  día a día, y manda `PATCH /business-hours {revision, days}` **solo con los días
  que cambiaron** (`changedDays`). El servidor sustituye esos días
  (`hours.replace_days`), sigue «por bloques» si de lunes a viernes siguen
  iguales (si no, pasa a día por día) y llama a `save_week(expected_revision=…)`:
  si alguien guardó antes, `409 revision_conflict`. Las reglas estrictas solo
  miran los días tocados: `422 {code, field, day}` con `too_many_shifts`,
  `bad_step`, `overlap`, `overlap_next_day` o `invalid_day`. El horario propio de
  una sede se enseña y no se toca desde aquí.
- **«Revísalo».** Un turno guardado con minutos fuera del paso de 5 (la API los
  aceptaba) se enseña tal cual, marcado, y se guarda igual mientras nadie toque
  su día. Se calcula al leer (`reviewDays`), sin columna.
- **Servicios por el catálogo.** Crear, editar y archivar pasan por
  `services_catalog.create_service`/`update_service`/`archive_service`: un solo
  validador y el historial de la ficha. `ServiceOut.price` es el de la ficha
  (`{kind, amount_minor?}`, con `currency` al lado); `POST`/`PATCH` reciben
  `price: PriceIn` («Gratis» es `free`, no un importe nulo). El `PATCH` solo
  cambia lo que llega. Desde Reservas un servicio se crea con su nombre y no se
  renombra: un nombre distinto del guardado da `422 rename_not_allowed`. Los
  demás «no» llevan su código y su campo (`bad_duration`, `amount_too_large`,
  `category_too_long`, `price_amount_required`…); la consola los comprueba antes
  con las mismas reglas (`safeParse` → `{status: 422, code, field}`) y los dice
  con `business.services.error.*`, nunca con «No se pudo hablar con el servidor».
- **Equipo.** El correo de una persona tiene formato de correo y 254 caracteres
  como mucho (`EmailStr`).

### Lo que no se deshace y lo que se escribe (spec 056, requisitos 11 a 13)

- Los diálogos de Reservas (nueva reserva y moverla, de los dos modos, cancelar,
  apuntar en la lista de espera, llegada sin reserva, bloqueo, horario, persona y
  servicio) preguntan antes de cerrarse con datos escritos
  (`components/use-discard-guard.tsx`).
- «Apuntar en la lista de espera» valida como «Nueva reserva»: el aviso al salir
  del campo y el botón desactivado hasta tener nombre, servicio y un teléfono válido.
- El dinero se escribe y se lee con `lib/amount.ts`, en el idioma de la persona
  («10,00 US$»), y los campos de importe aceptan coma o punto.
- Aforo: un grupo cabe a la hora `t` si en cada franja de `[t, t + estancia)`
  queda `aforo − guardadas − presencia ≥ n`; la llegada sin reserva usa el aforo
  entero. Un bloqueo no toca lo ya reservado.
- Servicios: un hueco cabe entero en el horario del negocio ∩ el de la persona
  (la pausa es el hueco entre sus dos tramos), sin pisar reservas vivas, huecos
  retenidos por una oferta en curso ni «ocupado» de Google.
- El agente reserva con al menos 60 min y como mucho a 60 días (ajustes), nunca
  pasa del máximo por grupo (`too_large` → escala a una persona).
- Estados: `pending` (Sin confirmar), `confirmed`, `arrived` (solo Aforo), `done`,
  `noshow`, `cancelled`. «Llega tarde» y el choque se calculan.

## API (`/console/lite/reservas/*`)

Contrato: [`contracts/lite-api.md`](../specs/043-reservas/contracts/lite-api.md).
La comparten la consola web y la app (mismo principal). `lite_scope("reservas")`:
sin el módulo, 403 opaco; un id de otro cliente, el mismo 404 que uno inventado.
Escrituras con `Idempotency-Key` (reservas y llegadas por columna; equipo,
servicios, bloqueos y entradas por Redis, 24 h) y `If-Match` (versión de la
reserva o de los ajustes; 412 `stale`). Cada `Booking` trae `allowed`: las
acciones válidas ahora, que las pantallas pintan sin recalcular reglas.

También tocan Reservas: `/me` (`reservas: {mode, capacity_kind}` y el módulo en
`nav`), el detalle de la Bandeja (`contact.next_booking`) y los avisos del
teléfono (tres tipos `reservas.*`, solo con el módulo).

## El agente (`reservas.*`)

Contrato: [`agent-tools.md`](../specs/043-reservas/contracts/agent-tools.md).
`apps/mcp/src/nexus_mcp/servers/reservas/`, registradas en el catálogo por
`0173_reservations_tools` (snapshot `alembic/data/0173_reservations_tools.json`),
con nombre de negocio en Capacidades (grupo Citas) y en la intención `book`
(y `info` las de lectura). **Ninguna acepta cliente**: la persona sale del turno
(spec 014); una reserva ajena se lee como inexistente; `answer_offer` resuelve
la oferta abierta de esa persona sin que el modelo la nombre.

**Cada agente, sus servicios** (spec 047, T058; requisito 11.4, garantía 9). Un
agente «Atiende todos los servicios» o tiene su lista (`agent_services`); un
servicio sin lista es «Para todos los agentes» y lo conocen solo los que atienden
todos. `reservas.services` lista solo los del agente del turno —el del número de
la conversación, nunca un argumento del modelo— y `find_slots`, `create` y
`join_waitlist` con un servicio de su hermano responden `not_offered`. Lo mismo
`booking.check_availability`/`create_appointment` cuando el nombre es el de un
servicio del catálogo que el agente no ofrece. Lo prueba
`tests/isolation/test_44_agent_within_client.py`.

## Lo automático (worker)

Contrato: [`worker-y-avisos.md`](../specs/043-reservas/contracts/worker-y-avisos.md).

| Cron | Tick | Qué |
|---|---|---|
| `reservations-cron` | 60 s | Pide confirmación y recuerda a su hora, libera en Aforo lo no confirmado 1 h antes (solo si la pregunta salió), cierra como `done`, caduca la lista, abre ofertas de Aforo (solo con el módulo encendido) |
| `reservation-offers-cron` | 15 s | Vence plazos y escribe al siguiente candidato |
| `reservation-outbox-cron` | 10 s | Envía `reservation_outbox`: texto dentro de la ventana de 24 h, plantilla aprobada fuera; sin plantilla, teléfono, canal o con la baja pedida, `skipped` y evento `notify_failed`; lo que ya no aplica (ya confirmó, ya se canceló), `stale` sin evento. Escribe el `Message` pendiente: lo entrega y lo mide el despachador de salida, como cualquier saliente |
| `reservation-calendar-cron` | 120 s | P3: termina las autorizaciones en curso, quita los eventos que sobran, escribe los que faltan y lee el ocupado, cada parte y cada profesional con su propio fallo. Sin conexión sana deja de bloquear (ver [Google Calendar](#google-calendar-p3)). Sin `composio_api_key` no hace nada (el cliente simulado del proveedor borraría el ocupado real) |

Los cuatro recorren los clientes **activos con `reservation_settings`**, tengan
o no el módulo encendido: al apagarlo, las reservas futuras siguen recibiendo
sus avisos; solo se dejan de abrir ofertas nuevas.

Los avisos de Reservas al **teléfono del negocio** (push) salen por el canal de
Android `reservations_v1` y la categoría de iOS `reservations` (los crea la app;
`services/push_payloads.KIND_CONFIG`).

**Plantillas** que el módulo usa fuera de la ventana de 24 h (las aprueba Meta en
el número de cada cliente): `reserva_confirmada`, `reserva_pide_confirmacion`,
`reserva_recordatorio`, `reserva_cambiada`, `reserva_cancelada`,
`reserva_hueco_libre`. Textos de partida y variables, en el contrato. Sin ellas,
lo que no cabe en la ventana no sale, y el historial de la reserva lo dice.

## Google Calendar (P3)

Solo Google (decisión del owner), solo en Servicios. **Cada profesional conecta su cuenta**
en **Ajustes → Calendarios de Google**, con una identidad propia en el proveedor
(`tenant_<slug>_staff_<id>`): ni la del negocio ni la de otro. A los agentes no se les ofrece
Google Calendar: `POST …/connections` y `…/consent` responden 409 `connect_from_reservas` a uno
nuevo. En las integraciones del cliente, una conexión de antes se puede renovar si se cayó, porque
un agente que aún reserva en Google la necesita y lo que hay allí bloquea horas, y se puede quitar.
Renovarla no da herramientas a nadie.

**El Google del negocio (spec 023) solo se lee** (R12.13). Las citas que un agente tomó allí **no se
importan**: un evento no dice de qué cliente es. Pero esa hora ya está dada: lo que hay en ese
calendario (`source = 'business'`) bloquea a cada profesional que aún no sincroniza el suyo, y su
fila lo dice (`business_busy`). No tienen recordatorio ni se pueden cancelar desde Reservas. Si la
fila de antes dice qué calendario era suyo, solo le bloquea a esa persona; si no, no se sabe de
quién es la cita y bloquea a todos: dar dos veces una hora es peor que no darla. Cuando todos
sincronizan, o se quita la conexión, se deja de leer. Lo lee solo el cron, no el botón de una persona.
**Aquí no vale «con datos viejos no se bloquea»**: si la lectura falla o la conexión se cae, lo
leído sigue, porque son citas ya dadas y dejar de leerlas no las cancela.

Entra el «ocupado» (solo inicio y fin, `reservation_busy`); un evento de todo el
día ocupa el día en la zona del negocio, y uno marcado como disponible, cancelado o
rechazado por esa persona no bloquea. Sale cada reserva viva como «Ocupado», sin cliente
ni servicio. A la vuelta se reconoce por el id del evento guardado en la reserva, no por
un texto que cualquiera puede escribir en una invitación.

**Conectar** (`POST …/staff/{id}/calendar/connect`). «Ir a Google» vuelve a
`/reservas?tab=settings&calendar_return=<id>`, y el panel pide `…/calendar/refresh` sin
esperar a la pasada. «Copiar enlace» (`share: true`) es para quien no está delante: el
enlace del proveedor, que caduca solo, y una página de «ya puedes cerrar esto» a la vuelta.
La autorización pide leer y escribir: la pantalla lo dice antes de ir a Google, y el permiso
real lo fija la configuración de autorización del proveedor, no un botón nuestro.

| Estado (`calendar.status`) | Qué dice la fila | Acción principal | En el menú |
|---|---|---|---|
| `none` | Sin conectar | Conectar | — |
| `pending` | Esperando a que autorice | Comprobar | Crear otro enlace, Desconectar |
| `connected` | La cuenta (y el calendario, si no es el principal) y la última sincronización | — | Cambiar calendario, Desconectar |
| `needs_calendar` | La cuenta ya la usa otro (`calendar_in_use`), o no tiene calendarios (`no_calendar`) | Elegir calendario, o Conectar otra cuenta | La otra, Desconectar |
| `needs_reauth` | Hay que volver a conectar; no bloquea huecos | Volver a conectar | Desconectar |
| `error` | No se pudo leer o escribir, o el calendario ya no existe | Reintentar, o Elegir calendario | Cambiar calendario, Conectar otra cuenta, Desconectar |

Al completarse queda con el **calendario principal** de esa cuenta si nadie más del negocio
lo usa, y se ve qué cuenta es: así se nota si Lucía quedó con la de quien pulsó el botón.
**Un calendario, un profesional**: 409 `calendar_in_use` con su nombre, y un índice único en
la base. Una cuenta compartida vale: se autoriza en cada uno y se elige un calendario distinto.

**Un enlace sin terminar** caduca a la hora, o antes si el proveedor lo da por fallido, y la
fila vuelve a como estaba. **Volver a conectar** conserva el calendario y revoca la conexión
anterior. **Desconectar** deja de bloquear al momento y la fila dice «Sin conectar»; la pasada
siguiente quita sus eventos y revoca la conexión (`disconnecting`), porque las dos cosas hacen
falta en ese orden y no caben en una petición. Si ya no puede borrarlos, revoca igual y no
insiste. Archivar a alguien lo desconecta, y borrar el cliente revoca la conexión de cada
profesional al confirmarse el borrado. Mientras tanto, volver a conectar responde 409
`calendar_disconnecting`.

**Salir de Servicios desconecta a todos**: en Aforo no hay panel desde el que hacerlo. **Apagar el
módulo no**: sus reservas por venir y sus avisos siguen vivos, y borrarlas de Google le quitaría esa
cita a la persona. Sigue sincronizando hasta que se vuelva a encender y se desconecte, o se borre
el cliente.

**Conectar otra cuenta no suelta la que funciona hasta que la nueva esté** (`previous_connection_id`):
es la única que llega a sus eventos. Si la nueva no termina, vuelve a ella, y si autorizó y Google no
le deja leer, la fila lo dice durante una hora (`new_account_refused`). Si termina, cada reserva
por venir sigue a la cuenta nueva: lo que está en un calendario al que la nueva no llega se borra
con la anterior y se escribe de nuevo, y luego se revoca la anterior. Una fila de antes de esta
enmienda no tiene con qué borrar: su evento se queda en el calendario del negocio, sin bloquear.

**Una pasada, tres partes que no dependen unas de otras:** borrar lo que sobra,
escribir lo que falta y leer, cada profesional con su conexión. Lo que se escribe en Google se
apunta en su propia transacción, reserva por reserva: Google no se deshace con un `ROLLBACK`, y
perder un id significaba un «Ocupado» repetido cada dos minutos. **La transacción de la pasada no
escribe nunca en `reservations`**: una fila suya sin confirmar haría esperar para siempre a la
otra conexión, y Postgres no lo ve como un interbloqueo. Todo va por `_own_tx`, con `lock_timeout`
de 5 s, y si no se puede apuntar, el evento se quita y se escribe en la pasada siguiente. El cron da
hasta 300 s a cada cliente y `refresh`, 25 s. Un 404 o 410 al borrar cuenta como borrado: alguien lo
quitó a mano. «Connected account not found» o «Tool … not found» no: el evento sigue allí.

**Mover.** `reservations.external_event_id` guarda `<profesional> <calendario> <evento>`, porque
el evento sigue donde se escribió aunque la reserva cambie de persona o la persona de
calendario o de cuenta, y solo se alcanza con la conexión de quien lo escribió. `move_booking` le
antepone `moved `, y la pasada siguiente lo borra de su calendario y escribe el nuevo. Si el fallo
es temporal, espera a borrarlo para no duplicar, y no más de una hora (`REMOVE_WAITS_AT_MOST`). Si
nadie puede borrarlo (el dueño no tiene conexión
o perdió el permiso, o el evento no tiene id), suelta la referencia y escribe el nuevo: lo de uno no
toca a los demás, y si el viejo vuelve a verse, su marca lo delata. Cambiar de calendario hace lo
mismo con los eventos de sus reservas por venir.

**Lo nuestro nunca es ocupado.** Se reconoce por el id que guarda la reserva y, si se perdió, por su
marca: la descripción `auphere:reserva:<id>` de un evento que organiza la propia cuenta, con el id de
una reserva que existe en este cliente. Si es la cita de esa persona, a esa hora, y aún no tiene
evento (una creación que no devolvió el id o que dio timeout), se adopta; si no, sobra y se borra.
Una marca de otro cliente, de una reserva que no existe o en una invitación de fuera no libera nada:
se lee como ocupado normal.

**Qué bloquea.** Lo cancelado, una invitación rechazada, un cumpleaños (`birthday`) y un lugar de
trabajo (`workingLocation`), no. Lo de todo el día sí, aunque Google lo marque como disponible: nace
así y es la forma de cerrar un día, con el coste de que un recordatorio de todo el día también lo
cierra. Lo que tiene hora y está marcado como disponible, no.

**Lo que cambia en Google vuelve bien.** Reservas manda: mover la cita de un cliente sin avisarle
no se hace desde otro calendario. Un evento de la persona bloquea y, si pisa una reserva, sale
como choque. Nuestro «Ocupado» borrado a mano se vuelve a escribir, y uno movido a mano vuelve a
la hora de la reserva, en la pasada siguiente (`reservation_calendar.event_put_back`). En los dos
casos se borra antes de escribir: si es el listado el que no lo trae, no se acumulan «Ocupado». Lo
escrito en esa misma pasada no se mira: la lectura puede no traerlo aún.

**Con datos viejos no se bloquea** (decisión de 2026-11-04). Un hueco ofrecido de
más se ve como un choque en la agenda; uno bloqueado de más es un cliente que nadie
atiende.

| Situación | Qué pasa con el ocupado | `status` · `last_error` | Qué dice la pantalla |
|---|---|---|---|
| Todo bien | Se renueva en cada pasada | `connected` · `null` | «Sincronizado hoy 10:30», o «Primera sincronización en curso» |
| La lectura falla | Se mantiene `BUSY_STALE_AFTER` (30 min) desde la última lectura buena y se quita | `error` · `read` | No pudimos leer; si sigue media hora, deja de bloquear |
| La escritura falla | Sigue igual | `error` · `write` | No pudimos escribir todas sus reservas; se sigue intentando |
| Google rechaza el permiso | Se quita en esa pasada | `needs_reauth` · `auth` | Hay que volver a conectar; lo de Google no bloquea huecos |
| El calendario ya no existe | Se quita en esa pasada | `error` · `calendar_gone` | Elige otro; lo de Google no bloquea huecos |
| La conexión está en `needs_reauth` | Se quita en la pasada siguiente | `needs_reauth` · `connection` | Hay que volver a conectar; lo de Google no bloquea huecos |

Lo que le pasa a un profesional no toca a los demás. `last_sync_at` es la última pasada en la que
salió todo. `last_error` es un código nuestro y la pantalla lo traduce: el texto del proveedor no
se guarda, no sale por la API y no va a los registros, porque puede traer un token o el título de
la cita de otra persona. Registros, todos con `tenant_id` y `staff_id`:
`reservation_calendar.read_failed`, `.write_failed`, `.event_without_id`, `.busy_dropped`,
`.connection_unhealthy` (una vez, no cada dos minutos), `.link_failed`, `.account_state_failed`,
`.revoke_failed`, `.event_put_back`, `.event_adopted`, `.ref_not_saved` y
`.business_read_failed`. Llevan el tipo de error, nunca su texto. En la auditoría del cliente:
`reservations.calendar_connect_started`, `.calendar_changed` y `.calendar_disconnected`, con quién y
de qué profesional, sin la cuenta de nadie.

El webhook del proveedor no interviene: no sabe de estas conexiones (`unknown_connection`, 200) y
cada una se resuelve mirando su estado (`calendar_sync.settle_pending`), al volver y en cada pasada.

Los nombres de las acciones y argumentos viven en `ComposioGoogleCalendar` y salen
del catálogo público de Composio (`docs.composio.dev/toolkits/googlecalendar`,
leído el 2026-11-04): `GOOGLECALENDAR_EVENTS_LIST`, `GOOGLECALENDAR_CREATE_EVENT`,
`GOOGLECALENDAR_DELETE_EVENT` y `GOOGLECALENDAR_LIST_CALENDARS`. **Ese catálogo no
describe la forma de las respuestas**, y esto no se ha probado con una cuenta de
Google de verdad: **verificarlo en staging** antes de encenderlo para un cliente.
Una respuesta que no es un listado cuenta como fallo de lectura, no como calendario
vacío. Si al crear un evento la respuesta no trae su id, se guarda `?` para no volver
a crearlo, lo dice `.event_without_id`, y la lectura siguiente lo adopta por su marca. El SDK va sin
reintentos: tras un timeout, repetir una escritura la hace dos veces.

## Los datos que dejan reservar

Lo que falla aquí no da un error: da un cliente al que el agente no sabe atender. Por eso se avisa
en Ajustes antes de que pase (spec 043, requisito 14; `warnings` de `/services` y `/staff`).

| Dato | En Ajustes | El agente | La consola |
|---|---|---|---|
| Servicio que no hace nadie en activo | `no_staff` | `reservas.services`: `bookable: false`, `why_not: no_staff`. `find_slots` y `create`: `no_staff` | 409 `no_staff` |
| Servicio que no cabe en el horario de quienes lo hacen, mirando la semana que viene | `does_not_fit` | Sin huecos; `slot_taken` | Sin huecos; 409 `slot_taken` |
| Persona con horario propio y ningún día | `no_hours` en la persona | Sin huecos con ella | Sin huecos con ella |
| Persona sin horario propio | — | El del negocio | El del negocio |
| Pedir a quien no hace ese servicio | — | `not_offered` | 404 |
| Persona archivada | Sale de la lista del servicio, también en la ficha del negocio; no puede volver a él y no cuenta | No se ofrece | No se ofrece |
| Fecha especial cerrada | — | `find_slots`: `closed`; `create`: `slot_taken` | `/slots`: `closed`; 409 `slot_taken` |

**Sin excepciones por persona.** Un día libre de un solo profesional solo se puede expresar con
su calendario conectado (un evento de todo el día). Sin calendario, hoy no hay forma.

## Probarlo en local

`apps/api/scripts/dev_seed_reservas_demo.py` (se niega en producción) siembra un
partner y dos clientes chilenos, uno por modo, con equipo, servicios, reservas
de esta semana, lista de espera, un bloqueo, conversaciones atendidas (una que
espera a una persona) y saldo:

```bash
NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/<base> \
  uv run --directory apps/api python scripts/dev_seed_reservas_demo.py
```

Entran `valeria@cultor.test` (Peluquería Cultor, Servicios), `carla@lafonda.test`
(Restaurante La Fonda, Aforo, tipo restaurante) y `socio@demo.test` (el partner),
con la contraseña que imprime. No envía nada: las reservas nacen sin aviso. La
pasada viva de accesibilidad y desbordes de la consola corre contra ellas:

```bash
E2E_BASE_URL=http://localhost:3110 E2E_CLIENT_EMAIL=valeria@cultor.test \
  E2E_CLIENT_PASSWORD=… pnpm --dir apps/console test:e2e --project=lite
```

## Aislamiento

- RLS FORCE en las tablas nuevas y FK compuestas `(tenant_id, id)` entre ellas y
  hacia `customers`, `conversations` y `agents` (`SET NULL (col)` donde la
  retención de datos puede borrar).
- `tests/isolation/test_reservas_client_vs_client.py`: todas las rutas, los dos
  modos, las dos credenciales; 403 a partner y a cliente sin módulo.
- `tests/isolation/test_reservas_customer_axis.py`: el agente de una persona no
  toca lo de otra del mismo negocio; ninguna herramienta tiene campo de cliente.
- Cada ruta de calendario entra en el barrido: un profesional de otro cliente da el mismo
  404 que uno inventado, y la identidad en el proveedor no sale por la API.
- `tests/isolation/test_reservas_auto_pass_scope.py` (spec 048): el paso
  automático de un cliente no lee ni escribe nada de otro — ni su sector, ni sus
  servicios y su equipo, ni sus agentes, citas, pruebas, ajustes, acceso o
  auditoría.
- Los barridos genéricos de la consola lite dejan `/console/lite/reservas` a
  esos dos ficheros.
