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
  que tiene, spec 047): con `reservas.*` y sin `booking.*`, o sin `reservas.*`.
  **No lo promueve**: se publica por la puerta; la pestaña enlaza a la pestaña
  Agente (`agents_pending_promotion`). Activar es además **pasar el cliente a
  Reservas** (abajo): el AgentSpec y el texto también, y las citas futuras.
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
  borrador nombra `booking.*` (herramientas, AgentSpec o texto). La lista de
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
| `calendar.py`, `calendar_sync.py` | P3: choques con Google Calendar y la sincronización |

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
  edita en Ajustes de Reservas (`PUT /business-hours`, que escribe en la ficha) o
  en Negocio de la consola de partners (`PUT /console/clients/{ref}/business/hours`).
- **Servicios no reservables** (spec 047, T058): un producto, un menú o una
  consulta no llevan duración (`bookable = false`, `duration_minutes` nulo). No
  tienen huecos (`not_bookable`) y Reservas no los lista: son de la ficha. Uno
  reservable dura de 5 a 480 min, en pasos de 5. El precio tiene tipo: sin precio,
  gratis o un importe (`price_kind`). Un servicio cambiado aquí es un cambio de la
  ficha: los agentes lo usan desde el siguiente mensaje.
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
| `reservation-calendar-cron` | 120 s | P3: el ocupado de Google entra, los «Ocupado» salen. Sin `composio_api_key` no hace nada (el cliente simulado del proveedor borraría el ocupado real) |

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

Solo Google (decisión del owner). Usa la conexión de Google Calendar que el
cliente hizo en el proveedor de consentimientos (spec 023); cada persona del
equipo se asocia a un calendario de esa cuenta (`PUT …/staff/{id}/calendar`).
Lo hace el sistema: las herramientas de Google Calendar del agente siguen
bloqueadas. Entra el «ocupado» (solo inicio y fin, `reservation_busy`); sale cada
reserva viva como «Ocupado» sin cliente ni servicio; a la vuelta se reconoce
por el id del evento guardado en la reserva, no por un texto que cualquiera
puede escribir en una invitación. El calendario de cada persona tiene que ser
de la cuenta conectada (`unknown_calendar` si no). Los nombres de las acciones y argumentos del proveedor viven en
`ComposioGoogleCalendar`: **verificar contra el conector real en staging**
antes de encenderlo para un cliente.

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
- `tests/isolation/test_reservas_auto_pass_scope.py` (spec 048): el paso
  automático de un cliente no lee ni escribe nada de otro — ni su sector, ni sus
  servicios y su equipo, ni sus agentes, citas, pruebas, ajustes, acceso o
  auditoría.
- Los barridos genéricos de la consola lite dejan `/console/lite/reservas` a
  esos dos ficheros.
