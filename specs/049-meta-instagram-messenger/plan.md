# Plan de implementación: 049 — Instagram y Messenger

**Rama**: `develop` | **Fecha**: 2026-10-29 | **Spec**: [spec.md](spec.md) | **Auditoría**: [auditoria-docs-oficiales.md](auditoria-docs-oficiales.md)

## Resumen

Dos canales nuevos sobre la superficie que ya abrió WhatsApp:

- **Instagram:** inicio de sesión unificado, token de usuario del sistema y `graph.facebook.com`.
- **Messenger:** Facebook Login for Business, token de Página derivado del de usuario del sistema.

Comparten el webhook `/webhook/meta`, el canje del código del inicio de sesión, el cifrado de credenciales y el despachador de salida. Producción y staging comparten la app de Meta pero no los eventos: lo que no es de un entorno se reenvía al otro, firmado como llegó. La conexión vive en la consola de partners, solo para los partners que el operador habilite, hasta que Meta apruebe.

## Contexto técnico

- **Lenguaje:** Python 3.12 (FastAPI, SQLAlchemy 2 async, Alembic, httpx) · TypeScript / Next.js (consola y panel).
- **Dependencias:** ninguna nueva.
- **Almacenamiento:** PostgreSQL. Migración `0175_meta_social_channels`.
- **API de Meta:** Graph `v26.0` (la de los webhooks). Configuraciones de Facebook Login for Business:
  - Instagram `1157578836735566`;
  - Messenger `2188508105420190`.

  Son de la misma app en los dos entornos y no son secretas, así que van por defecto en `config.py`.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | El cliente se resuelve con `resolve_channel_tenant(provider, entry.id)` y nunca desde el payload. Garantía 4: la conversación es por canal y persona. Garantía 8: IGSID y PSID los pone el servidor, nunca el modelo. Prueba: `tests/isolation/test_23_meta_social_isolation.py` |
| II | Superficie | ☑ | `0`. API y webhook de la plataforma |
| III | Lo leído es dato | ☑ | El texto del DM o del comentario entra como mensaje de usuario, igual que el de WhatsApp. El nombre de perfil que da Meta es dato de presentación |
| IV | Acción `mutates` | ☑ | Tomar la conversación queda auditado con la persona (`inbox.takeover`). La etiqueta de agente humano solo se usa en mensajes con `actor_kind="member"`. Conectar, desconectar y borrar dejan auditoría con quién lo hizo |
| V | Estados honestos | ☑ | El canal sin habilitar no existe en la consola. «Requiere atención» lleva el motivo y el paso exacto para corregirlo. Fuera de ventana, el motivo es explícito (`window_closed`) |
| VI | Por API | ☑ | Todo por Graph API |
| VII | Test primero | ☑ | Parsers, reenvío, ventanas, partición de texto y conexión con pruebas unitarias. Despachador e isolation con integración |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | KB | ☑ | ADR-030 enmienda 1, ADR-049, `13-meta-canales-investigacion-2026-10` |

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | Garantías 1, 4, 6 y 8 | T040 |
| **Licencias** | Ninguna | — |
| **Medidor** | Cada respuesta pasa por el mismo pipeline (consumo del modelo). El saliente aceptado registra `channel.message` con su proveedor real, ya no `"meta"` a fuego | T024 |

## Diseño

### Identidad y datos

| Canal | `channels.type` | `provider` | `provider_identifier` | Persona (`customers.identifier`) |
|---|---|---|---|---|
| Instagram | `instagram` | `meta_instagram` | IG ID profesional (`entry[].id`) | IGSID |
| Messenger | `messenger` (nuevo valor del enum) | `meta_messenger` | Page ID | PSID |

- **Credenciales:** cifradas en `channels.config_encrypted`, con el mismo `FernetEncrypted` de WhatsApp. Se guarda `{token, client_business_id}`, y en Messenger además `page_token`.
- **Datos públicos** en `channels.config`: `username`, `name`, `picture_url`, `comments` y `last_health`.
- **Migración `0175`:**
  - `ALTER TYPE channel_type ADD VALUE 'messenger'`;
  - `partners.beta_channels varchar[] DEFAULT '{}'`, con check `<@ ARRAY['instagram','messenger']`;
  - las palabras nuevas del vocabulario de auditoría: `channel.instagram.connect`, `channel.messenger.connect`, `channel.meta_social.disconnect`, `channel.meta_social.purge` y `customer.meta_social.erase`.

### Paquete `nexus_channels/meta_social/`

- `graph.py` — `MetaSocialClient`, httpx sobre `graph.facebook.com/v26.0` con `appsecret_proof`. Llamadas:
  - `exchange_code`;
  - `me_client_business_id`;
  - `assigned_instagram_accounts`;
  - `pages` (`/me/accounts`, con alternativa `/{page_id}?fields=access_token`);
  - `subscribe` / `unsubscribe` / `subscribed_fields`;
  - `send_message`;
  - `reply_comment`;
  - `user_profile`;
  - `account_profile`.

  Los errores se clasifican: `MetaSocialTokenError` (190), `MetaSocialPermissionError` (10/200 y `(#200)` de mensajes desactivados), `MetaSocialWindowError` (10 con subcódigo 2018278 / 551) y `MetaSocialAPIError`.
- `webhook_adapter.py` — parsers puros de los dos formatos, `messaging[]` y `changes[]`:
  - mensajes con texto, adjuntos (`image`, `video`, `audio`, `file`, `share`, `story_mention`, `ig_reel`), `quick_reply`, `postback`, `reply_to`, `reaction`, `read`/`seen` y `referral`;
  - comentarios (`field=comments`);
  - `is_echo` y `is_deleted`.

  Salida: `InboundMessage` con `provider_identifier = entry.id` y `sender_identifier = sender.id`. Los comentarios llevan `raw_event_type="comment"` y `context_message_id="comment:{id}"`. Los adjuntos llevan `media.provider_media_id="url:{url}"`.
- `adapter.py` — `MetaSocialChannelAdapter` (`provider="meta_instagram"` o `"meta_messenger"`). Implementa:
  - `send_text`, con partición: IG 1000 bytes, Messenger 2000 caracteres;
  - `send_interactive`, con respuestas rápidas o botones según la capacidad del canal y texto de reserva;
  - `send_image/video/audio/document`, por URL;
  - `send_reaction`, solo IG;
  - `send_template`, que lanza `ChannelCapabilityError`;
  - `mark_as_read` (`sender_action: mark_seen`);
  - `fetch_media_bytes` (`url:`, solo hosts `fbcdn.net` / `cdninstagram.com` / `fbsbx.com`);
  - `fetch_profile`.

  Recibe `human_agent: bool` y `private_reply_to: str | None`:
  - `human_agent` pone `messaging_type=MESSAGE_TAG, tag=HUMAN_AGENT`;
  - `private_reply_to` pone `recipient={"comment_id"}` y, si el canal lo configura, publica la respuesta pública.
- `connect.py` — `MetaSocialConnector`: canje del código, elección del activo (uno conecta directo; varios guardan una conexión pendiente en Redis 10 min y se devuelve la lista), suscripción, perfil, persistencia, invalidación de la caché y comprobación de salud. `disconnect` borra el token al momento, desuscribe y marca `disconnected_at` para el borrado a 30 días.

### Webhook (`api/webhooks/meta.py` + `meta_social.py` nuevo)

1. Se verifica la firma, como hoy. `object` `instagram` o `page` va a `handle_meta_social(payload, body, signature)`. WhatsApp no cambia.
2. Por cada `entry`, `resolve_tenant(provider, entry.id)`. Si alguna no resuelve, hay `meta_webhook_peer_url` configurada y la petición no trae `X-Auphere-Forwarded`, se reenvía el cuerpo crudo con su `X-Hub-Signature-256` y la cabecera `X-Auphere-Forwarded: 1` (timeout 5 s, sin reintento; el otro entorno ignora lo que tampoco es suyo).
3. Lo resuelto se deduplica por `mid` o id de comentario (Redis 48 h + índice único durable), se descartan ecos y eventos sin texto ni adjunto, y se encola en el stream de su nivel con el mismo formato que WhatsApp (`provider` = proveedor real). Las lecturas, reacciones y ediciones se registran sin encolar turno (las reacciones se encolan como hoy en WhatsApp: el worker no responde a una reacción).

### Worker

- `bootstrap.py` — dos adapters más en `channel_adapters` (`meta_instagram`, `meta_messenger`), el lector de acuses por proveedor, el obtenedor de medios combinado (`url:` → adapter social, el resto → Meta WhatsApp) y dos crons nuevos (`meta_social_health_cron`, `meta_social_retention_cron`).
- `streams/outbound.py`:
  - `_DISPATCHABLE_CHANNEL_TYPES` gana `INSTAGRAM` y `MESSENGER`.
  - **Antes de enviar**, `meta_window.decide(channel_type, conversation.last_inbound_at, msg.actor_kind, private_reply)`:
    - agente < 24 h, `RESPONSE`;
    - persona < 24 h, `RESPONSE`;
    - persona 24 h–7 d, `HUMAN_AGENT`;
    - respuesta privada < 7 d desde el comentario;
    - si no, `failure_code="window_closed"` sin reintento.
  - El medidor usa `provider` en vez de `"meta"`.
  - `_maybe_flag_reauth` reconoce `MetaSocialTokenError` y pasa el canal a `degraded` con `config.needs_attention`.
- `persistence/messages.py` — `persist_outbound_message` acepta `context_message_id`. El turno de un comentario guarda la respuesta del agente con `context_message_id="comment:{id}"`, para que salga como respuesta privada. Esto arregla también el `conversation_id` de TikTok, que hoy se pierde.
- Perfil: la primera vez que una persona escribe sin nombre, el turno pide `fetch_profile` (sin bloquear: si falla, sigue).

### API de consola

`api/console/meta_social.py`, con prefijo `/clients/{ref}/channels/{kind}` y `kind ∈ {instagram, messenger}`:

- `POST /connect {code}` → `connected | choose{nonce, accounts[]}`;
- `POST /connect/complete {nonce, account_id}`.

El permiso es `channels:write` y la condición, `kind ∈ partner.beta_channels`; si no, 404. La desconexión reutiliza `POST /{channel_id}/disconnect`, que deriva a `MetaSocialConnector.disconnect` según el proveedor. `GET /overview` gana `meta_social: {instagram: {enabled, config_id}, messenger: {...}, app_id, graph_version}`.

En la bandeja (`lite/inbox.py` y la de partners), `_can_send` admite 7 días en Instagram y Messenger para una persona que tomó la conversación.

### Panel de operador

- **Partner → Acceso:** interruptores «Instagram (beta)» y «Messenger (beta)» que escriben `beta_channels`.
- **Catálogo de canales:** Instagram y Messenger en `beta`.
- **Cliente → Clientes finales:** borrar a una persona de un canal de Meta (Req. 5.6), con auditoría.

### Consola de partners

- `visible-channels.ts` — `instagram` y `messenger` visibles cuando el overview los trae habilitados.
- `meta-social-connect.tsx` — botón por canal; `FB.login` con su `config_id` y `response_type=code`; selector si hay varias cuentas.
- `channel-card.tsx` — tarjeta de IG o Messenger con nombre, usuario, estado, motivo de atención y desconexión.
- Etiquetas `messenger` en i18n y logos.

## Estructura

```text
apps/api/alembic/versions/0175_meta_social_channels.py
apps/channels/src/nexus_channels/meta_social/{__init__,graph,webhook_adapter,adapter,connect,exceptions,text}.py
apps/channels/tests/test_meta_social_*.py
apps/api/src/nexus_api/api/webhooks/{meta,meta_social}.py
apps/api/src/nexus_api/api/console/meta_social.py (+ channels.py, lite/inbox.py)
apps/api/src/nexus_api/services/{meta_window,meta_social_service}.py
apps/api/src/nexus_api/config.py, db/models/{channel,partner}.py, services/channel_catalog.py
apps/api/tests/{unit,integration,isolation}/test_*meta_social*.py
apps/worker/src/nexus_worker/{bootstrap.py, streams/outbound.py, streams/meta_social_*_cron.py, persistence/messages.py, runtime/dispatcher.py}
apps/console/src/components/channels/{meta-social-connect.tsx, channel-card.tsx, visible-channels.ts}
apps/console/src/app/(console)/clients/[ref]/channels/{page.tsx, actions.ts}, lib/backend/channels.ts
apps/admin/src/app/(dashboard)/partners/[id]/** (interruptores beta)
```

## Complexity Tracking

| Añadido | Por qué |
|---|---|
| Reenvío entre entornos | Meta no admite override de callback para `page` ni `instagram`; sin reenvío, staging no recibe nada mientras la URL apunte a producción, y viceversa |
| Conexión pendiente en Redis | El `code` es de un solo uso; si el negocio concede varias cuentas, hay que elegir sin volver a pedir el inicio de sesión |
| `partners.beta_channels` en vez de un módulo de la spec 032 | Los módulos son vistas del menú; un canal en beta no es una vista |
