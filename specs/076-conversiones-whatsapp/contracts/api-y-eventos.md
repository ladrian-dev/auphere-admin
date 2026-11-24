# Contratos — spec 076

Lo que cruza una frontera: el stream del webhook al worker, la API de la consola, la API lite, lo que sale a Meta y los logs. Los nombres de campo son código y van en inglés.

## 1. Stream de entrantes: `referral_json`

Una clave más en el `fields` plano que `api/webhooks/meta.py` escribe con `xadd_capped`. Solo se escribe si sobrevive alguna clave.

```json
{
  "source_type": "ad",
  "source_id": "120211234567890",
  "source_url": "https://fb.me/…",
  "headline": "2x1 en cortes este mes",
  "body": "Reserva por WhatsApp",
  "media_type": "image",
  "ctwa_clid": "ARAkLkA8rmlFeiCktEJ…",
  "ref": "…"
}
```

**Lista blanca y topes**, en caracteres. Lo que pasa del tope se corta, y cualquier otra clave se descarta.

| Clave | Tope |
|---|---|
| `source_type` | `ad` o `post`; cualquier otro valor descarta el anuncio entero |
| `source_id` | 64 |
| `source_url` | 512 |
| `headline` | 200 |
| `body` | 500 |
| `media_type` | 16 |
| `ctwa_clid` | 256 |
| `ref` | 128 |

El worker la parsea en `InboundEvent.referral`. Un JSON roto se registra como `inbound.referral_unreadable`, con `tenant_id`, y el mensaje sigue su curso.

## 2. Consola de partners

Todas las rutas cuelgan de `/console/clients/{ref}` y usan `client_scope`. Con otro `ref` responden el 404 opaco de siempre (`test_console_scope.py`). Ninguna respuesta lleva campos `body`, `text`, `message`, `content` ni `reason`, ni nombres o teléfonos de clientes.

### 2.1 Bloque `ad_measurement` en la página del número

Va en `GET /console/clients/{ref}/channels/{channel_id}` (`ChannelPageOut`). **Si el número no admite la medición, el campo no existe** (research D10).

```json
{
  "ad_measurement": {
    "state": "on",
    "enabled": true,
    "dataset_linked": true,
    "sent_7d": 12,
    "last_error": null,
    "reconnect_config_id": "1234567890"
  }
}
```

- `state` vale `on`, `off` o `reauthorize`.
- `enabled` dice si está encendida, también cuando `state` es `reauthorize` (un número encendido que perdió el permiso): la consola ofrece «Apagar» solo si es `true`.
- `last_error`, cuando lo hay: `{ "code": "page_required", "at": "2026-…", "hint": "page_required" }`. `hint` es una clave de i18n de la consola, no un texto.
- `reconnect_config_id` (vacío si no hay ninguna puesta) es la configuración del registro insertado que usa «Volver a conectar». La elige la API según el modo del número (Cloud API o coexistencia): la de pruebas de ese modo si su ajuste está puesto, y si no la normal (research D6). La consola no elige.

### 2.2 Activar o desactivar

`PUT /console/clients/{ref}/channels/{channel_id}/ad-measurement`, con `client_scope("channels:write")`.

```json
{ "enabled": true, "confirm_data_sharing": true }
```

| Respuesta | Cuándo |
|---|---|
| `200` con el bloque `ad_measurement` | Activada o desactivada |
| `404` opaco | Número de otro cliente, o que no admite la medición |
| `409 {"code": "reauthorize"}` | El token del número no tiene `whatsapp_business_manage_events` |
| `422 {"code": "confirm_required"}` | Activar sin `confirm_data_sharing: true` |
| `502 {"code": "meta_unavailable"}` | Meta falló al crear u obtener el conjunto de datos; no se activa nada |

Cada cambio escribe en `audit_log` la acción `console.channel.ad_measurement`, con `actor` igual al de la consola y `target` igual a `channel:{id}`. `after_json` lleva `{"enabled": …, "confirm_data_sharing": …, "meta_dataset_id": …}`.

### 2.3 Informe de anuncios

`GET /console/clients/{ref}/ads/report?days=30`, con `client_scope("conversations:read")`. `days` admite 7, 30 o 90; cualquier otro valor da 422.

```json
{
  "days": 30,
  "rows": [
    {
      "ad_id": "120211234567890",
      "ad_kind": "ad",
      "ad_headline": "2x1 en cortes este mes",
      "ad_url": "https://fb.me/…",
      "conversations": 41,
      "bookings": 9,
      "amounts": [{ "currency": "CLP", "amount_minor": 135000 }]
    }
  ]
}
```

- Las filas van ordenadas por `bookings` y después por `conversations`, de más a menos.
- Los clics sin `source_id` se agrupan en una fila con `ad_id: null`.
- `amounts` lleva una entrada por moneda. Las reservas sin precio cuentan en `bookings` y no suman importe.

## 3. Consola lite: Bandeja

`GET /console/lite/inbox/conversations/{conversation_id}` (`ConversationDetailOut`) gana un campo:

```json
{ "ad_origin": { "kind": "ad", "headline": "2x1 en cortes este mes", "url": "https://fb.me/…" } }
```

- Vale `null` si el contacto no tiene ningún clic.
- Es el último clic del contacto de esa conversación.
- No lleva `ctwa_clid`.

Como cambia la API lite, se regeneran `apps/mobile/src/api/openapi.json` y `schema.gen.ts`. `scripts/export_openapi.py --check` falla si no están al día.

## 3b. Cancelaciones

Un `OrderCanceled` lleva el mismo `user_data` (el mismo clic o el teléfono), el mismo `custom_data` y el mismo `source_id` que su original. Su `event_id` es `"reservation:{id}:OrderCanceled"`. Solo sale después de que el original haya salido (data-model).

## 4. Lo que sale a Meta

Versión de Graph: la de `MetaClient` (`v26.0`, `settings.meta_graph_api_version`).

### 4.1 Permisos del token

`GET /debug_token?input_token={token del número}`, con el token de la app (`{app_id}|{app_secret}`). El permiso está concedido si `data.scopes` o `data.granular_scopes[].scope` contiene `whatsapp_business_manage_events`.

### 4.2 Conjunto de datos

`POST /{waba_id}/dataset`, con el token del número. La respuesta es `{"id": "<dataset id>"}`, y si ya existe uno devuelve ese.

### 4.3 Un evento

`POST /{meta_dataset_id}/events`, con el token del número. **Un evento por petición** (research D8).

Con clic de anuncio:

```json
{
  "data": [{
    "event_name": "Purchase",
    "event_time": 1764000000,
    "event_id": "reservation:6f1c…:Purchase",
    "action_source": "business_messaging",
    "messaging_channel": "whatsapp",
    "user_data": {
      "whatsapp_business_account_id": "1234567890",
      "ctwa_clid": "ARAkLkA8rmlFeiCktEJ…"
    },
    "custom_data": { "currency": "CLP", "value": 15000 }
  }],
  "partner_agent": "auphere"
}
```

Sin clic, `user_data` es:

```json
{
  "whatsapp_business_account_id": "1234567890",
  "whatsapp_phone_number_id": "1098765432",
  "ph": ["<sha256 del teléfono normalizado>"]
}
```

**Normalización del teléfono**, según Meta: solo dígitos, con código de país y sin ceros iniciales, y después SHA-256 en hexadecimal. Caso de prueba de su página: `(650)555-1212`, normalizado `16505551212`, da `e323ec626319ca94ee8bff2e4c87cf613be6ea19919ed1364124e16807ab3176`.

**Otras reglas:**
- `custom_data` solo va si hay importe. `value` va en unidades mayores: `value_minor` dividido por 1 en las monedas sin decimales (`services_catalog.ZERO_DECIMALS`) y por 100 en el resto.
- `LeadSubmitted` va sin `custom_data`.
- `test_event_code` se añade al cuerpo solo si `NEXUS_META_CAPI_TEST_EVENT_CODE` está puesto, lo que solo ocurre en staging.

**Qué hace el despachador con cada respuesta de Meta.** Los códigos de permiso y de Página son **provisionales**: ninguna página leída los da, y se fijan con las respuestas reales de staging.

| Respuesta | Qué pasa |
|---|---|
| 2xx | `sent` |
| `MetaTransientError` o `MetaRateLimitedError` | Reintento con espera de 1 min × 2^n, hasta 6 intentos |
| `TokenInvalidatedError`, o error de permiso (código 10 o 200) | `failed`, y la medición del número queda con `last_error_code = reauthorize` |
| Error que pide una Página | `failed`, y `last_error_code = page_required` (**aún sin productor**: el código de Graph se fija en T026; hasta entonces sale como `meta_<code>`) |
| Otro 4xx | `failed`, con `last_error_code = meta_<code>` |

## 5. Logs

Eventos de `structlog`. Cada uno lleva `tenant_id` explícito, y **ninguno lleva `ctwa_clid`, el teléfono ni su hash** (requisito 6.7).

| Evento | Campos |
|---|---|
| `ad_referral.stored` | `tenant_id`, `channel_id`, `source_type` |
| `ad_conversion.enqueued` | `tenant_id`, `channel_id`, `event_name`, `source_kind`, `attributed` (con clic o no) |
| `ad_conversion.sent` | `tenant_id`, `channel_id`, `event_name`, `attempts` |
| `ad_conversion.failed` | `tenant_id`, `channel_id`, `event_name`, `code`, `attempts` |
| `ad_conversion.discarded` | `tenant_id`, `channel_id`, `event_name`, `reason` (`measurement_off`, `opted_out` o `cancelled_before_send`) |
| `ad_measurement.changed` | `tenant_id`, `channel_id`, `enabled` |
