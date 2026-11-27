# Modelo de datos: spec 080

**Sin cambios de esquema y sin migración.** Solo hay lecturas nuevas, y todas dentro de la sesión del cliente (RLS por `tenant_id`).

| Tabla | Qué se lee | Para qué | RLS |
|---|---|---|---|
| `conversations` | `customer_id`, `attended_at` y `context_from` de la conversación del turno | Saber de quién son las reservas y desde cuándo cuenta el ciclo (R1) | `tenant_id` |
| `reservations` | `id`, `status` y `customer_id` | Reservas vivas del cliente (R1) | `tenant_id` |
| `reservation_events` | `kind ∈ {created, moved}` y `created_at` | Que la reserva se creó o se movió en el ciclo (R1) | `tenant_id` |

**Escritura que cambia (R4):** `reservation_events.actor_kind` del evento `cancelled` hecho por `reservas.cancel` pasa de `customer` a `agent`, y `actor_name` guarda el nombre del agente. `data.by` sigue siendo `customer`, y `reservations.cancelled_by` también. Los eventos anteriores no se tocan.
