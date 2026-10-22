# Contrato 043: `/console/lite/reservas/*` y lo que Reservas añade a otras rutas

**Estado: congelado el 2026-10-22.** Lo consumen la consola web (esta spec) y la
app Auphere Customers (spec 044), con el mismo principal de cliente. Un cambio
después de esta fecha se escribe aquí, con fecha, y se avisa a la sesión de la
app.

### Enmiendas

- **2026-10-22 (tarde), aditivas**, de lo que pidió la consola al construir:
  - `POST …/bookings/{id}/move` acepta `note` (opcional; sin él, la nota no cambia).
  - Cada entrada de `GET /waitlist` trae `booking_local` (`{date, start, end}` de
    la cita que quiere adelantar, o `null`).
  - Estados documentados: entrada `waiting | offered | accepted | removed |
    expired`; oferta `running | filled | empty | stopped`. `GET /waitlist` sin
    `status` es `status=waiting` (incluye `offered`); `status=all`, todas.
  - `data` de los eventos: `created {channel, origin}`, `moved` y
    `waitlist_accepted` `{from: {date, start}, to: {date, start}, notified}`,
    `cancelled {by, cause, notified}`, `notify_failed {why}`, `notified {kind}`.
  - `contact.next_booking` del detalle de la Bandeja viene siempre: `null` sin
    el módulo o sin reserva.
  - `GET /slots?walkin=true`: la franja en curso se evalúa como llegada sin
    reserva (aforo entero, sin `past`); `POST /walkins` usa esa franja.
- **2026-10-22 (noche)**, al cerrar el Panel:
  - `GET /summary`: `today.seats` (aditivo; Aforo, el aforo; Servicios, `null`).
  - La API se alinea con lo que este contrato ya decía: en `move`, `date` y
    `time` también se pueden omitir; `GET /offers?status=recent` ya no repite
    las que corren.
  - Toda escritura sobre una reserva relee la fila bajo candado antes de
    decidir: lo que otra transacción cambió entre la lectura y la escritura (el
    cron que libera) responde 409 `invalid_transition` o 412 `stale`, nunca se
    pisa.

## Reglas comunes

- **Puerta**: `require_client_principal("reservas")` (web: token de consola de
  60 s; app: token de teléfono). Sin el módulo, **403 opaco** (`No client
  access`). Una persona del partner: 403 en todas.
- **404 opaco**: un id que no existe y uno de otro cliente responden lo mismo,
  byte a byte.
- **Ninguna ruta acepta** `ref`, `tenant_id`, `partner_id` ni `customer_id`.
- **Escrituras**: las que crean aceptan `Idempotency-Key` (repetir devuelve lo
  mismo, sin duplicar). Las que cambian una reserva o los ajustes exigen
  `If-Match: <version>`; con otra versión, **412** `{"detail": {"code": "stale"}}`.
- **Errores de negocio** (cuerpo `{"detail": {"code": "...", ...}}`):

| Código HTTP | `code` | Cuándo |
|---|---|---|
| 409 | `slot_taken` | El hueco ya no está libre (otra reserva, bloqueo, aforo). Trae `first_fit` si se conoce |
| 409 | `invalid_transition` | La acción no vale en este estado o momento. Trae `status` |
| 409 | `live_reservations` | Archivar a una persona con reservas futuras vivas. Trae `count` |
| 409 | `hours_missing` | El negocio no tiene horario: no se puede reservar |
| 409 | `wrong_mode` | Ruta de Servicios con el cliente en Aforo, o al revés |
| 422 | (validación) | Campo fuera de rango. FastAPI estándar (`loc`, `msg`) |

- **Fechas y horas**: instantes en ISO 8601 UTC (`starts_at`). Para pintar sin
  calcular zonas, cada reserva trae también `local` en la zona del negocio.
  Parámetros de día: `YYYY-MM-DD` local. Horas: `HH:MM` local.
- **Dinero**: `price: {"amount_minor": 18000, "currency": "CLP"}` (unidad menor
  ISO 4217: CLP no tiene decimales). No es consumo: no va en US$.
- **Modo**: `services` | `capacity`. Las rutas marcadas *Servicios* o *Aforo*
  responden 409 `wrong_mode` en el otro.

---

## 1. Lo que Reservas añade a rutas que ya existen

### `GET /console/lite/me`

- `client.modules` y `nav` incluyen `"reservas"` cuando el cliente lo tiene
  (orden: `panel, inbox, reservas, usage`).
- Nuevo campo:

```json
"reservas": {"mode": "capacity", "capacity_kind": "restaurant"}
```

`null` sin el módulo. `capacity_kind` es `null` en Servicios; en Aforo,
`restaurant | bar | classes | tours | rooms | spa` (de ahí salen las palabras:
comensales, personas, plazas; «tiempo máximo de mesa», «duración de la sesión»…
Las palabras las pone cada pantalla, no la API).

### `GET /console/lite/inbox/conversations/{id}` — el contacto con su próxima reserva

`contact` gana:

```json
"next_booking": {"id": "…", "starts_at": "2026-10-23T23:30:00Z",
                 "local": {"date": "2026-10-23", "start": "20:30", "end": "22:00"},
                 "status": "confirmed", "service_name": null, "party_size": 4}
```

La próxima reserva viva (`pending`, `confirmed`) del contacto, o `null`. Solo si
el cliente tiene el módulo; si no, el campo no viene.

### `GET|PUT /console/lite/phones/current/notices`

Tipos nuevos en `kinds` (solo se aceptan con el módulo):

| Tipo | Qué avisa | Por defecto | Urgente |
|---|---|---|---|
| `reservas.agent_change` | Reserva nueva o cambiada por el agente. Una vez por reserva y cambio | sí | no |
| `reservas.cancelled_today` | Una reserva de **hoy** se canceló (por el cliente final o el sistema) | sí | no |
| `reservas.waitlist_accepted` | Alguien de la lista de espera aceptó un hueco | **no** | no |

Los no urgentes respetan `quiet_outside_hours` (spec 045). El payload del push
lleva `url` = `auphere-customers://reservas/{booking_id}` y nunca el nombre del
cliente final ni la nota (sí la hora y, en Aforo, cuántos).

---

## 2. Ajustes y horario

### `GET /console/lite/reservas/settings`

```json
{
  "mode": "capacity",
  "capacity_kind": "restaurant",
  "timezone": "America/Santiago",
  "currency": "CLP",
  "business_hours": {"monday": [{"from": "13:00", "to": "23:00"}], "…": "…", "sunday": []},
  "business_hours_label": "Lunes a sábado 13:00–23:00",
  "hours_missing": false,
  "slot_step_minutes": 30,
  "waitlist": {"enabled": true, "lead_minutes": 120},
  "agent": {"min_notice_minutes": 60, "max_days_ahead": 60},
  "confirmation": {"enabled": true, "when": "24h"},
  "reminder_enabled": true,
  "release_unconfirmed": true,
  "capacity": {
    "seats": 64, "stay_minutes": 90, "max_party": 10, "walkin_hold": 6,
    "schedule": {"model": "shifts", "step_minutes": 30,
                 "shifts": [{"name": "Comida", "from": "13:00", "to": "15:00"},
                            {"name": "Cena", "from": "20:00", "to": "22:00"}]}
  },
  "version": 4
}
```

- `capacity` es `null` en Servicios. `slot_step_minutes` y `reminder_enabled`
  solo significan algo en Servicios; `release_unconfirmed` y `confirmation.when`
  distinto de `24h`, solo en Aforo.
- `schedule` también puede ser `{"model": "slots", "step_minutes": 60, "from": "12:00", "to": "23:00"}`.
  `to` es la **última llegada** (inclusiva).

### `PATCH /console/lite/reservas/settings` — `If-Match`

Cuerpo: cualquier subconjunto de los campos editables, con la misma forma
(`waitlist`, `agent`, `confirmation`, `reminder_enabled`, `release_unconfirmed`,
`slot_step_minutes`, `capacity` —parcial dentro—). **No** acepta `mode` ni
`capacity_kind` (422). Devuelve los ajustes enteros.

Rangos: `lead_minutes ∈ {60,120,240,1440}`; `min_notice_minutes` 0–1440;
`max_days_ahead` 1–365; `seats` ≥ 1; `stay_minutes` 30–480 múltiplo de 15;
`max_party` 1–`seats`; `walkin_hold` 0–⌊`seats`/2⌋; `step_minutes ∈
{15,30,60,90,120}` y divide cada turno; turnos sin solaparse, 1–6.

### `PUT /console/lite/reservas/business-hours`

```json
{"hours": {"monday": [{"from": "09:00", "to": "14:00"}, {"from": "15:00", "to": "19:00"}], "…": "…", "sunday": []}}
```

Hasta dos tramos por día. Respuesta: `{"business_hours": {...}, "business_hours_label": "…"}`.
Es el horario del perfil del negocio (el mismo de `/me`). Las reservas que
quedan fuera se mantienen.

---

## 3. Equipo y servicios — *Servicios*

### `GET /console/lite/reservas/staff?archived=false`

```json
{"items": [{"id": "…", "name": "Lucía", "email": "lucia@…" ,
            "hours": null, "effective_hours": {"monday": [{"from": "09:00", "to": "14:00"}, {"from": "15:00", "to": "19:00"}], "…": "…"},
            "position": 1, "archived": false,
            "calendar": {"status": "none"}}]}
```

- `hours: null` = usa el horario del negocio; `effective_hours` es el que vale.
- `calendar.status`: `none | connected` (+ `calendar_name`, `last_sync_at`) —
  P3; hasta entonces siempre `none`.

### `POST /console/lite/reservas/staff` — `Idempotency-Key`

`{"name": "Lucía", "email": null, "hours": null}` → 201, la persona.

### `PATCH /console/lite/reservas/staff/{id}`

Cualquier subconjunto de `name`, `email`, `hours`, `position`. → la persona.

### `POST /console/lite/reservas/staff/{id}/archive`

204. 409 `live_reservations` con `count` si tiene reservas futuras vivas.

### `GET /console/lite/reservas/services?archived=false`

```json
{"items": [{"id": "…", "name": "Corte y barba", "duration_minutes": 45,
            "price": {"amount_minor": 15000, "currency": "CLP"},
            "staff": "all", "staff_ids": [], "position": 1, "archived": false}]}
```

`price: null` = sin coste. `staff`: `"all"` o `"some"` (con `staff_ids`).

### `POST /console/lite/reservas/services` — `Idempotency-Key`

`{"name": "…", "duration_minutes": 45, "price_minor": 15000, "staff_ids": null}`
(`staff_ids: null` = todo el equipo). → 201.

### `PATCH /console/lite/reservas/services/{id}` y `POST …/{id}/archive`

Como el equipo. Archivar un servicio no toca las reservas que ya lo tienen.

---

## 4. Reservas

### El objeto `Booking`

```json
{
  "id": "…",
  "mode": "services",
  "status": "pending",
  "starts_at": "2026-10-22T19:30:00Z",
  "ends_at": "2026-10-22T20:15:00Z",
  "local": {"date": "2026-10-22", "start": "16:30", "end": "17:15"},
  "party_size": 1,
  "staff": {"id": "…", "name": "Lucía"},
  "service": {"id": "…", "name": "Corte y barba", "duration_minutes": 45},
  "price": {"amount_minor": 15000, "currency": "CLP"},
  "contact": {"name": "Ana Pérez", "phone": "+56911112222", "conversation_id": "…"},
  "origin": "agent",
  "channel": "whatsapp",
  "created_by": {"kind": "agent", "name": "Agente de reservas"},
  "created_at": "2026-10-21T01:14:00Z",
  "note": "Pidió con Lucía",
  "arrived_at": null,
  "cancelled": null,
  "wants_earlier": false,
  "any_staff": false,
  "late_minutes": null,
  "clash": null,
  "allowed": ["confirm", "move", "cancel", "request_confirmation"],
  "version": 2
}
```

| Campo | Notas |
|---|---|
| `staff`, `service`, `price` | `null` en Aforo |
| `party_size` | 1 en Servicios |
| `contact.phone` | `null` si no lo dieron. `conversation_id` solo si hay una conversación visible en la Bandeja (y el cliente tiene `inbox`) |
| `origin` | `agent \| person \| waitlist \| walkin` |
| `channel` | `whatsapp \| phone \| in_person` |
| `created_by.kind` | `agent \| person \| system` |
| `cancelled` | `{"at": "…", "by": "customer\|business\|system", "cause": "mode_change\|release_unconfirmed\|null"}` |
| `late_minutes` | Aforo: minutos de retraso si `pending/confirmed`, ≥ 15 min pasada su hora y aún dentro de la estancia; si no, `null` |
| `clash` | P3: `{"source": "google", "local": {"start": "16:00", "end": "17:00"}}` o `null` |
| `allowed` | **Las acciones que la API acepta ahora mismo** para esta reserva: `confirm`, `move`, `cancel`, `request_confirmation`, `arrive`, `noshow`, `undo`. La pantalla pinta los botones de aquí; no recalcula las reglas |

### `GET /console/lite/reservas/bookings`

Parámetros: `from` y `to` (días locales, ambos incluidos, máximo 62 días),
`status` (repetible), `origin` (repetible), `staff_id`, `q` (nombre o teléfono,
≤ 80). Por defecto, todos los estados.

```json
{"items": [Booking, "…"], "closed_days": ["2026-10-26"], "truncated": false}
```

Orden: `starts_at` ascendente. Máximo 1 000; con más, `truncated: true`.

### `GET /console/lite/reservas/bookings/{id}`

`Booking` + `events`:

```json
"events": [
  {"kind": "created", "at": "…", "actor": {"kind": "agent", "name": "Agente de reservas"}, "data": {"channel": "whatsapp"}},
  {"kind": "reminder_sent", "at": "…", "actor": {"kind": "system", "name": null}, "data": {}},
  {"kind": "moved", "at": "…", "actor": {"kind": "person", "name": "Valeria Ríos"},
   "data": {"from": {"date": "2026-10-22", "start": "16:00"}, "to": {"date": "2026-10-22", "start": "16:30"}, "notified": true}}
]
```

`kind`: `created, confirmed, confirmation_requested, reminder_sent, replied_yes,
replied_no, moved, cancelled, arrived, noshow, undone, done, waitlist_joined,
waitlist_accepted, notified, notify_failed, released`. Los textos los compone la
pantalla. `notify_failed.data.why`: `no_phone | no_template | opted_out |
no_channel | send_failed`.

### `POST /console/lite/reservas/bookings` — `Idempotency-Key`

```json
{"date": "2026-10-23", "time": "10:00",
 "staff_id": "…", "service_id": "…",
 "party_size": 4,
 "contact": {"name": "Ana Pérez", "phone": "+56911112222"},
 "note": null,
 "join_waitlist": false,
 "notify": true}
```

- *Servicios*: `staff_id` y `service_id` obligatorios; `party_size` se ignora.
  `join_waitlist: true` = «avisarle si se libera un hueco antes» (crea la entrada
  de la lista ligada a esta reserva).
- *Aforo*: `party_size` obligatorio; `staff_id`, `service_id` se ignoran. El
  negocio puede pasar del máximo por reserva (el agente no).
- `contact.phone` opcional. Con teléfono y `notify: true`, se envía la
  confirmación por WhatsApp.
- Nace `confirmed`, origen `person`, canal `phone`, `created_by` la persona.
- 201 → `Booking`. 409 `slot_taken` (con `first_fit` en Aforo:
  `{"date": "…", "time": "21:30"}` o `null`). 409 `hours_missing`.

### `POST /console/lite/reservas/bookings/{id}/move` — `If-Match`

`{"date": "…", "time": "…", "staff_id": "…", "party_size": 4, "notify": true}`
(lo que no cambie, se omite). Revalida. Una `pending` sigue `pending`; las demás
quedan `confirmed`. → `Booking`.

### `POST /console/lite/reservas/bookings/{id}/cancel` — `If-Match`

`{"notify": true, "offer_slot": true}`. `offer_slot` solo vale en Servicios y si
la lista está activa, falta la antelación mínima y hay candidatos (lo dice
`GET …/{id}/cancel-preview`); si no, se ignora. En Aforo, el sitio liberado se
ofrece solo según las reglas de la lista. → `Booking` + `"offer": {"id": "…", "candidates": 3} | null`.

### `GET /console/lite/reservas/bookings/{id}/cancel-preview`

```json
{"can_offer": true, "candidates": 3, "why_not": null}
```

`why_not`: `waitlist_off | too_soon | nobody_fits | not_services`.

### Acciones de estado — `If-Match`, sin cuerpo, → `Booking`

| Ruta | De → a | Cuándo (si no, 409 `invalid_transition`) |
|---|---|---|
| `POST …/{id}/confirm` | `pending` → `confirmed` | Futura |
| `POST …/{id}/request-confirmation` | (sin cambio) | `pending`, futura, con teléfono. Encola el mensaje. 409 si ya se pidió en los últimos 30 min |
| `POST …/{id}/arrive` | `pending`/`confirmed` → `arrived` | *Aforo*, hoy, desde 30 min antes de su hora |
| `POST …/{id}/noshow` | `pending`/`confirmed` → `noshow` | Hoy, a partir de su hora |
| `POST …/{id}/undo` | `arrived`/`noshow` → `confirmed` | Hoy; no en llegadas sin reserva |

### `POST /console/lite/reservas/walkins` — *Aforo*, `Idempotency-Key`

`{"party_size": 4, "name": null}` → 201 `Booking` (`origin: walkin`,
`channel: in_person`, `status: arrived`, `contact.name`: el nombre o «Sin
reserva» — la palabra la pone la pantalla si `name` es `null`; la API guarda
`null`). Usa el aforo entero (sin restar las guardadas), en la franja en curso.
409 `slot_taken` con `first_fit` si no cabe; 409 `invalid_transition` fuera de
servicio (con `next_time`).

---

## 5. Huecos y ocupación

### `GET /console/lite/reservas/slots?date=YYYY-MM-DD` — huecos para reservar

*Servicios*: `&service_id=…&staff_id=…` (`staff_id` opcional = cualquiera que
haga el servicio). `&exclude=<booking_id>` al mover.

```json
{"date": "2026-10-23", "closed": false,
 "slots": [{"time": "10:00", "staff_ids": ["…", "…"]}, {"time": "10:30", "staff_ids": ["…"]}]}
```

*Aforo*: `&party_size=4` (`&walkin=true` para una llegada; `&exclude=` al
cambiar).

```json
{"date": "2026-10-23", "closed": false,
 "slots": [{"time": "13:00", "shift": "Comida", "fits": true, "left": 22, "why": null},
           {"time": "13:30", "shift": "Comida", "fits": false, "left": 2, "why": "full"}],
 "first_fit": "14:00"}
```

`why`: `past | blocked | full | closed | block_overlap`. `left` = sitio para
reservar en esa franja (aforo − guardadas − presencia, mínimo de la estancia).

### `GET /console/lite/reservas/occupancy?from=…&to=…` — *Aforo* (máx. 31 días)

```json
{"seats": 64, "walkin_hold": 6, "stay_minutes": 90,
 "days": [{"date": "2026-10-22", "closed": false,
           "slots": [{"time": "20:30", "shift": "Cena", "present": 40, "arriving": 11, "arrived": 6,
                      "pending": 2, "blocked": null, "past": false}]}]}
```

`present` = personas dentro (reservas vivas y llegadas con la franja dentro de
su estancia); `arriving` = personas que llegan a esa franja; `arrived` = de
ellas, las que ya llegaron; `blocked` = `{"id": "…", "label": "Evento privado"}`
o `null`.

### `GET /console/lite/reservas/summary` — Panel web y «Hoy en Reservas» de la app

```json
{"mode": "services",
 "today": {"date": "2026-10-22", "bookings": 12, "confirmed": 9, "pending": 3, "next_at": "2026-10-22T19:30:00Z",
           "people": null, "inside_now": null, "arriving_next_hour": null, "seats": null},
 "week": {"occupancy_pct": 64, "agent_share_pct": 58},
 "month": {"noshow_pct": 4.2, "recovered": 3},
 "waitlist": {"waiting": 2},
 "clashes": 0,
 "upcoming": [Booking, "…"]}
```

- *Servicios*: `today.people`, `inside_now`, `arriving_next_hour` y `seats` son `null`.
  `week.occupancy_pct` = horas reservadas / horas abiertas del equipo (lunes a
  domingo de esta semana). `month.noshow_pct` = no-show / (atendidas + no-show)
  del mes; `null` sin datos. `month.recovered` = reservas que entraron por la
  lista de espera este mes; `null` con la lista apagada.
- *Aforo*: `today.people` (personas reservadas hoy), `inside_now`,
  `arriving_next_hour`, `seats` (el aforo: «dentro ahora: 18 de 64»); `week.occupancy_pct` = personas·hora reservadas / aforo ·
  horas de servicio de la semana.
- `upcoming`: hasta 4 reservas vivas de hoy a partir de ahora.
- `clashes`: P3; 0 hasta entonces.
- Cada bloque puede venir `null` si no se pudo leer, y `errors: ["week"]` lo dice
  (estado parcial, como `/home`).

---

## 6. Bloqueos — *Aforo*

### `GET /console/lite/reservas/blocks?from=…&to=…`

`{"items": [{"id": "…", "date": "2026-10-24", "from": "20:00", "until": "22:00", "label": "Cena de empresa", "created_by_name": "Valeria Ríos"}]}`

### `POST /console/lite/reservas/blocks` — `Idempotency-Key`

`{"date": "2026-10-24", "from": "20:00", "until": "22:00", "label": "Cena de empresa"}`
(`from`/`until`: franjas, `until` inclusiva; `label` 1–120 obligatoria). → 201
`{"block": {...}, "overlapping_bookings": 3}` (las que ya había: se mantienen).

### `POST /console/lite/reservas/blocks/{id}/remove`

204. No se borra: queda quitado.

---

## 7. Lista de espera y ofertas

### `GET /console/lite/reservas/waitlist?status=waiting&from=…&to=…`

```json
{"enabled": true, "items": [{
  "id": "…", "status": "waiting",
  "contact": {"name": "Marta Gil", "phone": "+56…"},
  "party_size": 2, "desired": {"date": "2026-10-23", "time": "20:30", "until": null},
  "service": {"id": "…", "name": "Corte", "duration_minutes": 30}, "staff": null,
  "booking_id": "…",
  "joined": {"kind": "agent", "name": null, "at": "…"},
  "fits_now": true,
  "offer": {"id": "…", "deadline_at": "…"}
}]}
```

- *Servicios*: `service`, `staff` (`null` = cualquiera), `booking_id` (la cita que
  quiere adelantar) y `desired.date` o `desired.until` («cualquier hueco hasta…»).
- *Aforo*: `party_size`, `desired.date` + `desired.time`; `fits_now` dice si cabe
  ahora.
- `offer`: la oferta abierta a esta persona, o `null`.

### `POST /console/lite/reservas/waitlist` — `Idempotency-Key`

*Aforo*: `{"name": "…", "phone": null, "party_size": 2, "date": "…", "time": "20:30", "in_person": false}`.
*Servicios*: `{"name": "…", "phone": "+56…", "service_id": "…", "staff_id": null, "date": null, "until": "2026-10-26"}`.
→ 201.

### `POST /console/lite/reservas/waitlist/{id}/remove` → 204

### `POST /console/lite/reservas/waitlist/{id}/offer` — *Aforo*

Ofrecer a mano si cabe y no hay otra oferta abierta para esa franja. → la
oferta. 409 `slot_taken` / `invalid_transition`.

### `GET /console/lite/reservas/offers?status=running|recent`

```json
{"items": [{
  "id": "…", "status": "running",
  "slot": {"local": {"date": "2026-10-22", "start": "10:00", "end": "10:45"},
           "staff": {"id": "…", "name": "Lucía"}, "service": {"id": "…", "name": "Corte y barba"}, "seats": null},
  "cancelled_by_name": "Ana Pérez",
  "window_minutes": 5,
  "candidates": [{"position": 1, "waitlist_id": "…", "name": "Marta Gil", "status": "waiting",
                  "deadline_at": "…", "answered_at": null}],
  "filled_booking_id": null,
  "created_at": "…"
}]}
```

`recent` = cerradas en las últimas 24 h. Estados de candidato: `queued, waiting,
noreply, accepted, late_taken, late_won, skipped, stopped`.

### `POST /console/lite/reservas/offers/{id}/stop` → la oferta

---

## 8. Calendarios — P3

### `GET /console/lite/reservas/calendar`

`{"provider": "google", "connected": true, "calendars": [{"id": "…", "name": "Lucía"}]}`
(`connected: false` y `calendars: []` si el cliente no lo ha conectado; se
conecta en la consola del partner o el panel de operador, como hoy).

### `PUT /console/lite/reservas/staff/{id}/calendar`

`{"calendar_id": "…"}` o `{"calendar_id": null}` para soltarlo. → la persona.
El id tiene que ser uno de `GET …/calendar` (la cuenta que el cliente conectó):
si no, 422 `unknown_calendar`; sin conexión, 409 `calendar_not_connected`; con el
proveedor caído, 409 `calendar_unavailable`.
