# Modelo de datos — spec 076

Una migración, `0241_ad_conversions`, que va detrás de la cabeza actual (`0240_respond_bindings_to_agents`). Crea tres tablas de tenant con el patrón de `0233_quedate_connector`:

- `ENABLE` y `FORCE ROW LEVEL SECURITY`;
- la política `<tabla>_tenant_isolation` sobre `app.tenant_id`;
- `GRANT` a `nexus_app`;
- FK de `tenant_id` a `tenants` con `ON DELETE CASCADE`;
- y **FK compuestas `(tenant_id, x_id)`** hacia las tablas de tenant, que tienen su `UNIQUE (tenant_id, id)`: `channels` en la 0176, `customers` y `conversations` en la 0172, `reservations` en la 0172.

La misma migración añade a `console_audit_vocabulary` la acción `console.channel.ad_measurement`.

Los modelos ORM van en `apps/api/src/nexus_api/db/models/ad_conversion.py`, con `UUIDPrimaryKey`, `TimestampMixin` y `TenantScopedMixin`.

## `customer_ad_referrals` — un clic de anuncio o de publicación

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid, no nulo | RLS |
| `customer_id` | uuid, no nulo | FK `(tenant_id, customer_id)` → `customers`, `ON DELETE CASCADE` |
| `conversation_id` | uuid, nulo | FK `(tenant_id, conversation_id)` → `conversations`, `ON DELETE SET NULL (conversation_id)` |
| `channel_id` | uuid, no nulo | FK `(tenant_id, channel_id)` → `channels`, `ON DELETE CASCADE` |
| `provider_message_id` | varchar(512), no nulo | El `wamid` del mensaje que trajo el anuncio |
| `source_type` | varchar(8), no nulo | `ad` o `post`; CHECK |
| `source_id` | varchar(64), nulo | |
| `source_url` | varchar(512), nulo | |
| `headline` | varchar(200), nulo | Texto del anunciante, saneado al mostrarlo |
| `ad_text` | varchar(500), nulo | El `body` del anuncio. Se llama así para no chocar con las reglas de campos de cuerpo |
| `media_type` | varchar(16), nulo | |
| `ctwa_clid` | varchar(256), nulo | **Se pone a NULL a los 90 días** (D9). Nunca sale en logs ni en respuestas de la API |
| `ref` | varchar(128), nulo | |
| `clicked_at` | timestamptz, no nulo | La hora del mensaje |

**Restricciones e índices.**
- `UNIQUE (tenant_id, provider_message_id)`: un reintento del webhook no duplica.
- `UNIQUE (tenant_id, id)`: para la FK compuesta desde `ad_conversion_events`.
- Índice `(tenant_id, customer_id, channel_id, clicked_at DESC)`, para el último clic de un contacto en un número.
- Índice `(tenant_id, clicked_at)`, para el informe y la retención.

**Reglas.**
- El clic que atribuye un resultado es el último del contacto **en el número del resultado** anterior a un instante `t`: `WHERE customer_id = :c AND channel_id = :ch AND clicked_at <= :t ORDER BY clicked_at DESC LIMIT 1`. Por eso el índice es `(tenant_id, customer_id, channel_id, clicked_at DESC)`.
- **El contacto se fija desde el servidor**: el del mensaje entrante. Nunca viene de una petición.

## `channel_ad_measurement` — la medición de un número

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid, no nulo | RLS |
| `channel_id` | uuid, no nulo | FK `(tenant_id, channel_id)` → `channels`, `ON DELETE CASCADE`; `UNIQUE (tenant_id, channel_id)` |
| `enabled` | bool, no nulo, `false` | |
| `meta_dataset_id` | varchar(64), nulo | El conjunto de datos de Meta de la cuenta de WhatsApp. No es secreto |
| `enabled_by` | varchar(255), nulo | El actor de la consola, como en `audit_log.actor` |
| `enabled_at` | timestamptz, nulo | |
| `disabled_by` | varchar(255), nulo | |
| `disabled_at` | timestamptz, nulo | |
| `last_error_code` | varchar(40), nulo | `reauthorize`, `page_required`, `meta_<código>`, `too_old` |
| `last_error_at` | timestamptz, nulo | |

**Reglas.**
- No hay fila hasta la primera activación. Sin fila, la medición está apagada.
- Activar sin `meta_dataset_id` no es posible: la API crea u obtiene el conjunto de datos antes de poner `enabled = true`.
- Un envío correcto limpia `last_error_*`.

## `ad_conversion_events` — la cola de eventos

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid, no nulo | RLS |
| `channel_id` | uuid, no nulo | FK `(tenant_id, channel_id)` → `channels`, `ON DELETE CASCADE` |
| `customer_id` | uuid, no nulo | FK `(tenant_id, customer_id)` → `customers`, `ON DELETE CASCADE` |
| `referral_id` | uuid, nulo | FK `(tenant_id, referral_id)` → `customer_ad_referrals`, `ON DELETE SET NULL (referral_id)`. Solo clics del mismo contacto y del mismo número |
| `cancels_event_id` | uuid, nulo | Solo en `OrderCanceled`: el evento que cancela. FK `(tenant_id, cancels_event_id)` → `ad_conversion_events`, `ON DELETE CASCADE`. Hereda su `referral_id`, `value_minor` y `currency` |
| `source_kind` | varchar(16), no nulo | `reservation` o `woo_order`; CHECK |
| `source_id` | varchar(64), no nulo | El id de la reserva o del pedido de la tienda |
| `event_name` | varchar(24), no nulo | `Purchase`, `LeadSubmitted`, `OrderCreated` u `OrderCanceled`; CHECK |
| `event_id` | varchar(128), no nulo | `"{source_kind}:{source_id}:{event_name}"`; `UNIQUE (tenant_id, event_id)` |
| `event_time` | timestamptz, no nulo | Cuándo ocurrió el resultado |
| `value_minor` | bigint, nulo | En unidades menores. Nulo en `LeadSubmitted` |
| `currency` | varchar(3), nulo | |
| `status` | varchar(12), no nulo, `pending` | `pending`, `sent`, `failed` o `discarded`; CHECK |
| `attempts` | int, no nulo, 0 | |
| `next_attempt_at` | timestamptz, no nulo, `now()` | |
| `lease_until` | timestamptz, nulo | Reserva del despachador, como en push |
| `sent_at` | timestamptz, nulo | |
| `last_error_code` | varchar(40), nulo | |

**Índices.**
- `(tenant_id, status, next_attempt_at)`, parcial `WHERE status = 'pending'`, para el despachador.
- `(tenant_id, channel_id, sent_at)`, para el contador de 7 días.

**No hay columna de teléfono**, ni en claro ni cifrado. El despachador lo lee de `customers.phone` al enviar y lo cifra en memoria.

### Estados de un evento

```text
            encolar
               │
               ▼
           pending ──── envío correcto ─────► sent
            │   ▲
 transitorio│   │ espera 1 min × 2^n (hasta 6 intentos)
            ▼   │
           pending
            │
            ├── error permanente, sin permiso, 6 intentos o más de 6 d 23 h ──► failed
            │
            └── medición apagada o baja de marketing ──► discarded
```

`sent`, `failed` y `discarded` son finales.

**Una cancelación (`OrderCanceled`)** sigue `pending` sin gastar intentos mientras su original (`cancels_event_id`) no sea final. Después:
- si el original quedó `sent`, entra en el ciclo de arriba;
- si quedó `failed` o `discarded`, pasa a `discarded`.

La tabla necesita `UNIQUE (tenant_id, id)` para la FK de `cancels_event_id`.

**Baja de marketing.** Bloquea, al encolar y al enviar, cualquier fila de `whatsapp_opt_outs` que cumpla todo esto:
- es del mismo `channel_id`;
- tiene `opted_in_at IS NULL`, sea cual sea su `scope`;
- coincide por `customer_id` o por `recipient_phone` igual al teléfono del contacto.

## Cambios en lo que existe

| Dónde | Cambio |
|---|---|
| `nexus_channels.base.InboundMessage` | Nada. Ya tiene `referral`. El filtrado lo hace la API al escribir el stream |
| `api/webhooks/meta.py` | La clave nueva del stream `referral_json`, con lista blanca y topes (research D1) |
| `nexus_worker.runtime.dispatcher.InboundEvent` | `referral: dict[str, str] \| None` |
| `core/tenant_context.py` | `conversation_context` y `get_current_conversation()` (research D7) |
| `core/guardrails/untrusted.py` | `TAG_AD_REFERRAL = "ad_referral"` |
| `api/console/lite/inbox.ConversationDetailOut` | `ad_origin: AdOriginOut \| None` |
| `api/console/channel_config.ChannelPageOut` | `ad_measurement: AdMeasurementOut \| None` |
| `config.py` (API) | `ad_measurement_tenants: list[UUID]`, `ad_measurement_general_availability: bool = False`, `meta_capi_test_event_code: str \| None`, `meta_config_id_wa_events_test_cloud_api: str \| None`, `meta_config_id_wa_events_test_coexistence: str \| None`. Los tres últimos, solo en staging |
| `config.py` (worker) | `retention_ad_click_days: int = 90`, `conversion_dispatch_tick_seconds: float = 60` |
| `api/console/whatsapp.py` | La cuota no cuenta el número que se reconecta. Si la prueba de D6 lo pide, `complete()` se salta el registro de un número vivo |

## A qué tenant pertenece cada cosa

Las tres tablas son del negocio y la RLS las alcanza por su `tenant_id`.

**Desde el lado del tenant:**
- El despachador resuelve el conjunto de datos y el token **leyendo como ese tenant**. Nunca toma un id de la fila del evento para ir a buscar credenciales.
- `test_22_tenant_delete_leaves_nothing` comprueba que borrar un tenant borra sus filas, por las FK con `CASCADE`.

**Desde el lado del cliente final:**
- El clic de un anuncio y el evento que lo usa son del mismo `customer_id`. La FK compuesta solo garantiza el tenant; que el cliente sea el mismo lo garantiza el código al encolar, y lo prueba `tests/isolation/test_076_ad_click_customer_axis.py`.
