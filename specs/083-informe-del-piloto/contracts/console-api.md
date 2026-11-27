# Contrato: `GET /console/clients/{ref}/report`

Spec 083. Una lectura de la consola de partners, bajo el cliente `{ref}` del partner que llama.

- **Permisos**: `conversations:read` y `usage:read` (owner, admin, builder y analyst).
- **Parámetros** (query, obligatorios): `from` y `to`, fechas `YYYY-MM-DD` del calendario del cliente. Los dos incluidos.
- **Nunca** acepta `tenant_id` ni `partner_id`, y la respuesta no lleva ninguno.
- **Sin palabras de nadie**: ningún campo lleva cuerpos de mensaje, nombres, teléfonos ni el texto libre de un escalado. Los motivos son códigos (`cause`).
- **Dinero**: `{amount_micros, currency}` en cien milésimas de la moneda de la cuenta del partner (`contracts/console-api.md` de la 047, «Dinero»).

## Errores

| Código | Cuándo | Cuerpo |
|---|---|---|
| 401 | sin principal | el de siempre |
| 403 | al rol le falta un permiso | el de siempre |
| 404 | `{ref}` no es un cliente del partner (o no existe) | `{"detail": "Unknown client reference"}`, idéntico en los dos casos |
| 422 | `to` antes que `from` | `{"detail": {"code": "range_reversed"}}` |
| 422 | más de 92 días | `{"detail": {"code": "range_too_long"}}` |
| 422 | `to` después de hoy (en la zona del cliente) | `{"detail": {"code": "range_in_future"}}` |

## 200

```jsonc
{
  "from": "2026-11-10",
  "to": "2026-12-07",
  "timezone": "America/Caracas",
  "since": "2026-11-10T04:00:00Z",      // medianoche local de `from`
  "until": "2026-12-08T04:00:00Z",      // medianoche local de `to` + 1, o ahora si `to` es hoy
  "generated_at": "2026-12-07T15:02:11Z",
  "autoclose": true,                     // el cliente cierra conversaciones por inactividad
  "targets": { "without_person_pct": 70, "first_response_pct": 95, "first_response_seconds": 60 },

  "conversations": {
    "total": 214,
    "without_person": 163,
    "with_person": 51,
    "without_person_pct": 76.2,          // null sin conversaciones
    "series": [ { "day": "2026-11-10", "without_person": 6, "with_person": 2 } ],  // un día por fecha del periodo
    // Enmienda 2026-11-27 (13.1): por la hora y el día de la semana locales del primer mensaje del contacto.
    "by_hour": [ { "hour": 0, "without_person": 0, "with_person": 0 } ],           // 24 filas, de 0 a 23
    "by_weekday": [ { "weekday": 1, "without_person": 9, "with_person": 3 } ]      // 7 filas, ISO: 1 lunes … 7 domingo
  },

  "first_response": {
    "answered": 205,                     // conversaciones con al menos un envío del agente
    "within_target": 199,
    "within_target_pct": 97.1,           // null si answered = 0
    "median_seconds": 9,                 // null si answered = 0
    "p90_seconds": 21,
    "unanswered": 9                      // conversaciones del periodo sin envío del agente
  },

  "incidents": {
    "total": 58, "resolved": 55, "open": 3,
    "by_cause": [ { "cause": "escalated", "total": 31, "resolved": 30 } ],   // de más a menos
    "items": [ { "at": "2026-12-06T22:14:03Z", "cause": "booking_brake", "resolved_at": null } ],  // las 100 más recientes
    "truncated": false
  },

  "booking_brake": { "stopped": 12, "corrected": 10, "handed_over": 2 },

  "agenda": {                            // null si el cliente no tiene Reservas
    "created":   { "agent": 61, "person": 9, "customer": 1, "total": 71 },
    "moved":     { "agent": 14, "person": 3, "customer": 0, "total": 17 },
    "cancelled": { "agent": 8,  "person": 2, "customer": 5, "total": 15 },
    "released": 2,                       // liberadas sin confirmar (automático)
    "reminders": [
      { "kind": "reminder",         "sent": 80, "failed": 1, "skipped": 0 },
      { "kind": "ask_confirmation", "sent": 66, "failed": 0, "skipped": 2 }
    ]
  },

  "spend": {                             // null si no se pudo leer (estado parcial)
    "currency": "USD",
    "total":         { "amount_micros": 41280000, "currency": "USD" },   // conversaciones + pruebas a cargo del cliente
    "conversations": { "amount_micros": 40100000, "currency": "USD" },
    "client_tests":  { "amount_micros": 1180000,  "currency": "USD" },
    "meta":          { "amount_micros": 3020000,  "currency": "USD" },   // estimación
    "approx": false,                     // hubo cambio de moneda en lo de la bolsa
    "per_conversation": { "amount_micros": 192897, "currency": "USD" }   // null sin conversaciones
  }
}
```

### `cause`

`escalated` · `booking_unbacked` · `booking_brake` · `no_balance` · `agent_cap` · `paused_agent` · `paused_channel` · `paused_client` · `archived_client` · `channel_problem` · `agent_unpublished` · `no_model` · `provider_failure` · `turn_limit` · `reception_loop` · `agenda_not_ready` · `other`.

## Lo que cambia en `GET …/agents/{agent_id}/performance` y `…/conversations`

La forma no cambia. Cambia lo que cuentan:

- `conversations` y `series[].conversations` son ciclos con mensaje del contacto (requisito 2), por día local del cliente.
- `handed_to_person` es por historial (requisito 3).
- `since` es la medianoche local del primer día.
- En la lista, `outcome` y `handoff_reason` salen del historial de la fila (requisito 9.3).
