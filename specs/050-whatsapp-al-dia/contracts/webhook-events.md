# Contrato: eventos del webhook de WhatsApp (`object=whatsapp_business_account`)

`POST /webhook/meta`. La firma `X-Hub-Signature-256` es la única causa de un no-2xx. Cada `entry[].changes[]` se procesa entero: **todos** sus elementos, cada uno en su propio bloque (D1). Formas: `D/webhooks/reference/<campo>.md` (ver [research.md](../research.md)).

## Atribución

| Clave del evento | Cómo se resuelve el negocio |
|---|---|
| `value.metadata.display_phone_number` / `phone_number_id` | `resolve_channel_tenant('meta', +E164)`, como hoy |
| `waba_info.waba_id` o `entry[].id` (eventos de cuenta y de plantilla sin número) | `resolve_waba_tenants(waba_id)`: el evento se aplica bajo la RLS de cada negocio, a sus números de esa WABA |
| Número de Auphere (canal del dueño) | Camino actual (`owner_channel`), sin cambios |
| Ninguno | Se ignora y se cuenta `channel.unresolved_event` |

## Matriz de tratamiento

| Campo | Elemento | Tratamiento | Requisito |
|---|---|---|---|
| `messages` → `messages[]` | Entrante (todos los tipos) | Identidad (D2), dedupe por `id`, encolar al agente | 1.1, 2.1 |
| | `type=system` (`user_changed_number`, `user_changed_user_id`) | Actualiza `phone` / `bsuid` del cliente; no dispara al agente | 1.5, 2.2 |
| | `type=button` | `INTERACTIVE` `template_button` con `payload`, `text` y la plantilla de `context.id` | 7.1 |
| | `type=contacts` | Texto legible para el agente | 7.3 |
| | `referral` presente | Se guarda en `conversations.ad_referral` (la primera vez) y va al agente como contexto | 7.2 |
| | `errors[]` / `type=unsupported` | Se registra el código; el agente recibe `[unsupported:<tipo>]` | 1.5 |
| | Mensaje con `deleted` / revocado | Se marca en la conversación; sin turno | 1.6 |
| `messages` → `statuses[]` | `sent`, `delivered`, `read`, `played`, `failed`, `warning`, `deleted` | Estado del mensaje con guarda de orden; `pricing{billable, type, category}` | 1.1, 1.6, 8.1 |
| `messages` → `value.errors[]` | Error de lote (p. ej. 130429) | Log y métrica; sin efecto en datos | 1.2 |
| `message_template_status_update` | 14 eventos | Estado, motivo y categoría bajo el tenant de la WABA; aviso si impide enviar; invalida la caché | 4.1 |
| `message_template_quality_update` | Calidad | `quality`; aviso si baja a `YELLOW`/`RED` | 4.1 |
| `template_category_update` | Aviso / hecho | `pending_category` o `category` y `previous_category`; aviso | 4.1 |
| `account_update` | Unos 20 eventos (ver research D5) | Estado del canal, `problem_reason` y `config`; los de socio por `waba_info` | 4.2, 4.3 |
| `account_alerts` | Alerta | `config.alerts`; `CRITICAL` + `ACTIVE` → `problem_reason=account_alert` | 4.2 |
| `account_review_update` | `decision` | `config.account_review`; `REJECTED`/`DEFERRED` → `problem_reason=account_review` | 4.2 |
| `business_capability_update` | Límites | `config.messaging_limit`, `max_phone_numbers_per_waba` | 8.4 |
| `phone_number_name_update` | `decision` | `config.name_*`; aviso si `REJECTED` | 4.4 |
| `phone_number_quality_update` | `event` | `config.messaging_limit` | 8.4 |
| `user_preferences` | `stop` / `resume` | Baja o reactivación de marketing por cliente (D6) | 5.1, 5.2 |
| `business_username_updates` | `status` | `config.username`, `username_status` | 2.5 |
| `history`, `smb_app_state_sync`, `smb_message_echoes` | Coexistencia | Camino actual, ahora con todos los elementos y con identidad BSUID | 1.1 |
| Cualquier otro | — | `webhook.meta.unhandled_field` sin datos personales, 200 | 1.4 |

## Lo que el agente nunca recibe como instrucción

El texto de `referral` (`headline`, `body`), los nombres de perfil y los mensajes de sistema se pasan como **datos** dentro del contexto del turno, nunca en el `system` del operador (constitución §III).
