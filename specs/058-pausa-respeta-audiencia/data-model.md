# Modelo de datos: La pausa respeta la audiencia

**Sin migración.** No hay tablas, columnas ni valores nuevos. El cambio está en
cuándo se escriben los valores que ya existen.

## Conversación (`conversations`, tenant, RLS por `tenant_id`)

| Campo | Qué cambia |
|---|---|
| `waiting_reason` | Con un contacto fuera de la audiencia vale `out_of_audience` aunque el cliente, el canal o el agente estén en pausa (antes, el motivo de la pausa). Si la conversación sigue en `escalated` por un motivo que no es de puerta, o está asignada, **no se toca** (antes se sobrescribía). |
| `status` | Una conversación `escalated` por un motivo de puerta, sin asignar, pasa a `open` cuando su contacto escribe fuera de la audiencia (requisito 2) o cuando corre la limpieza (requisito 3). |
| `attended_at`, `last_attended_inbound_at` | Sin cambios. Un mensaje fuera de la audiencia no marca atendida la conversación, como hoy con el cliente activo. |

### Transiciones nuevas

```
escalated (motivo de puerta, sin asignar)
    ── entrante fuera de la audiencia ──►  open, waiting_reason = out_of_audience
    ── limpieza --apply (canal strict) ─►  open, waiting_reason = out_of_audience

escalated (motivo que no es de puerta, o asignada)
    ── entrante fuera de la audiencia ──►  sin cambios
```

## Evento de conversación (`conversation_events`, tenant, RLS por `tenant_id`)

Se reutiliza el tipo `released`. Payload nuevo:
`{"why": "out_of_audience", "reason": "<motivo anterior>"}`. El actor es
`system`. No lleva texto del mensaje ni datos del contacto.

## Mensaje (`messages`, tenant)

`skipped_reason = "not_admin"` en los entrantes fuera de la audiencia, también
con el cliente en pausa. Es lo que Conversaciones pinta como «sin responder ·
número no permitido» (spec 024).

## Aviso de la consola (`console_notifications`, plataforma)

- No se crea ninguno `inbox.waiting` por un contacto fuera de la audiencia.
- Al liberar una espera (requisitos 2 y 3), su aviso pendiente pasa a
  `handled_at = now()` con `mark_waiting_handled`. La función filtra por partner y
  por referencia del cliente (spec 056).

## Push del cliente (`client_push_events`, tenant)

No se encola `inbox.waiting` para un contacto fuera de la audiencia.
