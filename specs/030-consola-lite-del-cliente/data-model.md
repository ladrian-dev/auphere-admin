# Data model: la consola lite

Todas las tablas nuevas con `tenant_id` llevan RLS `ENABLE` + `FORCE` con la
política estándar de `0002_rls_policies.py`
(`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`) y
permisos para `nexus_app`. Las tablas de identidad del cliente siguen el patrón
de `partner_memberships` (sin RLS por tenant: se leen por cuenta en la
resolución de la sesión, como las del partner).

## Iteración 1 — acceso e identidad

### `client_access` (0147)

| Columna | Tipo | Notas |
|---|---|---|
| `tenant_id` | uuid PK, FK `tenants` ON DELETE CASCADE | uno por cliente |
| `partner_id` | uuid FK `partners` | el partner del cliente en el momento de activar (de `partner_tenants`) |
| `enabled` | bool not null default false | |
| `modules` | text[] not null default '{}' | subconjunto de `{panel, inbox, usage}`; CHECK `modules <@ ARRAY['panel','inbox','usage']` |
| `updated_by` | text | `operator:<correo>` |
| `created_at`, `updated_at` | timestamptz | |

Reglas (servicio, no CHECK): `enabled` exige ≥ 1 módulo; `inbox` exige un canal
de WhatsApp conectado **al activarlo**; el cliente debe estar en
`partner_tenants`. RLS por `tenant_id`; la resolución de la sesión la lee con el
tenant fijado.

### `client_memberships` (0147)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `partner_id` | uuid FK `partners` ON DELETE CASCADE | |
| `tenant_id` | uuid FK `tenants` ON DELETE CASCADE | |
| `user_id` | varchar(64) not null | id de la cuenta (`console_auth.principals`), por valor como en el partner |
| `email`, `display_name` | varchar(255) | |
| `status` | varchar(20) `active` \| `revoked` | CHECK |
| `invited_by` | text | `operator:<correo>` |
| `accepted_at`, `created_at`, `updated_at` | timestamptz | |

Índices: único `user_id` (una cuenta, un cliente); `(tenant_id)`.
Invariante entre tablas: una cuenta no está a la vez en `partner_memberships` y
en `client_memberships` (servicio + bloqueo consultivo por correo + test).

### `client_invitations` (0147)

Como `partner_invitations` sin `role`: `id`, `partner_id`, `tenant_id`,
`email` (minúsculas), `token_hash` char(64) único, `status`
(`pending|accepted|revoked|expired`), `invited_by`, `expires_at` (21 días),
`accepted_at`, `accepted_membership_id` FK, `created_at`. Índice único parcial
`(tenant_id, email) WHERE status = 'pending'`.

### `console_notifications.audience` y vocabulario del acceso (0148)

`varchar(10) not null default 'partner'`, CHECK `IN ('partner','client')`.
Índice `(partner_id, audience, external_client_ref, created_at desc)`.
Siembra en `console_audit_vocabulary`: `client_access.updated`,
`client_member.invited`, `client_member.resent`, `client_member.revoked`,
`client_member.joined`.

## Iteración 2 — Bandeja

### `conversations` (0149, columnas nuevas)

| Columna | Tipo | Notas |
|---|---|---|
| `assigned_user_id` | varchar(64) null | cuenta de la persona que responde |
| `closed_at` | timestamptz null | `CLOSED` = resuelta |
| `last_message_at` | timestamptz null | última actividad en cualquier sentido; relleno con `max(messages.created_at)` |

Índice `ix_conversations_tenant_last_message (tenant_id, last_message_at DESC, id)`.

Transiciones de estado (D11–D14):

```
             entrante                     escalate (con Bandeja: agent_active=false)
  (nueva) ───────────► OPEN ─────────────────────────────► ESCALATED
                        ▲  ▲                                   │
         devolver /     │  │ tomar el control / devolver       │
         reabrir        │  └───────────────────────────────────┘
                        │
   entrante / reabrir   │      resolver
            CLOSED ─────┘ ◄────────── OPEN | ESCALATED
```

### `conversation_events` (0149)

`id`, `tenant_id`, `conversation_id` FK, `kind` (`escalated | takeover |
released | resolved | reopened | agent_changed`), `actor` (`agent:<agent_id>` |
`client:<user_id>` | `operator:<id>` | `contact` | `system`), `payload` jsonb
(`reason`, `customer_summary` en `escalated`; nunca texto de mensajes),
`created_at`. Índice `(conversation_id, created_at desc)`.

### `inbox_reads` (0150)

`tenant_id`, `conversation_id`, `user_id`, `read_at` timestamptz,
`marked_unread` bool default false. PK `(conversation_id, user_id)`.
*Sin leer* = existe un mensaje entrante posterior a `read_at`, o `marked_unread`.

### `conversation_tags` (0150)

`tenant_id`, `conversation_id`, `tag` varchar(40) (recortado, sin vacíos),
`created_by`, `created_at`. PK `(conversation_id, lower(tag))`. Sugerencias =
etiquetas distintas del tenant.

### `contact_notes` (0150)

`tenant_id`, `customer_id` PK FK `customers`, `body` text (≤ 4.000),
`updated_by` (cuenta), `updated_at`. **No se lee desde `apps/worker` ni
`apps/mcp`** (barrido D18).

### `saved_replies` (0150)

`id`, `tenant_id`, `title` varchar(80), `body` text (≤ 1.000), `created_by`,
`created_at`, `updated_at`, `archived_at` timestamptz null (borrar = archivar,
constitución §IV).

### `messages` (0149)

`actor_kind` admite `member` (persona del cliente). Sin columna nueva en esta
iteración.

### `console_audit_vocabulary` (0151)

Siembra `inbox.takeover`, `inbox.released`, `inbox.message_sent`,
`inbox.attachment_sent`, `inbox.resolved`, `inbox.reopened`, `inbox.tagged`,
`inbox.untagged`, `inbox.note_saved`, `inbox.reply_saved` con su frase.

## Iteración 3 — varios agentes

### `agents` (0152)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | RLS |
| `name` | varchar(80) not null | único por tenant entre activos |
| `status` | varchar(20) `active` \| `archived` | |
| `created_at`, `updated_at` | timestamptz | |

*Agente principal* = el activo más antiguo del tenant (D23); no es columna.

### Columnas nuevas (0152)

| Tabla | Columna | Notas |
|---|---|---|
| `agent_configs` | `agent_id` uuid not null FK `agents` | relleno: el agente creado para su tenant. Se **mantiene** `(tenant_id, version)` (ver la decisión de abajo); un índice único parcial `(agent_id) WHERE status = 'active'` fija una versión activa por agente |
| `channels` | `agent_id` uuid null FK `agents` | relleno: los canales con `config.role` de agente → el agente del tenant |
| `messages` | `agent_id` uuid null | mensajes salientes del agente (tabla particionada: columna anulable, sin FK) |
| `usage_records` | `agent_id` uuid null | |
| `usage_ledger` | `agent_id` uuid null | |
| QA/playground threads | `agent_id` uuid null | el hilo de prueba fija su agente |

### Hallazgo de implementación (2026-10-08): un agente solo se referencia desde su cliente

`agent_configs.agent_id` y `channels.agent_id` nacieron (0152) con una clave
foránea de una columna a `agents.id`. La comprobación de una clave foránea no
pasa por la RLS, y el admin recibe `agent_id` por la URL: una versión o un
número del cliente A podía apuntar al agente del cliente B. `0155` lo cierra en
la base de datos: unicidad `(tenant_id, id)` en `agents` y claves
`(tenant_id, agent_id)` desde las dos tablas (`agent_configs` con `CASCADE`,
`channels` con `SET NULL (agent_id)`). El repositorio, además, rechaza un
agente que no es activo del cliente antes de llegar ahí (`UnknownAgent`).
Prueba: `tests/isolation/test_agent_scope_within_tenant.py`.

### Decisión de implementación (2026-10-08): las versiones siguen numeradas por tenant

El plan decía «unicidad `(agent_id, version)` en lugar de `(tenant_id,
version)`». Al inventariar el código antes de tocarlo apareció cuánto depende
de que `(tenant_id, version)` identifique **una** fila: la puerta de
evaluaciones antes de publicar (`has_passing_recent_run(tenant_id,
agent_config_version)`), `eval_runs.agent_config_version`, la biblioteca de
prompts, `PATCH …/agent-config/{version}/runtime` del admin y las rutas de
publicar y revertir por número. Numerar por agente los volvía ambiguos con dos
agentes y obligaba a cambiarlos todos a la vez.

Se queda **`uq_agent_configs_tenant_version`** y se añade lo que de verdad
importa: **una versión activa por agente** (índice único parcial
`(agent_id) WHERE status = 'active'`). Los números siguen subiendo por cliente:
el primer borrador de un agente nuevo puede ser la v7. Es lo único que se ve
distinto del contrato («borrador v1»), y la consola enseña la versión dentro
del agente elegido, así que no confunde dos agentes entre sí.

### Relleno (0153, datos)

1. Por cada tenant con alguna fila en `agent_configs`: un `agents` «Agente
   principal» (`active`) y `agent_configs.agent_id` = ese agente.
2. `channels.agent_id` = ese agente para los canales de rol agente.
3. Comprobación al final de la migración: ninguna `agent_configs` sin agente y
   ningún agente con más de una versión activa; si falla, la migración aborta.
