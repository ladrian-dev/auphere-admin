# Modelo de datos — spec 025

Migración `0137_payment_reviews` (revision id ≤ 32 caracteres).

## `payment_reviews` (RLS por tenant)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid PK | `gen_random_uuid()` |
| `tenant_id` | uuid FK tenants, not null | RLS `tenant_id = app.tenant_id` |
| `conversation_id` | uuid FK conversations, not null | conversación del **cliente** |
| `channel_id` | uuid FK channels, not null | canal por el que salen los avisos |
| `token` | varchar(16), not null, **unique** | va en el id del botón |
| `method` | varchar(16), not null | `transfer` · `link` |
| `status` | varchar(16), not null, default `pending` | `pending` · `confirmed` · `rejected` · `informed` |
| `summary` | jsonb, not null | `{product, modality, place, date, slot, total, customer_name}` (strings, todos opcionales) |
| `order_id` | varchar(40), null | pedido de la tienda (link) |
| `order_status` | varchar(40), null | estado leído en la tienda (link) |
| `receipt_message_ids` | uuid[], not null, default `{}` | entrantes del cliente con comprobante |
| `resolved_by_phone` | varchar(32), null | E.164 del revisor |
| `resolved_by_name` | varchar(120), null | |
| `resolved_at` | timestamptz, null | |
| `customer_notified` | boolean, null | `true` respuesta encolada · `false` ventana cerrada · null sin resolver |
| `created_at` / `updated_at` | timestamptz | `now()` |

Índices: `(tenant_id, conversation_id, status)`.
CHECK: `status IN (…)`, `method IN (…)`, y `status='pending'` ⇔
`resolved_at IS NULL` salvo `informed`.

## `payment_review_notices` (RLS por tenant)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK tenants, not null | RLS |
| `review_id` | uuid FK payment_reviews ON DELETE CASCADE, not null | |
| `reviewer_phone` | varchar(32), not null | E.164 |
| `reviewer_name` | varchar(120), null | |
| `reviewer_conversation_id` | uuid FK conversations, null | la conversación del revisor en el canal |
| `delivery` | varchar(20), not null | `interactive` · `undelivered` |
| `reason` | varchar(40), null | `window_closed` |
| `message_id` | uuid FK messages, null | el mensaje con botones |
| `created_at` | timestamptz | |

Único: `(review_id, reviewer_phone)`.

## Política del agente

`policies.payment_review = {"reviewers": [{"phone": "+56…", "name": "…"}]}`
(máx. 10). Ausente o vacía = sin revisión de pagos (comportamiento de hoy).

## Catálogo de herramientas

Fila `payments.request_review` en `tool_catalog` (`mcp_server=payments`,
`side_effects=[mutates_db, sends_message]`, `read_only=false`,
`destructive=false`, `requires_consent=false`). Nombre de negocio en
`capability_names.py`: «Pedir revisión de un pago», función `orders`.

## Vocabulario de auditoría

`payment_review.opened` y `payment_review.resolved` (categoría `agent`,
severidad `info`).
