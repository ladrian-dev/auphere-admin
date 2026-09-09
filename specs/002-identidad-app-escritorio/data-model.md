# Fase 1 — Modelo de datos (migración `0107_device_owner_and_pairing`)

**Rama**: `002-identidad-app-escritorio` · **Fecha**: 2026-09-09

Una tabla cambia de dueño, dos tablas nacen, y ninguna acepta el tenant ni el
partner del llamante: salen del contexto de petición (`app.partner_id`,
`app.principal_id`, `app.tenant_id`) y la RLS decide. Expresiones de GUC idénticas
a `0094` y `0090`.

---

## 1. `partner_devices` — la máquina, ahora del partner

| Campo | Tipo | Cambio | Reglas |
|---|---|---|---|
| `id` | uuid | — | |
| `partner_id` | uuid | **NUEVO**, NOT NULL, FK `partners` CASCADE | **RLS**. Del contexto |
| `principal_id` | text | se mantiene | La dueña. **Ahora se lee**: política RLS por persona |
| `display_name` | text | se mantiene | Editable desde la consola (R3.6) |
| `hostname` | text | **NUEVO** | Lo que la máquina dijo al emparejar; propuesto como nombre |
| `platform` | text | se mantiene | CHECK `macos \| windows` |
| `app_version` | text | se mantiene | |
| `credential_generation` | int | **NUEVO**, NOT NULL, default 1 | Sube en cada renovación. La credencial lleva `gen` |
| `credential_rotated_at` | timestamptz | **NUEVO**, NULL | Base de la gracia de 60 s |
| `last_heartbeat_at` | timestamptz | se mantiene | Base de la presencia y del umbral de 30 días |
| `enrolled_at` | timestamptz | se mantiene | Ahora significa «emparejada» |
| `revoked_at` | timestamptz | se mantiene | Archivar; terminal |
| `revoked_reason` | text | **NUEVO**, NULL | CHECK `desemparejada \| archivada_consola \| pertenencia_retirada` |
| ~~`tenant_id`~~ | — | **SE VA** | Pasa a `device_client_links` |
| ~~`workdir`~~ | — | **SE VA** | Pasa a `device_client_links` |

**Índices**: `(partner_id, enrolled_at)`, `(principal_id)`.

**RLS**: FORCE. Dos políticas (OR):

- `partner_devices_owner`: `partner_id = P AND principal_id = PR`
- `partner_devices_manager`: `partner_id = P AND
  current_setting('app.workstation_manager', true) = 'true'`

**Estados (derivados, no columna)**: `nunca vista → presente → ausente →
presente → archivada`. `archivada` es terminal (R11.5). «Sin sesión» **no** es un
estado de la fila: es que dejó de latir, y la presencia decae sola (D14).

**Backfill**: `partner_id` desde `partner_tenants` por el `tenant_id` antiguo;
por cada fila, un `device_client_links (device_id, tenant_id, workdir)`.

## 2. `device_client_links` — a qué clientes sirve una máquina, y dónde

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid | |
| `tenant_id` | uuid | **RLS por tenant** (FORCE; `test_21` lo exige). FK `tenants` CASCADE |
| `device_id` | uuid | FK `partner_devices` CASCADE |
| `workdir` | text | **NULL hasta que la máquina lo declare** (R7). Nunca se teclea en la consola |
| `declared_at` | timestamptz | NULL hasta declarar |
| `declared_by_device` | boolean | NOT NULL default true — la única vía es la máquina |
| `created_by` | text | La persona que vinculó desde la consola |
| `created_at` | timestamptz | |
| `removed_at` | timestamptz | Se archiva, no se borra |

**Unicidad**: `(device_id, tenant_id)` con `removed_at IS NULL`.

**Invariante de partner (no la RLS, un CHECK de aplicación + test)**: el tenant del
vínculo pertenece al partner de la máquina. Se garantiza porque el vínculo solo se
crea desde `/console/workstation` (partner de la sesión) o desde `/device/links`
(partner de la firma), y en los dos casos el tenant se resuelve por
`partner_tenants` bajo `app.partner_id`. `test_30` lo prueba desde los dos lados.

**Presencia por tenant** (D14): el tenant X tiene herramientas locales si existe un
vínculo suyo con `workdir IS NOT NULL`, `removed_at IS NULL`, cuya máquina no está
archivada y late dentro de la ventana.

## 3. `device_pairing_codes` — el código, de un solo uso

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid | |
| `partner_id` | uuid | **RLS por partner** (FORCE). FK `partners` CASCADE |
| `principal_id` | text | La persona que pidió el código; será la dueña de la máquina |
| `code_hash` | text | `sha256` del código normalizado (mayúsculas, sin guion). **Nunca el código** |
| `expires_at` | timestamptz | `now() + 10 min` |
| `consumed_at` | timestamptz | NULL hasta el canje; el canje es un `UPDATE … WHERE consumed_at IS NULL … RETURNING` |
| `consumed_device_id` | uuid | FK `partner_devices`, NULL hasta canjear |
| `created_at` | timestamptz | |

**Índice único**: `code_hash`. **Barrido**: los caducados se borran (aquí sí:
un código caducado no es dato de nadie) por el mismo barrido oportunista que
`console_sessions`.

**El canje corre sin partner en contexto** —no hay credencial aún— con el rol
dueño, por `code_hash`, y **fija el partner y la persona desde la fila**, nunca
desde el cuerpo. Es el único camino de `/device/*` sin credencial (Complexity
Tracking del plan).

## 4. Lo que no cambia

- `local_executables`, `local_argument_grants`, `local_executions`: por tenant,
  como en `0106`. `local_executions.device_id` sigue apuntando a la máquina; la
  máquina ahora es del partner y el registro sigue etiquetado por el tenant del
  trabajo (garantía 6).
- `audit_log`: se reutiliza. Vocabulario nuevo: `device.paired` ·
  `device.renewed` · `device.unpaired` · `device.archived` · `device.link_declared`
  · `device.pair_denied`, con `actor` la persona o `device:{id}`.

## 5. En la máquina (no es base de datos, pero es estado)

`userData/credentials.bin` — `safeStorage.encryptString` de:

```json
{ "<user_id>": { "device_id", "token", "gen", "exp", "partner_slug", "display_name" } }
```

Nunca en claro; por persona; se borra la entrada al desemparejar. Sin
`safeStorage` disponible, no se escribe y la barra lo dice.

## 6. Diagrama

```
partners ─┬─< partner_devices (partner_id, principal_id, gen) ─< device_client_links >─ tenants
          │                                                            │ (workdir)
          └─< device_pairing_codes (principal_id, code_hash) ──consumed──┘
tenants ──< local_executables · local_argument_grants · local_executions (device_id →)
```
