# Lo que la app necesita de la API (spec 044)

**Estado: superado el 2026-10-22 por los contratos congelados de la API** —
`specs/043-reservas/contracts/lite-api.md` y
`specs/045-consola-customers-mejoras-y-beta/contracts/lite-api.md` (en la rama de
`consolas-web`). **Mandan ellos.** La app se reconcilió con ellos ese mismo día
(T047): el adaptador `src/api/reservas.ts` habla su forma. Este documento queda
como registro de lo que la app pidió y de dónde difiere lo que la API dio
(tabla al final). Se envió a la sesión `consolas-web` el 2026-10-22. La API es suya (`apps/api`); esta spec no la
toca. Cuando sus `contracts/` existan, este documento se reconcilia con ellos
en la tarea T-RECONCILIAR de `tasks.md`: **manda su contrato**, y lo que cambie
se absorbe en un solo sitio de la app (`src/api/reservas.ts`, el adaptador).

Mientras tanto, los datos de ejemplo de desarrollo (Requisito 18) responden
**exactamente** con estas formas, para que el adaptador y las pantallas se
prueben contra algo concreto.

Todas las rutas van bajo `/console/lite/*` con el mismo `ClientPrincipal` que la
web (031): el teléfono no tiene permisos propios. El `tenant_id` sale del token.
Fechas `YYYY-MM-DD` y horas `HH:MM` son **la hora de pared del negocio**, en su
zona (`timezone`).

---

## 1. Quién y qué (`GET /console/lite/me`)

- `client.modules` y `nav` incluyen `"reservas"` cuando el módulo está activo.
- Nada más cambia aquí: el modo y la zona van en la configuración (§2).

## 2. Configuración (`GET /console/lite/reservations/config`)

```json
{
  "mode": "services",
  "timezone": "America/Santiago",
  "currency": "CLP",
  "hours": [
    { "weekday": 1, "open": "09:00", "close": "19:00" },
    { "weekday": 6, "open": "09:00", "close": "14:00" }
  ],
  "hours_label": "lunes a viernes 9:00–19:00, sábado 9:00–14:00",
  "waitlist": { "enabled": true, "lead_hours": 2, "editable": true },
  "confirmation": { "enabled": true, "when": "24h", "editable": true },
  "services": {
    "step_min": 30,
    "team": [{ "id": "p1", "name": "Marcos Soto", "calendar": "google" }],
    "catalog": [{ "id": "s1", "name": "Corte", "duration_min": 30, "price": 12000, "pro_ids": null }]
  },
  "capacity": null
}
```

En modo `capacity`, `services` es `null` y:

```json
"capacity": {
  "unit": "comensales",
  "capacity": 64,
  "stay_min": 90,
  "max_party": 10,
  "walkin_reserved": 6,
  "shifts": [
    { "name": "Comida", "from": "13:00", "to": "15:00", "every_min": 30 },
    { "name": "Cena", "from": "20:00", "to": "22:00", "every_min": 30 }
  ],
  "closed": [{ "weekday": 7, "shift": "Cena" }],
  "blocks": [{ "id": "b1", "date": "2026-10-08", "shift": "Cena", "reason": "Evento privado · cena de empresa" }],
  "editable": true
}
```

- `weekday`: 1 lunes … 7 domingo. Un día sin entrada está cerrado.
- `editable` (en `waitlist`, `confirmation`, `capacity`): si la persona puede
  cambiarlo desde la consola customers. La app no lo decide (clarificación 1).
- `calendar`: solo `google` o `none` (decisión del owner).

`PATCH /console/lite/reservations/config` con cualquier subconjunto de
`waitlist`, `confirmation`, `capacity.{capacity,stay_min,max_party,walkin_reserved}`
→ la configuración entera. `403 not_editable` si no se puede.

## 3. Reservas de un rango (`GET /console/lite/reservations?from=&to=`)

```json
{
  "now": "2026-10-22T11:20:00-03:00",
  "items": [
    {
      "id": "r1",
      "date": "2026-10-22",
      "start": "11:30",
      "end": "12:15",
      "state": "pending",
      "customer": { "name": "Camila Rojas", "phone": "+56 9 8765 4321" },
      "origin": "agent",
      "channel": "whatsapp",
      "by": null,
      "created_at": "2026-10-21T22:14:00-03:00",
      "arrived_at": null,
      "service": { "id": "s2", "name": "Corte y peinado", "duration_min": 45, "price": 18000 },
      "pro": { "id": "p1", "name": "Marcos Soto" },
      "party_size": null,
      "conflict": null,
      "history": [{ "at": "2026-10-21T22:14:00-03:00", "text": "El agente la reservó por WhatsApp" }],
      "actions": ["confirm", "cancel"]
    }
  ]
}
```

- `state`: `pending` · `confirmed` · `arrived` (solo Aforo) · `done` · `noshow`
  · `cancelled` (vocabulario común de la KB).
- `origin`: `agent` · `person` · `walkin` · `waitlist`. `channel`: `whatsapp` ·
  `phone` · `in_person`. Nada de Instagram ni «Reserve with Google».
- `actions`: **lo que la API deja hacer ahora** con esa reserva (`confirm`,
  `arrived`, `noshow`, `undo`, `cancel`). La app ofrece exactamente eso.
- `now`: la hora del servidor en la zona del negocio; la app calcula «ahora» y
  «Llega tarde» con ella, no con el reloj del teléfono.
- `conflict`: solo Servicios, cuando choca con un ocupado de Google Calendar.

## 4. Ocupación (`GET /console/lite/reservations/occupancy?from=&to=`)

```json
{
  "slots": [{ "date": "2026-10-22", "time": "13:00", "inside": 40, "capacity": 64, "blocked": null, "closed": false }],
  "days": [{ "date": "2026-10-22", "pct": 72, "closed": false }]
}
```

`slots` solo en Aforo (Día y Semana). `days` en los dos modos (Mes).

## 5. Huecos para «Nueva reserva» (`GET /console/lite/reservations/slots`)

- Servicios: `?date=&service_id=&pro_id=` (sin `pro_id` = cualquiera).
- Aforo: `?date=&party_size=`.

```json
{ "slots": [{ "time": "17:00", "pro": { "id": "p1", "name": "Marcos Soto" }, "left": null, "full": false }] }
```

## 6. Escrituras

| Qué | Ruta | Cuerpo | Respuesta | Errores |
|---|---|---|---|---|
| Crear | `POST /console/lite/reservations` + `Idempotency-Key` | `{date, time, customer:{name, phone?}, service_id?, pro_id?, party_size?}` | la reserva | `409 slot_taken`, `422 closed`, `422 blocked` |
| Acción | `POST /console/lite/reservations/{id}/{action}` | — | la reserva | `409 stale` (cambió entre medias) |
| Llegada sin reserva | `POST /console/lite/reservations/walk-ins` + `Idempotency-Key` | `{party_size, name?}` | la reserva | `409 no_room`, `422 closed` |
| Lista de espera | `GET /console/lite/reservations/waitlist` | — | `{items}` (§7) | — |
| Apuntar | `POST /console/lite/reservations/waitlist` | `{party_size, name?, date, time?}` | la entrada | — |
| Ofrecer | `POST /console/lite/reservations/waitlist/{id}/offer` | — | la entrada | `409 no_room` |
| Quitar | `DELETE /console/lite/reservations/waitlist/{id}` | — | `204` | — |
| Bloquear | `POST /console/lite/reservations/blocks` | `{date, shift, reason}` | el bloqueo | `422` sin motivo |
| Desbloquear | `DELETE /console/lite/reservations/blocks/{id}` | — | `204` | — |

Los códigos de error van en `detail.code`, como el resto de la API, y la app
los dice en una frase. Un `403` con el módulo apagado relee `/me` (031 R3.5).

## 7. Lista de espera

```json
{
  "id": "w1",
  "name": "Ignacio Fuentes",
  "phone": "+56 9 5555 1234",
  "wants": { "date": "2026-10-22", "time": "14:00", "party_size": 2, "service": null, "pro": null, "text": null },
  "state": "waiting",
  "fits": true,
  "offered_until": null,
  "joined_by": "agent",
  "by": null,
  "joined_at": "2026-10-21T19:02:00-03:00"
}
```

`state`: `waiting` · `offered` (con `offered_until`) · `accepted`. `fits`:
si cabe ahora (`null` si no aplica).

## 8. Tiempo real

Un evento `reservations.changed` (sin datos del cliente final) en la línea SSE
que ya existe (`/console/lite/inbox/stream`), o en una propia. La app relee.

## 9. Mejoras (spec 045)

| Dónde | Campo | Uso en la app |
|---|---|---|
| `ConversationItemOut` | `waiting_reason: str \| null`, `waiting_since: datetime \| null` | Grupo «Esperan a una persona» (R10.1). Sin `waiting_since`, sin tiempo (R10.2) |
| `ConversationDetailOut` | `waiting_since: datetime \| null` | «Espera hace N min» (R11.1). Sin él, la app usa el último `escalated` de `activity` |
| `ConversationDetailOut` | `next_reservation: {id, date, start, label} \| null` | «Próxima reserva» (R12) |
| `NoticesOut` | `quiet_outside_hours: bool`, `hours_label: str \| null` | Interruptor y su pista (R14.3). Sin el campo, no hay interruptor |
| `NoticesIn` | `quiet_outside_hours?: bool` | Guardarlo |
| `NoticeKind` | `reservations.changed`, `reservations.cancelled_today`, `reservations.waitlist_accepted` | R14.2 |
| Push | `url: auphere-customers://reservations/<id>?date=YYYY-MM-DD`, canal Android `reservations_v1`, categoría iOS `reservations` | R14.5, R14.6 |
| `LiteBalanceOut` (opcional) | `runs_out_on: date \| null` | «Te alcanza hasta…» (R13.1). Sin él, la app lo calcula de `days_left` |

**No hace falta** un bloque de Reservas en `LiteHomeOut`: la tarjeta «Hoy en
Reservas» y la atención de reservas sin confirmar salen de §3 con el día de
hoy (research D4), así el teléfono y la pestaña cuentan lo mismo.


---

## Reconciliación con los contratos congelados (2026-10-22, T047)

| Lo que la app pidió | Lo que da la API | Cómo lo absorbe la app |
|---|---|---|
| `/console/lite/reservations/*` | `/console/lite/reservas/*` (043) | Prefijo en el adaptador |
| `config` en una ruta | `settings`, `staff`, `services` y `blocks` por separado (043 §2, §3, §6) | `config()` las lee juntas y las une |
| Horas locales `start`/`end` y `now` en la lista | `Booking.local` y ningún `now` (043 §4) | «Ahora» con el reloj del teléfono en la zona del negocio (D3) |
| Acciones sin versión | `If-Match: version` en cada acción y en `PATCH /settings`; 412 `stale` | La reserva y los ajustes llevan su `version` |
| `actions` | `allowed` con `arrive`, `move`, `request_confirmation` | Se traducen; `move` y `request_confirmation` aún no están en el teléfono |
| Historial como texto | `events` con `kind` en el detalle (`GET /bookings/{id}`) | La hoja lee el detalle por id y compone las frases |
| Bloqueos por turno | Bloqueos por franjas `from`/`until` (043 §6) | El turno elegido se manda como sus franjas |
| `no_room` / `closed` en la llegada | 409 `slot_taken` / `invalid_transition` (043 §4) | El adaptador los traduce a las palabras de la app |
| Avisos `reservations.*` | `reservas.agent_change`, `reservas.cancelled_today`, `reservas.waitlist_accepted`; URL `auphere-customers://reservas/{id}` (043 §1) | Tipos y ruta renombrados |
| `waiting_reason`/`waiting_since` en la fila | `waiting: {reason, since}` (045 §2) | La fila lee el objeto |
| `next_reservation` | `contact.next_booking` (043 §1) | El contacto lo lee de ahí |
| `hours_label` en los avisos | `/me.business.hours_label` (045 §4) | Ajustes lo lee de `/me` |
| Ocupación del mes en los dos modos | `/occupancy` solo en Aforo (043 §5) | En Servicios el mes se calcula con las reservas y el horario |
| `editable` por ajuste | No existe: la persona puede cambiar lo que `PATCH` acepta | Todo lo de `PATCH` es editable; el horario y el equipo, en la web |

Pregunta abierta a `consolas-web`: el canal de Android y la categoría de iOS que
manda el push de Reservas (la app crea `reservations_v1` y `reservations`).
