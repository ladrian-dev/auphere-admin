# Contrato: API de la consola y del panel (050)

Prefijo de consola: `/console/clients/{ref}`. Las reglas de siempre se mantienen:
- el negocio sale de `{ref}` y nunca del llamante;
- las respuestas no llevan ids internos de tenant ni cuerpos de mensajes;
- toda escritura pide `channels:write` y deja auditoría con la persona.

## Iteración 1

### `GET /channels/{channel_id}` (página del canal, spec 047): campos nuevos

```json
{
  "whatsapp": {
    "username": "acme", "username_status": "approved",
    "name": {"decision": "REJECTED", "requested": "Acme Spa", "rejection_reason": "NAME_FORMAT_UNACCEPTABLE"},
    "messaging_limit": "TIER_2K",
    "account_review": "APPROVED",
    "alerts": [{"type": "PROFILE_PICTURE_LOST", "severity": "WARNING", "status": "ACTIVE", "at": "…"}]
  }
}
```

`visible_state.reason` admite además `account_review` y `account_alert`.

### `GET /channels/whatsapp/templates`: filas con `status` (Meta, en mayúsculas), `quality`, `category`, `pending_category` y `rejection_reason`

### Panel (operador)

- `POST /admin/tenants/{tenant_id}/channels/{channel_id}/two-step-pin` → `{rotated: true}`. Genera el PIN, lo envía a Meta, lo guarda cifrado y no lo devuelve nunca.
- `GET /admin/tenants/{tenant_id}/opt-outs?channel_id=` → lista con `scope`, `source` y fechas, sin cuerpos de mensajes.
- `POST /admin/tenants/{tenant_id}/opt-outs/{id}/lift` `{reason}` → levanta una baja `source=keyword`. Las de `meta` solo se levantan con `resume`: 409 `lifted_by_person_only`.

### Navegador: configuración del registro integrado

`GET /console/clients/{ref}/channels/overview` y la información del enlace del dueño devuelven `meta: {app_id, graph_version, signup_version: "v4", config_ids: {...}}`. La consola construye los `extras` con `signupExtras(mode, signup_version)` y no fija ninguna versión a mano.

## Iteración 2

### Plantillas: `POST /channels/whatsapp/templates` (amplía `TemplateCreateIn`)

```json
{
  "name": "pedido_listo", "language": "es", "category": "UTILITY",
  "header": {"format": "IMAGE", "media_upload_id": "upl_…"},
  "body": {"text": "Hola {{1}}…", "examples": ["Ana"]},
  "footer": "…",
  "buttons": [{"type": "QUICK_REPLY", "text": "Ver"}, {"type": "COPY_CODE", "example": "250FF"}],
  "authentication": {"add_security_recommendation": true, "code_expiration_minutes": 10, "otp_type": "copy_code"},
  "carousel": {"cards": [{"header": {"format": "IMAGE", "media_upload_id": "upl_…"}, "body": "…", "buttons": [...]}]}
}
```

- `POST /channels/whatsapp/templates/media` (multipart, máx. 16 MB, `image/jpeg|png`, `video/mp4`, `application/pdf`) → `{media_upload_id}`. El servidor hace la Resumable Upload de Meta.

Validaciones:
- `authentication` solo con `category=AUTHENTICATION`;
- `carousel` solo con `MARKETING`, de 2 a 10 tarjetas;
- un solo botón `COPY_CODE`.

Errores con `code` cerrado: `invalid_header_media`, `too_many_cards`, `category_mismatch`, `meta_rejected` con `reason` y `suggested_action`.

### Consumo

`GET /usage/meta-messages?ref=&month=YYYY-MM` →

```json
{"by_category": [{"category": "marketing", "sent": 120, "billable": 120}, {"category": "service", "sent": 980, "billable": 0}], "note": "billed_by_meta"}
```

## Iteración 3 — Catálogo

Base: `/channels/{channel_id}/catalog`.

| Método y ruta | Cuerpo | Respuesta / errores |
|---|---|---|
| `GET /` | — | `{state, source, catalog: {id, name, product_count}, visible}`. `source` es `auphere`, `feed`, `linked` o `coexistence` |
| `POST /` | `{name}` | Crea el catálogo en el portafolio del negocio, lo enlaza a la WABA y lo hace visible. 201 con el estado; 409 `already_linked`, `coexistence` |
| `PUT /` (existente) | `{catalog_id}` | Enlazar uno que ya existe (spec 022) |
| `GET /products?q=&availability=&cursor=` | — | `{items: [{retailer_id, name, price: {amount_cents, currency}, availability, visible, image_url, review: {status, reasons[]}}], next_cursor}` |
| `POST /products` | `{name, description?, price: {amount_cents, currency}, image_url \| image_upload_id, availability, url?}` | 201 con el producto; 409 `read_only_source` si el origen es `feed`; 422 por validación |
| `PATCH /products/{retailer_id}` | Campos a cambiar, más `If-Match` (revisión) | 200; 412 `changed_meanwhile` |
| `DELETE /products/{retailer_id}` | — | 204; auditoría con el nombre |
| `POST /products/images` | multipart | `{image_upload_id}`: la imagen se sirve a Meta por una URL firmada de corta vida |

## Iteración 4 — Perfil

- `GET /channels/{channel_id}/whatsapp-profile` → `{about, address, description, email, websites[], vertical, picture_url}`. En coexistencia, 404: la sección no existe.
- `PUT /channels/{channel_id}/whatsapp-profile` con los mismos campos y sus límites (about ≤ 139, description ≤ 512, websites ≤ 2), más `picture_upload_id?` → 200; 409 `coexistence`.
