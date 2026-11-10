# Modelo de datos — 045

Dos columnas en una tabla que ya existe y una en otra. Ninguna tabla nueva.

## `conversations` (ya existe; RLS FORCE por `tenant_id`)

| Columna nueva | Tipo | Qué es |
|---|---|---|
| `attended_at` | `timestamptz NULL` | Primer entrante que el agente pudo atender (no silenciado por la puerta de números permitidos, en un número con agente). `NULL` = la conversación no existe para la Bandeja |
| `last_attended_inbound_at` | `timestamptz NULL` | Último entrante atendido. Es contra lo que se mide el «sin leer» |

- Las escribe el despachador del worker en la misma transacción que persiste el
  entrante (`runtime/dispatcher.py`), después de decidir la puerta.
- Índice parcial `ix_conversations_attended` sobre
  `(tenant_id, last_message_at DESC) WHERE attended_at IS NOT NULL` para la
  lista.
- **Relleno** (migración `0171`): para cada conversación, `MIN` y `MAX` de
  `messages.created_at` de los entrantes con `skipped_reason IS NULL`. Corre como
  el rol de migraciones (sin RLS). Idempotente (solo escribe donde difiere).
  `downgrade` borra las columnas.

`last_inbound_at` **no cambia**: sigue siendo la ventana de 24 h de WhatsApp,
que Meta abre con cualquier mensaje, silenciado o no.

## `client_phones` (ya existe; RLS FORCE por `tenant_id`)

| Columna nueva | Tipo | Qué es |
|---|---|---|
| `quiet_outside_hours` | `boolean NOT NULL DEFAULT true` | Silenciar fuera del horario del negocio los avisos no urgentes |

## `client_push_deliveries` (ya existe)

`skip_reason` gana el valor `quiet_hours` (columna de texto: sin CHECK que
cambiar; se comprueba en la prueba de la fan-out).

## Lo que se lee, no se guarda

- `waiting.reason` / `waiting.since`: del último `conversation_events` de tipo
  `escalated` (su `payload.reason` y su `created_at`).
- `month_days_left` / `runs_out_on`: del saldo que ya se calcula y de
  `tenants.timezone`.
- `business.hours`: `tenants.business_hours` por `services/business_hours.py`.
