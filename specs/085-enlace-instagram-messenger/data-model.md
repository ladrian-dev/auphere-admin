# Modelo de datos: el enlace para que el cliente conecte Instagram y Messenger

No hay tablas nuevas. Cambian una tabla y un valor de Redis.

## `channel_signup_links` (existe desde la migración 0160)

Pertenece a un cliente (`tenant_id`). **No tiene RLS, a propósito**: la página pública solo conoce el token (spec 040). La conexión corre después bajo `tenant_scoped_session(tenant_id del enlace)`.

| Campo | Hoy | Con la 085 |
|---|---|---|
| `channel` | `String(16)`, CHECK `IN ('whatsapp')` | CHECK `IN ('whatsapp','instagram','messenger')` |
| `mode` | `String(16)` obligatorio, CHECK `IN ('coexistence','cloud_api','whatsapp_login')` | Añade `'meta_login'` |
| `agent_id` | Opcional, con FK compuesta (0191) | Sin cambios |
| `channel_id` | El canal que conectó el dueño | Sin cambios: también para Instagram y Messenger |

**Migración `0244_owner_links_meta_social`:**
- amplía `ck_channel_signup_links_channel` y `ck_channel_signup_links_mode`;
- crea `ck_channel_signup_links_mode_per_channel`: `channel = 'whatsapp'` va con los tres modos de WhatsApp, e `instagram` y `messenger` solo con `meta_login`;
- cambia `uq_channel_signup_links_one_pending` de `(tenant_id, agent_id)` a `(tenant_id, agent_id, channel)`, con la misma condición: `consumed_at IS NULL AND revoked_at IS NULL AND agent_id IS NOT NULL`;
- la vuelta atrás borra antes los enlaces de Instagram y Messenger, y después restaura las restricciones de 0191.

**Ciclo de vida** (sin cambios):
- **vigente:** sin usar, sin anular y sin caducar;
- **usado:** `consumed_at`, al terminar la conexión;
- **anulado:** `revoked_at`, cuando lo anula el partner, o al crear otro del mismo cliente y canal, o del mismo agente y canal;
- **caducado:** `expires_at` pasado, a los 7 días.

**Cambio de regla:**
- **Sin agente:** crear un enlace anula los vivos del mismo cliente **y canal**.
- **Con agente:** también anula los caducados sin anular del mismo agente y canal, para que no choquen con el índice.

## La elección pendiente (Redis, existe desde la spec 049)

- **Clave:** `nexus:meta_social:pending:{tenant}:{nonce}`, que no cambia. Caduca a los 600 s.
- **Valor:** un JSON cifrado con Fernet: `{kind, token, business_id, page_tokens, accounts}`. Con la 085 añade **`origin`**: `"console"` o `"link:{link_id}"`. Si un valor anterior no lo trae, se lee como `"console"`.
- **Regla nueva:** `complete` rechaza con `pending_expired` cuando el `origin` pedido no coincide con el guardado.

## Lo que el partner ve de un enlace

`SignupLinkRow` y `OwnerLinkOut` ganan `channel`. `AgentChannelsOut` gana `pending_links: list[OwnerLinkOut]`, uno por canal, y conserva `pending_link`, el de WhatsApp.
