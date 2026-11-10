# Modelo de datos: 050 — WhatsApp al día

Todas las tablas tocadas ya tienen `tenant_id`, RLS FORCE y su política, salvo lo que se dice. Hay una migración por iteración, encadenada sobre la cabeza que haya en `develop` al empezar (hoy `0205_meta_social_channels`).

## Iteración 1

### `customers` (D2)

| Columna | Tipo | Notas |
|---|---|---|
| `identifier` | existente | **Sin cambios de significado.** Teléfono (dígitos) si lo había al crearla; si no, el BSUID. No se reescribe nunca |
| `bsuid` | `varchar(160)` nulo | Identificador de Meta (`CC.…`). Índice único parcial `(tenant_id, bsuid) WHERE bsuid IS NOT NULL` |
| `phone` | `varchar(32)` nulo | Dígitos E.164 sin `+`. Índice `(tenant_id, phone)`. Relleno inicial: `phone = identifier` cuando `identifier ~ '^[0-9]{6,20}$'` |
| `username` | `varchar(64)` nulo | `profile.username` de Meta, informativo |

**Reglas de resolución** (worker, `upsert_customer_identity`):
1. Con `bsuid`, se busca por `bsuid`.
2. Si no aparece, y hay `phone`, se busca por `phone` o por `identifier = phone`. Si aparece, se le pone el `bsuid` (Meta los dio juntos).
3. Si no aparece ninguno, se crea con `identifier = phone ?? bsuid`.
4. Si `bsuid` y `phone` encuentran **dos filas distintas**, se usa la del `bsuid`, no se toca la otra y se escribe el log `customer.identity_conflict`, sin datos personales.

**Transiciones:**
- `system.user_changed_number`: `phone` pasa a ser el `wa_id` nuevo.
- `system.user_changed_user_id`: `bsuid` pasa de `previous_user_id` al `user_id` nuevo.

### `whatsapp_opt_outs` (D6)

| Columna | Tipo | Notas |
|---|---|---|
| `customer_id` | `uuid` nulo, FK `customers` `ON DELETE CASCADE` | Se rellena al crear y en el relleno inicial (por `recipient_phone` = `customers.phone`) |
| `scope` | `varchar(12)` `NOT NULL DEFAULT 'all'` | `marketing` o `all`. CHECK. Filas existentes: `all` |
| `source` | `varchar(12)` `NOT NULL DEFAULT 'keyword'` | `meta`, `keyword` u `operator` |
| `lifted_by` | `varchar(255)` nulo | Persona que la levantó (actor) |
| `recipient_phone` | existente, **pasa a nulo** | Una baja por BSUID no tiene teléfono |

Unicidad nueva: `(tenant_id, channel_id, customer_id) WHERE opted_in_at IS NULL`. La antigua por `recipient_phone` se conserva para las filas sin `customer_id`.

### `whatsapp_template_status` (D5)

| Columna | Tipo | Notas |
|---|---|---|
| `tenant_id` | existente | **Se rellena** (hoy queda nulo), con la atribución por WABA. La tabla sigue **sin RLS**: también guarda las plantillas de la WABA de Auphere (canal del dueño), que no son de ningún negocio. Se lee siempre filtrando por `waba_id` del canal del negocio |
| `category` | existente | Se escribe con `message_template_category` / `new_category` |
| `previous_category` | `varchar(32)` nulo | De `template_category_update` |
| `quality` | `varchar(12)` nulo | `GREEN`, `YELLOW`, `RED` o `UNKNOWN` |
| `pending_category` | `varchar(32)` nulo | Aviso de recategorización (`correct_category`) antes de que se aplique |
| `status` | existente | Valores de Meta en mayúsculas. Se compara sin distinguir mayúsculas |

### `channels` (D5, D9, D10)

- `problem_reason`: el CHECK `ck_channels_problem_reason` admite además `account_review` y `account_alert`. Cambia también `PROBLEM_REASONS` en `services/agent_lifecycle.py`.
- Claves nuevas en `config` (JSONB, sin migración):
  - `username` y `username_status` (`business_username_updates`);
  - `name_decision`, `requested_name` y `name_rejection_reason` (`phone_number_name_update`);
  - `messaging_limit` (`TIER_*`) y `max_phone_numbers_per_waba`;
  - `pricing_tier` (`VOLUME_BASED_PRICING_TIER_UPDATE`);
  - `account_review` (`APPROVED` / `REJECTED` / `PENDING` / `DEFERRED`);
  - `alerts[]` (`{type, severity, status, at}`, las últimas 20);
  - `problem_source`: `quality` o `account`. El cron solo limpia los suyos.

### `MetaCredentials` (cifrado, `channels.config_encrypted` y `tenant_credentials`)

- `two_step_pin`: `str | None`. Se escribe en el alta y al rotarlo. Nunca sale en una respuesta.

### Función `resolve_waba_tenants(p_waba_id text) RETURNS SETOF uuid`

`SECURITY DEFINER`, `SET row_security = off`. Devuelve los `tenant_id` distintos con canales `provider='meta'`, `config->>'waba_id' = p_waba_id` y estado distinto de `disconnected`. Solo da ids de tenant, nunca filas. `GRANT EXECUTE` al rol de la app, como `resolve_channel_tenant`.

### Vocabulario de auditoría

Entradas nuevas:
- `customer.opt_out.recorded`
- `customer.opt_out.lifted`
- `channel.whatsapp.pin_rotated`
- `channel.whatsapp.template_state`
- `channel.whatsapp.account_state`
- `channel.whatsapp.name_decision`

### Notificaciones (`NotificationKind`)

Tipos nuevos (y su texto en `i18n` `notif.kind.*` de la consola):
- `template.paused`
- `template.disabled`
- `template.quality_dropped`
- `template.recategorized`
- `channel.account_review`
- `channel.account_alert`
- `channel.name_rejected`

`template.rejected` ya existe, pero nada lo emitía hasta ahora.

## Iteración 2

### `messages` (D9)

| Columna | Tipo | Notas |
|---|---|---|
| `pricing_billable` | `boolean` nulo | `pricing.billable` |
| `pricing_type` | `varchar(32)` nulo | `regular`, `free_customer_service`, `free_entry_point` o `free_group_customer_service` |
| `pricing_category` | existente | Ahora incluye `authentication-international`, `marketing_lite`, `referral_conversion` y las de grupo |

### `conversations` (D8)

| Columna | Tipo | Notas |
|---|---|---|
| `ad_referral` | `jsonb` nulo | Primer `referral` de la conversación: `{source_type, source_id, source_url, headline, body, media_type, ctwa_clid, at}`. Dato, nunca instrucción |

### Plantillas (D7)

Sin tablas nuevas. El esquema de autoría (`TemplateCreateIn`) gana `header.format ∈ {TEXT, IMAGE, VIDEO, DOCUMENT}` con `media_upload_id` (subida previa), botón `COPY_CODE` / `OTP`, `add_security_recommendation`, `code_expiration_minutes` y `carousel.cards[]`.

## Iteración 3 — Catálogo (D11)

Sin tablas nuevas: **la fuente de verdad de los productos es Meta**.

- `channels.config`:
  - `catalog_id` (existente);
  - `catalog_source`: `auphere` (creado aquí), `feed` (tiene `product_feeds`), `linked` (enlazado sin feed y no creado aquí) o `coexistence`;
  - `catalog_visible` (bool, de `whatsapp_commerce_settings`).
- Auditoría:
  - `channel.catalog.created`
  - `channel.catalog.product_created`
  - `channel.catalog.product_updated`
  - `channel.catalog.product_deleted`

  Cada una con `{product_name, retailer_id}`, nunca la imagen.
- Productos (en Meta):
  - `retailer_id = "aup_" + ulid`, generado por el servidor;
  - `price` en céntimos y `currency` de la moneda del negocio;
  - `availability ∈ {in stock, out of stock}`;
  - «ocultar» = `visibility: staging`.

## Iteración 4 — Perfil (D10)

Sin tablas nuevas: el perfil vive en Meta. Auditoría `channel.whatsapp.profile_updated`, con los nombres de los campos cambiados, no sus valores.
