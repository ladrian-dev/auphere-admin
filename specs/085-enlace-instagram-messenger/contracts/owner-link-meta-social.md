# Contrato: el enlace de Instagram y Messenger

Las rutas públicas (`/console/channel-signup/*`) solo las atiende la credencial de servicio de la consola (`require_console_service()`), con el límite de 10 llamadas por minuto y token de la 040. Las de la consola piden `channels:write` (crear y anular) o `channels:read` (listar).

## Consola (partner)

### `POST /console/clients/{ref}/channels/{kind}/signup-link`

- `kind`: `instagram` | `messenger`. Otro valor da 422.
- **Cuerpo:** vacío.
- **201:** `{url, channel, expires_at}`. La dirección es `{console}/connect/{kind}/{token}`.
- **404:** el canal no está disponible para el partner (`_require_enabled`).
- **Efecto:** anula los enlaces vivos del cliente para ese canal.

### `GET /console/clients/{ref}/channels/whatsapp/signup-links` (existe)

Cada fila gana `channel`. Sigue listando los de todos los canales.

### `POST /console/clients/{ref}/agents/{agent_id}/channels/owner-links` (existe)

- **Cuerpo:** `{channel?: "whatsapp"|"instagram"|"messenger" = "whatsapp", mode?, replace?}`.
  - Con `whatsapp`, `mode` es obligatorio, como hoy.
  - Con `instagram` o `messenger`, `mode` no se envía.
- **Respuesta:** gana `channel`.
- **409 `link_pending_exists`:** se mantiene, ahora por agente **y canal**.

## Página pública (dueño)

### `GET /console/channel-signup/{token}` (existe)

`LinkInfoOut` gana dos campos:
- `channel`: `whatsapp` | `instagram` | `messenger`;
- `meta_page_config_id`: la configuración con Página, solo en Instagram cuando está configurada.

Para Instagram y Messenger:
- `meta_config_id` es la configuración de siempre del canal, la misma que da la oferta de la consola;
- `mode` es `meta_login`;
- `meta_signup_version` va a `null`.

Si el canal no está disponible para el partner del cliente, responde `state: "unknown"`, como un enlace que no existe.

### `POST /console/channel-signup/{token}` (existe, WhatsApp)

Con un enlace que no es de WhatsApp responde 409 `link_channel_mismatch`, y no consume el enlace.

### `POST /console/channel-signup/{token}/meta-social`

- **Cuerpo:** `{code: str 1..2048}`. `extra` está prohibido.
- **200** `{status: "connected", display_name, business_name}`: el enlace queda usado y el canal en el cliente, y en su agente si lo trae.
- **200** `{status: "choose", nonce, accounts: [{id, name, username, picture_url}]}`: el enlace sigue vigente.
- **409** `{code, help}`: los motivos de la consola (`code_exchange_failed`, `no_page`, `missing_permission`, `already_connected_elsewhere`, `subscribe_failed`). El enlace sigue vigente.
- **404/410:** los estados del enlace, como hoy (`link_unknown`, `link_used`, `link_expired`, `link_revoked`).
- **502:** Meta no responde. El enlace sigue vigente.
- **Origen de la elección:** `link:{link.id}`.

### `POST /console/channel-signup/{token}/meta-social/complete`

- **Cuerpo:** `{nonce: str 8..64, account_id: str 1..64}`.
- **200** `{status: "connected", display_name, business_name}`.
- **409** `pending_expired`: la elección caducó, o la inició la consola u otro enlace. El enlace sigue vigente.
- **404/410:** los estados del enlace.

**Común a las dos rutas:** la conexión corre bajo `tenant_scoped_session(link.tenant_id)` y relee el enlace con `FOR UPDATE`, como la de WhatsApp. El aviso al partner (`announce_connected`, `via: "owner_link"`) sale después del commit. Ninguna acepta ni devuelve `tenant_id`.
