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
- Activar o desactivar **prepara** una versión del agente por cada agente
  activo: con `reservas.*` y sin `booking.*` (que escribían en `appointments`,
  que la consola no ve), o sin `reservas.*`. **No la promueve**: la pestaña
  enlaza a la pestaña Agente (`agents_pending_promotion`).
- Desactivar el módulo no borra ajustes ni reservas; las futuras siguen
  recibiendo sus recordatorios.

La parte de Reservas de esa llamada corre **bajo la RLS del cliente dentro de la
transacción del admin** (`services/reservations/admin.py: as_tenant`: cambia al
rol `nexus_app` y vuelve con `RESET ROLE`): la sesión del admin trabaja sin RLS y
las consultas del dominio no filtran por tenant a mano.

## El dominio (`apps/api/src/nexus_api/services/reservations/`)

| Fichero | Qué |
|---|---|
| `engine.py` | El motor de disponibilidad, **puro**: franjas de turnos o franjas (la última llegada incluida), presencia, `capacity_fit`, `first_fit`, huecos de Servicios. Lo usan la API, las herramientas y el worker |
| `core.py` | Contexto del cliente, crear/mover/cancelar con **candado + revalidación**, transiciones de estado y `allowed_actions`, historial, outbox, avisos al negocio |
| `waitlist.py` | Lista de espera y ofertas: candidatos, plazos (5 min Servicios, 15 min Aforo), aceptar a tiempo o tarde |
| `views.py` | La forma `Booking` del contrato, listado, ocupación por franja, resumen |
| `settings.py` | Valores de partida por modo y tipo; validación de lo que el negocio cambia |
| `admin.py` | La activación desde el admin |
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
- Los barridos genéricos de la consola lite dejan `/console/lite/reservas` a
  esos dos ficheros.
