# Modelo de datos: spec 031, Auphere Customers

Migraciones **0158 a 0162**. La última en `main` es `0157_tenant_payments`.

**Reglas del repo que se aplican a todas las tablas nuevas:**
- Las tablas de tenant llevan RLS con `ENABLE` y `FORCE`, con la política
  `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`
  (patrón de `0150_inbox_tables.py`). Así lo exige `test_21`.
- Las referencias entre tablas de tenant usan **FK compuesta** `(tenant_id, id)`,
  porque una FK no pasa por la RLS (patrón de `0155_agents_tenant_fk.py`).
  Antes de referenciar una tabla hay que añadirle su `UNIQUE (tenant_id, id)`.
- Borrar un tenant no deja filas: todo cuelga con `ON DELETE CASCADE` y lo
  comprueba `test_22`.

---

## 0158 · `client_phones`: el teléfono de una persona

Es la entidad **Teléfono de una persona** y **Destino de avisos** de la spec:
el destino vive en la misma fila, porque hay uno por teléfono.

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid PK | Va en la credencial como `sub` |
| `tenant_id` | uuid NOT NULL | El cliente de la persona. Se fija al entrar, desde la membresía; nunca lo manda la app |
| `partner_id` | uuid NOT NULL | Viene de la membresía. Es lo que necesita `resolve_client_principal` |
| `client_membership_id` | uuid NOT NULL | FK compuesta `(tenant_id, client_membership_id)` → `client_memberships (tenant_id, id)`, `ON DELETE CASCADE` |
| `principal_id` | uuid NOT NULL | La cuenta (`console_auth.principals`) |
| `platform` | text NOT NULL | CHECK `ios` \| `android` |
| `display_name` | text NOT NULL | Lo que manda el sistema («iPhone de Valeria»), recortado a 80 |
| `install_id` | text NOT NULL | Lo genera la app al instalarse. `UNIQUE (install_id) WHERE revoked_at IS NULL`. Al entrar, se revoca con `signed_out` la fila activa con ese `install_id`, sea de quien sea, en la transacción de identidad. Así una recepción compartida no deja sesiones fantasma |
| `app_version` | text NOT NULL | Se actualiza en cada renovación |
| `refresh_hash` | bytea NOT NULL | SHA-256 de la renovación vigente. Nunca se guarda en claro |
| `refresh_prev_hash` | bytea NULL | La anterior, válida 60 s tras rotar (R2) |
| `refresh_rotated_at` | timestamptz NOT NULL | |
| `credential_generation` | int NOT NULL DEFAULT 1 | Sube con cada rotación. Va en la credencial de acceso (`gen`) |
| `push_provider` | text NULL | CHECK `apns` \| `fcm` |
| `push_token` | text NULL | El destino que dan Apple o Google |
| `push_token_updated_at` | timestamptz NULL | Cuándo se registró. Si dos filas activas comparten destino, **solo vale la más reciente** (ver abajo) |
| `apns_environment` | text NULL | CHECK `sandbox` \| `production` |
| `notice_kinds` | text[] NOT NULL | Tipos activados en este teléfono (R11.2). Por defecto los tres de R8.1. CHECK ⊆ `{inbox.waiting, inbox.message_for_you, client.balance}` |
| `locale` | text NOT NULL | `es` \| `en`, el idioma del teléfono (R14.6) |
| `last_seen_at` | timestamptz NOT NULL | Se toca como mucho una vez cada 5 minutos |
| `enrolled_at` | timestamptz NOT NULL | |
| `revoked_at` | timestamptz NULL | |
| `revoked_reason` | text NULL | CHECK `signed_out` \| `closed_by_person` \| `closed_by_auphere` \| `access_disabled` \| `member_removed` \| `password_reset` \| `abandoned` \| `refresh_reused` |
| `revoked_by` | text NULL | `client:<correo>`, `operator:<correo>` o `system` (R7.6) |

**Restricciones e índices**

- `UNIQUE (tenant_id, id)`, para las FK de `client_push_deliveries`.
- Índice `(tenant_id, principal_id) WHERE revoked_at IS NULL`, para la lista de
  teléfonos y los destinatarios de un aviso.
- Índice `(push_token) WHERE revoked_at IS NULL AND push_token IS NOT NULL`.
- **Un destino, un dueño.** Apple y Google pueden reutilizar un destino.
  - **Al registrarlo**, en la transacción de identidad, se pone a `NULL` el
    mismo destino en cualquier otra fila, de cualquier cliente.
  - **El worker lo comprueba otra vez al repartir:** solo envía si ninguna otra
    fila activa tiene ese destino con un `push_token_updated_at` más reciente.
  - Lo vigila T034.

**Política:** la RLS de tenant.

**Quién lo lee sin contexto de tenant:** la comprobación de la credencial, el
canje y el registro del destino. Lo hacen como identidad, igual que
`resolve_client_principal` con las membresías (research D3). Todo lo demás lo
lee bajo la RLS del cliente.

**Estados**

```
activo ──(cerrar sesión · lo cierra la persona · lo cierra Auphere ·
          se apaga el acceso · se quita a la persona · se restablece la
          contraseña · 90 días sin uso · renovación reutilizada)──► revocado
```

- **Revocado es final.** Volver a entrar crea otra fila. La anterior se queda
  como constancia: nada se borra, se archiva (constitución §IV).
- **Al revocar** se pone a `NULL` el `push_token`, así ningún aviso posterior
  sale (R7.2).

---

## 0159 · `console_auth.session_codes`: añadir `purpose`

Esta tabla ya existe y la usan las specs 009 y 012.

| Cambio | Regla |
|---|---|
| Columna `purpose text NOT NULL DEFAULT 'desktop_session'` | CHECK `desktop_session` \| `client_phone` |
| Columna `challenge_encoding text NOT NULL DEFAULT 'hex'` | CHECK `hex` \| `base64url`. Los códigos del teléfono se emiten en `base64url`, que es lo que pide el RFC 7636 (research §D2) |

Un código de un propósito no se canjea en el otro: el canje filtra por
`purpose`. La vida y el uso único no cambian (10 minutos, un solo uso).

---

## 0160 · `client_push_events`: el outbox de avisos

Un hecho que puede producir avisos. Se escribe **en la misma transacción que el
hecho**, y el worker solo ve lo confirmado (R8.5). Es el mismo patrón que
`messages.status = 'pending'` en `outbound.py`.

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid NOT NULL | |
| `kind` | text NOT NULL | CHECK `inbox.waiting` \| `inbox.message_for_you` \| `client.balance` |
| `conversation_id` | uuid NULL | Para los tipos de la Bandeja |
| `notification_id` | uuid NULL | Para `client.balance`, el `console_notifications.id` de la campana |
| `target_principal_id` | uuid NULL | Solo para `inbox.message_for_you`: la persona que tiene el control |
| `dedupe_key` | text NOT NULL | `inbox.waiting:{conversation_event_id}` · `inbox.message:{message_id}` · `client.balance:{notification_id}`. `UNIQUE (tenant_id, dedupe_key)`: un hecho, un evento (R8.2 a R8.4) |
| `status` | text NOT NULL DEFAULT `pending` | CHECK `pending` \| `fanned_out` \| `failed` |
| `attempts` | int NOT NULL DEFAULT 0 | Como mucho 5 |
| `last_error` | text NULL | |
| `created_at` / `fanned_out_at` | timestamptz | |

- **Sin contenido.** Ni nombre, ni texto, ni motivo: solo referencias.
- **Política:** la RLS de tenant.
- **Disparador:** `pg_notify('nexus_push')` al insertar, como 0062 hace con
  `nexus_outbound`.

---

## 0161 · `client_push_deliveries`: un aviso a un teléfono

La entidad **Aviso entregado** de la spec. La crea el worker al repartir un
evento. Los destinatarios se calculan **en ese momento**, así cuentan las
revocaciones y los interruptores de ese instante (R7.2 y R11.2).

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid NOT NULL | |
| `event_id` | uuid NOT NULL | FK compuesta → `client_push_events (tenant_id, id)`, CASCADE |
| `phone_id` | uuid NOT NULL | FK compuesta → `client_phones (tenant_id, id)`, CASCADE |
| `status` | text NOT NULL | CHECK `queued` \| `sent` \| `failed` \| `skipped` |
| `skip_reason` | text NULL | `phone_revoked` \| `kind_disabled` \| `no_push_token` \| `module_missing` |
| `provider_message_id` | text NULL | El `apns-id` o el `name` de FCM |
| `error_code` | text NULL | Por ejemplo `Unregistered` o `BadDeviceToken`: limpia `push_token` |
| `created_at` / `sent_at` | timestamptz | |

- `UNIQUE (tenant_id, event_id, phone_id)`: un evento, un aviso por teléfono.
- **Política:** la RLS de tenant.

---

## 0162 · Vocabulario de auditoría

Son filas de `console_audit_vocabulary`, con el patrón de
`0151_inbox_audit_vocab.py`. **No se usa el prefijo `device.*`**, que ya es de
las máquinas de la spec 002.

| `action` | Categoría | ES |
|---|---|---|
| `client_phone.signed_in` | auth | «{actor} entró desde {phone}» |
| `client_phone.signed_out` | auth | «{actor} cerró la sesión en {phone}» |
| `client_phone.closed` | auth | «{actor} cerró {phone} de {person}» |
| `client_phone.revoked` | auth | «Se cerró {phone} de {person}: {reason}» |
| `client_account.deletion_requested` | auth | «{actor} pidió borrar su cuenta» |

`audit_words.PLACEHOLDERS` gana `{phone}` y `{reason}`. Lo vigila
`test_console_audit_words.py`.

---

## Lo que cambia sin tabla nueva

- **`messages.idempotency_key`** (0053) pasa a usarlo también el envío de la
  Bandeja lite y los adjuntos. El índice parcial por tenant ya existe.
- **`console_identity.principal_sessions`** no cambia. La sesión web sigue
  durando 7 días absolutos. El teléfono no es una fila de esta tabla
  (research §D1).
- **`console_notifications`** no cambia. Los avisos de saldo producen un
  `client_push_events` en la misma transacción que su `emit()`, fijando antes el
  tenant con `SET LOCAL`.
- **La versión mínima** vive en la configuración, como la del escritorio
  (`config.py:88-90`): `customers_app_min_version_ios`,
  `customers_app_min_version_android`, `customers_app_min_version_reason` y
  `customers_app_min_version_from`. No hace falta una tabla.
