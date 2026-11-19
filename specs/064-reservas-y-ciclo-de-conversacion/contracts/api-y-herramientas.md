# Contratos — spec 064

Solo lo que cambia. Lo demás sigue como en `specs/043-reservas/contracts/` y
`specs/030-consola-lite-del-cliente/contracts/`.

## 1. `PATCH /console/lite/reservas/settings`

Sin cambio de forma. Cambia la validación de un campo:

| Campo | Antes | Ahora |
|---|---|---|
| `agent.min_notice_minutes` | entero de 0 a 1440 | uno de `0, 15, 30, 60, 120, 240, 1440` |

Otro valor: `422 {"code": "invalid", "field": "agent.min_notice_minutes", "message": …}`.
`GET` no cambia: sigue devolviendo `agent.min_notice_minutes`.

## 2. `reservas.find_slots` (herramienta del agente)

Un campo nuevo en la salida. La entrada no cambia.

```text
FindSlotsOutput
  date, closed, why_closed, slots[], first_fit, refused, services[], staff[]   (igual)
  too_soon: list[str]   # nuevo. "HH:MM", en orden. Vacío por defecto.
```

- `too_soon` trae las horas del día que están libres, que no han empezado y que
  el agente no puede dar solo por la antelación del negocio.
- `slots` sigue trayendo solo las que el agente puede dar.
- En Servicios y en Aforo. Vacío cuando el negocio no tiene antelación.
- La descripción de la herramienta dice: no ofrecer ni reservar una hora de
  `too_soon`. Decir que esa hora la confirma el negocio y ofrecer pasar la
  conversación a una persona. Nunca decir que no hay disponibilidad si `too_soon`
  trae algo.

`reservas.create` y `reservas.reschedule` ya devuelven `refused = "too_soon"`.
Su descripción añade la misma instrucción.

## 3. Acciones de una reserva (`POST /console/lite/reservas/bookings/{id}/{acción}`)

Sin rutas nuevas. Cambia cuándo aparecen dos acciones en `Booking.allowed`, solo
en Servicios:

| Estado | Condición | `allowed` añade |
|---|---|---|
| `done` | `now − ends_at ≤ 7 días` | `noshow` |
| `noshow` | `ends_at ≤ now` y `now − ends_at ≤ 7 días` | `undo` |

- `noshow` sobre `done` deja `noshow`. `undo` sobre un `noshow` pasado deja
  `done`.
- Fuera de la ventana, o en Aforo: `409 invalid_transition`, como cualquier
  acción que no toca.
- Ninguna de las dos encola un aviso al cliente final.
- La forma de `Booking` no cambia.

## 4. `POST /console/lite/reservas/bookings` (crear)

**No cambia.** `contact.phone` sigue siendo opcional en la API, porque la app
móvil de hoy lo manda vacío (requisito 3.5). La regla del teléfono vive en la
consola: el formulario y su acción de servidor (`createSchema`).

Regla de la consola: empieza por `+` y tiene de 8 a 15 dígitos, sin contar
espacios, guiones ni paréntesis.

## 5. `GET` y `PATCH /console/lite/inbox/settings` (nuevas)

Alcance: `lite_scope("inbox")`. Sin la Bandeja, 403 como el resto de `/inbox`.

```text
GET   → 200 {"autoclose_hours": 24 | 72 | 168 | 720 | null}
PATCH   {"autoclose_hours": 24 | 72 | 168 | 720 | null}
      → 200 {"autoclose_hours": …}
      → 422 {"code": "invalid", "field": "autoclose_hours"}   otro valor
```

- `null` es «nunca».
- El cliente sale del contexto de la petición. El cuerpo no lleva ningún
  identificador de cliente.
- Deja `inbox.settings_changed` en la auditoría, con el valor de antes y el de
  después.

## 6. El evento `resolved` del hilo

Sin cambio de forma. El cierre por inactividad lo escribe con:

```text
kind = "resolved", actor = "system", payload = {"reason": "inactivity"}
```

La consola lo dice como «Se cerró por inactividad». Un `resolved` sin ese
`payload` se dice como hoy.

## 7. Worker

### Cron nuevo: `inbox-autoclose-cron`

- En el planificador, cada 300 s.
- Por cada cliente activo con `inbox_autoclose_hours`, en su sesión acotada:
  resuelve las conversaciones que cumplen todo esto, hasta 200 por pasada:
  `status = OPEN`, `agent_active`, sin `assigned_user_id`, sin `waiting_reason`,
  con `attended_at`, y `last_message_at ≤ now − plazo`.
- Tras el commit, publica el evento de tiempo real de cada una.
- No avisa a nadie.
- Registro: `inbox_autoclose_cron.tenant` con `tenant_id` y `closed`, solo si
  cerró alguna.

### El historial del turno

`pipeline._load_recent_history` lee desde
`greatest(attended_at, context_from)`. Con `context_from` puesto, añade al final
una nota `{"role": "system"}` con el nombre saneado del contacto y con que ya es
un contacto del negocio.
