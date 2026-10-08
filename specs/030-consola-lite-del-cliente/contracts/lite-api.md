# Contrato: `/console/lite/*`

Autenticación: `Authorization: Bearer <token de consola de 60 s>` con
`role: "client"`, verificado por `require_client_principal(<módulo>)`.
Respuestas comunes:

| Código | Cuándo |
|---|---|
| 401 | token ausente, caducado, repetido o mal firmado |
| 403 | la cuenta no es de un cliente, acceso apagado, persona revocada o módulo que el cliente no tiene. **Una persona del partner recibe 403 en todas** |
| 404 | objeto que no existe **o** que es de otro cliente — misma respuesta, byte a byte |

Ninguna ruta acepta `ref`, `tenant_id`, `partner_id` ni `customer_id`. Dinero
siempre en céntimos de US$ (`*_cents`), redondeado en servidor (spec 027).

## Identidad

### `GET /console/lite/me` — cualquier módulo

```json
{
  "user": {"id": "…", "email": "valeria@minegocio.com", "name": "Valeria Ríos"},
  "client": {"name": "Flor y Encanto", "modules": ["panel", "inbox", "usage"]},
  "balance_contact": {"kind": "partner", "name": "Amacrux"},
  "agents": [{"id": "…", "name": "Agente de soporte"}],
  "channels": [{"kind": "whatsapp", "connected": true}]
}
```

`balance_contact.kind` es `partner` o `auphere` (D10). `agents` solo lista los
activos.

## Panel (`panel`)

### `GET /console/lite/home`

Cada bloque es anulable; `errors` lista los que no se pudieron leer
(estado parcial, igual que `/console/home`).

```json
{
  "spend_month": {"total_cents": 1626, "by_agent": [{"agent_id": "…", "cents": 683}]},
  "conversations": {"last_7d": 75, "prev_7d": null, "daily": [{"day": "2026-10-02", "count": 5}]},
  "waiting": {"count": 3, "first_conversation_id": "…"},
  "balance": {"remaining_cents": 3013, "cap_cents": 5000, "days_left": 11, "assigned": true},
  "attention": [{"kind": "waiting", "count": 3}, {"kind": "balance_low", "days_left": 11}],
  "errors": []
}
```

- `by_agent` solo con más de un agente activo (D22).
- `waiting` solo si el cliente tiene `inbox`; si no, `null` y no hay fila
  `waiting` en `attention`.
- `prev_7d: null` → «sin semana anterior para comparar».
- `days_left: null` sin gasto en 7 días; `assigned: false` sin tope.
- `attention.kind`: `waiting` | `balance_low` (no llega a fin de mes) |
  `balance_out` (agotado).

## Consumo (`usage`)

### `GET /console/lite/usage/summary`

```json
{
  "balance": {"remaining_cents": 3013, "cap_cents": 5000, "days_left": 11, "assigned": true},
  "month": {"spent_cents": 1626, "projection_cents": 8401, "conversations": 70, "avg_per_conversation_cents": 23},
  "by_agent": [{"agent_id": "…", "name": "…", "conversations": 41, "spent_cents": 950, "share_pct": 58}],
  "errors": []
}
```

`projection_cents: null` cuando no se puede proyectar. `by_agent` solo con más
de un agente.

### `GET /console/lite/usage/spend?days=7|30|90&agent=<uuid?>`

Serie diaria en céntimos del cliente (`include_outside = false`), total y por
agente; `agent` filtra. Agente de otro cliente → 404.

### `GET /console/lite/usage/detail?days=…` · `GET /console/lite/usage/export.csv?days=…`

El detalle técnico de `/console/usage?client=<el suyo>` sin el bloque del
partner; el CSV solo con filas del cliente.

## Avisos (cualquier módulo)

`GET /console/lite/notifications?unread=&cursor=` ·
`GET /console/lite/notifications/unread-count` ·
`POST /console/lite/notifications/read-all` ·
`POST /console/lite/notifications/{id}/read`

Solo filas con `audience = 'client'` y el `external_client_ref` del cliente.

## Bandeja (`inbox`) — las únicas rutas con cuerpos de mensaje

### `GET /console/lite/inbox/conversations`

Query: `filter=all|unread|waiting|resolved` (por defecto `all`, sin
resueltas), `q`, `agent`, `cursor`, `limit ≤ 50`.

```json
{
  "items": [{
    "id": "…",
    "contact": {"name": "Martín Ruiz", "handle": "+54 11 4093 2275", "initials": "MR"},
    "channel": {"kind": "whatsapp"},
    "agent": {"id": "…", "name": "Agente de soporte"},
    "state": "waiting",
    "assignee": null,
    "last_message": {"at": "…", "author": {"kind": "contact"}, "preview": "Quiero que me devuelvan el dinero.", "has_media": false},
    "unread": true,
    "tags": ["Reclamo"]
  }],
  "next_cursor": "…",
  "counts": {"unread": 4, "waiting": 3},
  "has_any": true,
  "channel_kinds": ["whatsapp"]
}
```

`has_any` distingue una bandeja sin conversaciones de un filtro sin
resultados; `channel_kinds` decide si hay pestañas por tipo de canal (solo con
más de uno). `state`: `agent` | `waiting` | `person` | `resolved`. `author.kind`: `contact`
| `agent` | `member` (con `name` y `is_me`) | `operator`. Orden
`last_message_at desc, id`. `preview` recortado a 140 caracteres en servidor.

### `GET /console/lite/inbox/conversations/{id}`

Detalle para la cabecera, el cuadro y el panel de contacto:

```json
{
  "id": "…", "state": "person", "assignee": {"id": "…", "name": "Valeria Ríos", "is_me": true},
  "agent": {"id": "…", "name": "Agente de soporte"},
  "control_version": 7,
  "window": {"open": true, "closes_at": "…"},
  "channel": {"kind": "whatsapp", "connected": true},
  "contact": {"name": "…", "handle": "…", "first_message_at": "…", "conversations": 3},
  "summary": "Recibió el pedido #4821 con flores marchitas…",
  "waiting_reason": "Pide un reembolso por el pedido #4821…",
  "tags": ["Reclamo"], "note": {"body": "", "updated_at": null},
  "activity": [{"kind": "escalated", "at": "…", "actor": {"kind": "agent", "name": "…"}, "detail": "reembolso"}],
  "balance_out": false
}
```

`summary` y `waiting_reason` son `null` sin escalado (D19).
`contact.conversations` = 1 + reaperturas por el contacto + filas anteriores
del mismo contacto. `control_version`
es el `agent_active_version` que va en `If-Match`.

### `GET /console/lite/inbox/conversations/{id}/messages?before=<cursor>&limit≤100`

Mensajes y notas en orden cronológico, paginando hacia atrás:

```json
{"items": [
  {"type": "message", "id": "…", "at": "…", "direction": "inbound", "author": {"kind": "contact"}, "text": "…", "media": {"kind": "image", "filename": "IMG_2207.jpg", "transcript": null}},
  {"type": "message", "id": "…", "at": "…", "direction": "outbound", "author": {"kind": "agent", "name": "Agente de soporte"}, "text": "…", "delivery": "read"},
  {"type": "event", "id": "…", "at": "…", "kind": "escalated", "actor": {"kind": "agent", "name": "…"}, "detail": "reembolso"}
], "next_before": "…"}
```

`delivery`: `pending` | `sent` | `delivered` | `read` | `failed` (con
`failure_reason`).

### Acciones

| Método y ruta | Cuerpo | Respuesta | Errores propios |
|---|---|---|---|
| `POST …/{id}/takeover` | — · `If-Match: <control_version>` | detalle | 412 versión distinta (con el estado real) |
| `POST …/{id}/release` | — · `If-Match` | detalle | 412 · 409 si no la atiende quien la devuelve |
| `POST …/{id}/messages` | `{"text": "…"}` (1–4.096) | mensaje | 409 `not_assigned_to_you` · 409 `window_closed` · 409 `channel_disconnected` |
| `POST …/{id}/attachments` | multipart `file` (+ `caption` opcional) | mensaje | 413/415 con el límite (D15) · mismos 409 |
| `POST …/{id}/resolve` | — | detalle | — (idempotente) |
| `POST …/{id}/reopen` | — | detalle | — (idempotente) |
| `POST …/{id}/read` | — | 204 | — |
| `POST …/{id}/unread` | — | 204 | — |
| `PUT …/{id}/tags` | `{"tags": ["…"]}` (≤ 20, ≤ 40 car.) | `{"tags": […]}` | 422 |
| `PUT …/{id}/note` | `{"body": "…"}` (≤ 4.000) | `{"body", "updated_at"}` | 422 |

`…` = `/console/lite/inbox/conversations`. Todas auditadas (vocabulario
`inbox.*`) y publicadas en el canal de tiempo real.

### Otras

- `GET /console/lite/inbox/tags` → etiquetas usadas por el cliente (sugerencias).
- `GET /console/lite/inbox/counts` → `{"unread": 4, "waiting": 3}` para la persona de
  la sesión: el número junto a «Bandeja de entrada» en la barra.
- `GET|POST /console/lite/inbox/replies` · `PATCH /console/lite/inbox/replies/{id}` ·
  `DELETE /console/lite/inbox/replies/{id}` → respuestas guardadas `{id, title, body}`.
  `DELETE` **archiva** (`archived_at`), no borra; la lista no enseña las archivadas.
- `GET /console/lite/inbox/messages/{id}/media` → bytes del archivo
  (`Content-Type` y `Content-Disposition` del mensaje), por streaming (D16).
- `GET /console/lite/inbox/stream` → SSE (ver [realtime.md](realtime.md)).
