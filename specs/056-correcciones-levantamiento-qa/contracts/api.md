# Contrato de la API: spec 056

Lo que cambia en las rutas. Formas en JSON. Las que no aparecen no cambian.

## Rutas nuevas del partner (Requisito 3)

Todas exigen el permiso `client_access:manage` (owner y admin). `ref` es la referencia del cliente. Un cliente ajeno o inexistente da el mismo 404 opaco. Ningún cuerpo lleva `partner_id` ni `tenant_id`.

### `GET /console/clients/{ref}/client-access`

```json
{
  "eligible": true,
  "ineligible_reason": null,
  "enabled": true,
  "modules": ["panel", "inbox", "reservas"],
  "whatsapp_connected": true,
  "reservas": {
    "mode": "services",
    "capacity_kind": null,
    "live_future": 0,
    "agents_pending_promotion": [],
    "agents_with_other_calendar": []
  },
  "members": [
    {
      "id": "…",
      "kind": "invitation|member",
      "email": "ana@negocio.com",
      "name": "Ana",
      "status": "pending|accepted|expired|revoked|active",
      "invited_at": "…",
      "expires_at": "…"
    }
  ]
}
```

Es la misma forma que la del panel, **sin** `partner`. Nada de la Bandeja: ni conversaciones, ni contactos, ni texto de avisos (4.2).

### `PUT /console/clients/{ref}/client-access`

```json
{
  "enabled": true,
  "modules": ["panel", "reservas"],
  "reservas": {
    "mode": "services",
    "capacity_kind": null,
    "on_live": "cancel_and_notify"
  }
}
```

| Error | Cuándo |
|---|---|
| 422 `unknown_module` | `agents`, `business` u otro |
| 422 `no_modules` | encendido sin módulos |
| 422 `inbox_requires_whatsapp` | Bandeja sin WhatsApp conectado |
| 409 `live_reservations` `{count}` | cambio de modo con reservas futuras y sin `on_live` |

### `POST /console/clients/{ref}/client-members`

Recibe `{ "email": "...", "name": "..." }` y responde:

```json
{
  "member": { "…": "…" },
  "accept_url": "https://console…/invite/…",
  "email_sent": true
}
```

| Error | Cuándo |
|---|---|
| 409 `access_disabled` | el acceso está apagado |
| 409 `account_is_partner_member`, `account_is_other_client`, `already_member` | los de hoy del servicio: correo con cuenta de partner, de otro cliente o ya dentro |
| 429 `rate_limited` | más de `console_client_invites_per_minute` invitaciones por partner y minuto |

### `POST /console/clients/{ref}/client-members/{member_id}/resend`

Misma respuesta que invitar. Retira el enlace anterior.

### `POST /console/clients/{ref}/client-members/{member_id}/revoke`

Responde 200 `{ "member": {…} }` y cierra sus sesiones y teléfonos en la misma transacción.

## Rutas nuevas del partner (Requisito 9)

### `POST /console/clients/{ref}/corrections/{batch_id}/accept`
### `POST /console/clients/{ref}/corrections/{batch_id}/discard`

Exigen el mismo permiso que aceptar una propuesta hoy. Aplican o descartan todas las correcciones del lote en una transacción y responden `{ "batch_id": "…", "applied": 2, "skipped": [] }`.

## Rutas que cambian

| Ruta | Cambio | Requisito |
|---|---|---|
| `PUT /admin/tenants/{id}/client-access` | `agents` y `business` dan 422 `unknown_module` | 2.3 |
| Todas las de `/console/lite/agents*` y `/console/lite/business*` | Responden siempre el 403 de un módulo que no se tiene | 2.5 |
| `GET /console/lite/inbox/conversations` | Gana `resolved: int` en el primer nivel. Se calcula con `filter=all` y la página vacía; si no, `0`. `has_any` se queda | 6.2 |
| `GET /console/lite/inbox/conversations[/{id}]` | `display_handle` lleva «+» y prefijo en WhatsApp | 13.3 |
| `GET /console/lite/notifications` | Cada aviso gana `handled: bool`. El contador de no leídos excluye lo atendido | 8.2 |
| `GET /console/lite/reservas/settings` | `hours` con la forma de la ficha: revisión, layout y días con `overnight`. Gana `location_hours: [{location, has_own_hours}]` solo de lectura | 5.1 |
| `PATCH /console/lite/reservas/business-hours` **(nueva, sustituye al PUT)** | Recibe `{ "revision": "…", "days": { "mon": [{"open": "09:00", "close": "13:00"}] } }` con solo los días tocados. Da 409 `revision_conflict`, o 422 `{code, field, day}` con `too_many_shifts`, `bad_step`, `overlap` | 5.1, 5.3 |
| `GET /console/lite/reservas/services` | Cada servicio gana `price: {kind: "none"\|"free"\|"amount", amount_minor?}` | 5.2 |
| `POST/PATCH /console/lite/reservas/services[/{id}]` | `price: PriceIn` sustituye a `price_minor`/`clear_price`. Duración de 5 a 480 en pasos de 5. Errores en la tabla siguiente | 5.2, 5.4, 11.2 |
| `POST/PATCH /console/lite/reservas/staff[/{id}]` | `email` con formato válido y máximo 254 caracteres | 11.3 |
| `POST/PATCH` de fechas especiales (ficha) | 422 `date_past` si `to < hoy` en la zona del negocio | 11.4 |
| `GET /console/auth/session` | Gana `expires_at` | 15.1 |

Errores de los servicios de Reservas:

| Error | Cuándo |
|---|---|
| 422 `rename_not_allowed` | el nombre es distinto del guardado |
| 422 `amount_too_large` | importe mayor que 10¹² unidades menores |
| 422 `bad_duration` | duración fuera de 5–480 o no múltiplo de 5 |
| 422 `category_too_long` | categoría de más de 40 caracteres |

## Contrato de la app

Las rutas que usa la app son las de `/console/lite/*` de arriba. Se regenera `apps/mobile/src/api/lite.gen.ts` con `pnpm gen` y lo comprueba `gen:check`.
