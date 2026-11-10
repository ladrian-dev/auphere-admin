# Contrato 043: el panel de operador activa Reservas

**Estado: congelado el 2026-10-22.**

Rutas que ya existen (spec 030), con `Authorization: Bearer <NEXUS_ADMIN_TOKEN>`
y, en las escrituras, `X-Operator-Id`. Solo se describe lo que cambia.

## `GET /admin/tenants/{tenant_id}/client-access`

Gana `reservas`:

```json
{
  "enabled": true,
  "modules": ["panel", "inbox", "reservas", "usage"],
  "…": "lo de la 030",
  "reservas": {
    "mode": "capacity",
    "capacity_kind": "restaurant",
    "live_future": 3,
    "agents_pending_promotion": [{"agent_id": "…", "name": "Agente de reservas", "version": 7}]
  }
}
```

- `reservas` es `null` si el cliente nunca tuvo ajustes de Reservas.
- `live_future`: reservas futuras vivas (`pending`, `confirmed`), para avisar
  antes de cambiar de modo.
- `agents_pending_promotion`: agentes con una versión preparada por la
  activación (o desactivación) que aún no se promovió. La pestaña enlaza a su
  pestaña Agente.

## `PUT /admin/tenants/{tenant_id}/client-access`

Cuerpo, campo nuevo opcional `reservas`:

```json
{"enabled": true,
 "modules": ["panel", "inbox", "reservas", "usage"],
 "reservas": {"mode": "capacity", "capacity_kind": "restaurant", "on_live": "refuse"}}
```

| Campo | Notas |
|---|---|
| `modules` | `max_length` pasa a 4; `Literal` gana `"reservas"` |
| `reservas.mode` | `services \| capacity`. **Obligatorio** si `reservas` está en `modules` y el cliente no tenía ajustes → si falta, 422 `reservas_mode_required` |
| `reservas.capacity_kind` | Obligatorio con `capacity` (`restaurant\|bar\|classes\|tours\|rooms\|spa`); prohibido con `services` |
| `reservas.on_live` | `refuse` (por defecto) \| `cancel_and_notify`. Solo cuenta si el modo **cambia** |

Respuestas nuevas:

| Código | `detail.code` | Cuándo |
|---|---|---|
| 422 | `reservas_mode_required` | Activar sin modo, por primera vez |
| 422 | `reservas_kind_required` | `capacity` sin tipo |
| 409 | `live_reservations` (+ `count`) | Cambiar de modo con reservas vivas y `on_live = refuse` |

Efectos, en una transacción:

1. Crea o actualiza `reservation_settings` (en la primera activación, con los
   valores de partida del modo y del tipo; al cambiar de tipo en Aforo, solo
   cambia el tipo: los números son del negocio).
2. Con `cancel_and_notify`: cancela las reservas futuras vivas
   (`cancelled_by = business`, `cancel_cause = mode_change`), deja su evento y
   encola el aviso `cancelled` de cada una con teléfono.
3. Si `reservas` entra o sale de `modules`: prepara, por cada agente activo, una
   versión **no activa** con (o sin) `reservas.*` y sin `booking.*`. No promueve.
4. Audita `client_access.updated` (como hoy) y, si cambió, `reservations.mode_changed`
   con `{from, to, cancelled}`.

Desactivar el módulo **no** borra ajustes ni reservas.
