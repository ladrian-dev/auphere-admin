# Contrato — las rutas de consola

Todas cuelgan del ámbito de cliente que ya usan las demás (`/console/clients/{ref}/…`), donde `ref` es la referencia del partner y nunca un identificador interno. Dinero en `{amount_micros, currency}`, cien milésimas de la moneda de la cuenta.

Permisos: `schedules:read` para leer, `schedules:write` para crear, cambiar, pausar, archivar y ejecutar.

## Elegir cliente

### `GET /console/schedules/clients` · `schedules:read`

La primera pantalla: una tarjeta por cliente del partner.

```json
{ "clients": [ { "ref": "muna", "name": "Muna", "trade": "Tienda de bienestar",
  "agents": 2, "active_schedules": 2, "month_spend": {"amount_micros": 1280000, "currency": "USD"} } ] }
```

## La lista de un cliente

### `GET /console/clients/{ref}/schedules` · `schedules:read`

Parámetros: `agent` (id) y `state` (`active · paused · archived`), los dos opcionales.

Devuelve las rutinas, las cuentas de cada filtro y el reparto de la bolsa (requisitos 9.3 y 14).

```json
{
  "timezone": "America/Santiago",
  "counts": {"all": 3, "active": 2, "paused": 1, "archived": 0},
  "spend": {
    "bag": {"amount_micros": 20000000, "currency": "USD"},
    "conversations": {"amount_micros": 12840000, "currency": "USD"},
    "schedules": {"amount_micros": 1280000, "currency": "USD"}
  },
  "schedules": [
    {
      "id": "…", "name": "Altas de ayer en Notion",
      "agent": {"id": "…", "name": "Soporte", "state": "attending"},
      "when": {"cadence": "daily", "local_time": "09:00"},
      "next_run_at": "2026-11-28T12:00:00Z",
      "last_run": {"at": "2026-11-27T12:00:00Z", "status": "done"},
      "month": {"spend": {"amount_micros": 41000, "currency": "USD"}, "runs": 21},
      "state": "active", "pause_reason": null
    }
  ]
}
```

`state` y `pause_reason` son **el estado efectivo**, ya cruzado con el del agente y el saldo. El cliente sin ninguna rutina devuelve `schedules: []` y la consola enseña el estado vacío, sin botones apagados.

## El alta y los cambios

### `POST /console/clients/{ref}/schedules` · `schedules:write`

```json
{ "agent_id": "…", "name": "Altas de ayer en Notion",
  "instruction": "Revisa la vista «Usuarios» de Notion y dame la lista de los que se dieron de alta ayer.",
  "cadence": "daily", "local_time": "09:00", "email": true }
```

Según la periodicidad: `weekdays` para `weekly`, `day_of_month` para `monthly`, `run_date` para `once`.

`201` con la rutina. Errores de validación en `422` con el campo: `name_required`, `instruction_required`, `weekdays_required`, `day_of_month_out_of_range`, `limit_reached` (requisito 12.1).

Si el agente no está atendiendo, la rutina **nace en pausa** con `pause_reason: "agent_unavailable"` y la respuesta lo dice, para que la consola pueda avisar en el momento (requisito 8.3).

### `PATCH /console/clients/{ref}/schedules/{id}` · `schedules:write`

Los mismos campos, todos opcionales, con las mismas validaciones. Cambiar la instrucción **no toca el historial** (requisito 15.2).

### `POST …/{id}/pause` · `…/resume` · `…/archive` · `…/restore` · `schedules:write`

`pause` guarda motivo `manual`, y esa pausa no la deshace el sistema cuando el agente vuelva. `restore` deja la rutina **en pausa**, nunca ejecutándose (requisito 15.5). No hay `DELETE`: no se borra (requisito 15.6).

## Las próximas ejecuciones, antes de guardar

### `POST /console/clients/{ref}/schedules/preview` · `schedules:read`

Recibe una periodicidad y una hora, devuelve las tres próximas ejecuciones ya resueltas en la zona del negocio. Es lo que el alta enseña mientras el partner toca los controles (requisito 3.6). No escribe nada.

```json
{ "next": ["2026-11-28T12:00:00Z", "2026-11-29T12:00:00Z", "2026-11-30T12:00:00Z"],
  "timezone": "America/Santiago" }
```

## Ejecutar

### `POST /console/clients/{ref}/schedules/{id}/run` · `schedules:write`

`202 {"run_id": "…", "job_id": "…"}`. La ejecución queda con `trigger: "manual"` y se cobra igual que una de calendario. `409 bag_empty` si la bolsa está vacía (requisito 6.4).

### `POST /console/clients/{ref}/agents/{agent_id}/schedules/try` · `schedules:write`

«Probar ahora» desde el alta, sin haber guardado (requisito 6.3). Recibe la instrucción, ejecuta y **no crea rutina**. Misma respuesta que la anterior, con `schedule_id: null`.

## El historial

### `GET /console/clients/{ref}/schedules/{id}/runs` · `schedules:read`

Paginado por cursor, el más reciente primero.

```json
{ "runs": [
    { "id": "…", "scheduled_for": "2026-11-27T12:00:00Z", "trigger": "schedule",
      "status": "done", "attempts": 1, "duration_ms": 22000,
      "spend": {"amount_micros": 2000, "currency": "USD"},
      "answer": "Ayer se dieron de alta 14 usuarios…",
      "tools_used": ["Notion · consultar la vista Usuarios"],
      "withheld": null, "error_code": null,
      "instruction": "Revisa la vista «Usuarios» de Notion…" } ],
  "next_cursor": null }
```

Una ejecución `partial` trae `withheld` relleno y la consola lo pinta. Una `failed` trae `error_code` y `attempts: 3`.

## Lo que el contrato no abre

- **Ninguna ruta en la consola del cliente.** El negocio no ve sus rutinas (requisito 11.4).
- **Ningún `DELETE`.**
- **Ningún campo con un cliente final**, en ninguna dirección.
