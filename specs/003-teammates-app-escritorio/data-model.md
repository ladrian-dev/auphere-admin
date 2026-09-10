# Data model — 003 teammates en la aplicación de escritorio

Todo lo nuevo es de **partner** o de **persona**; nada lleva `tenant_id`
salvo lo que ya lo llevaba. Los ids internos no salen de la API.

## Tablas nuevas

### `teammates` (partner) — migración 0109

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `partner_id` | uuid FK partners | RLS por `app.partner_id` (política como `partner_devices_owner`, sin filtro por principal: todos ven el roster) |
| `name` | text ≤ 80 | no único: dos «Sofía» se permiten (caso límite) |
| `job` | text ≤ 80 | semilla de ocho; libre |
| `model` | text | debe estar en la lista que publica la plataforma (`partner_model_allowlist`) |
| `tool_names` | text[] | **⊆ `ALL_TOOLS`**, validado en la API; CHECK `array_length ≥ 0` |
| `permissions` | jsonb | `{read, write, spend, publish, contact}` booleanos — lo que el formulario pintó; la verdad operativa es `tool_names` |
| `local_exec` | bool | si puede pedir `shell_local` |
| `status` | text | `active · archived` |
| `created_by` | text | principal |
| `created_at`, `updated_at`, `archived_at` | timestamptz | |

Invariantes: `archived_at IS NOT NULL ⇔ status = 'archived'`; nunca `DELETE`.

### `teammate_tasks` (persona) — migración 0110

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `thread_id` | uuid FK threads | el hilo ya tiene RLS por `principal_id`; la tarea hereda por `EXISTS` sobre el hilo (patrón 0090) |
| `teammate_id` | uuid FK teammates | |
| `principal_id` | text | copiado del hilo |
| `title` | text | primera línea del encargo |
| `state` | text | `en_marcha · esperandote · pausada_por_tope · terminada · cancelada · caducada` |
| `expires_at` | timestamptz | tope de vida: ahora + `teammate_task_ttl_days`, se desplaza con cada evento |
| `current_run_id` | uuid FK runs NULL | |
| `pending_action_id` | uuid FK actions NULL | solo en `esperandote` |
| `created_at`, `updated_at`, `ended_at` | | |

Transiciones:

```
en_marcha ──hitl.requested──▶ esperandote ──resume(approve|deny)──▶ en_marcha
en_marcha ──budget.paused───▶ pausada_por_tope ──tope subido──────▶ en_marcha
en_marcha ──run.completed───▶ terminada
cualquiera ──cancelar────────▶ cancelada
esperandote ──expires_at─────▶ caducada   (la acción se cierra 'expired' con motivo 'task_expired')
esperandote ──teammate archivado▶ cancelada (acción 'expired', motivo 'teammate_archived')
```

### `partner_local_exec_policy` (partner) — migración 0111

| Columna | Tipo | Notas |
|---|---|---|
| `partner_id` | uuid PK/FK | una fila por partner; ausente ⇒ `ask` |
| `ceiling` | text | `ask · always · never` |
| `updated_by`, `updated_at` | | |

### `principal_local_exec_prefs` (persona) — migración 0111

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `partner_id` | uuid FK | RLS por partner **y** `app.principal_id` (como `partner_devices_owner`) |
| `principal_id` | text | |
| `executable` | text NULL | NULL = global; mismo patrón que `local_executables.executable` |
| `mode` | text | `ask · always · never` |
| UNIQUE `(partner_id, principal_id, executable)` | | |

Resolución (en `LocalExecGate`): `pref = prefs[executable] ?? prefs[NULL] ?? ask`;
`effective = min(ceiling, pref)` con `never < ask < always`.

## Columnas nuevas

| Tabla | Columna | Notas |
|---|---|---|
| `threads` | `teammate_id uuid FK NULL` | NULL = hilo del Companion clásico. Índice `(principal_id, teammate_id)` |
| `runs` | `teammate_id uuid NULL`, `task_id uuid NULL` | denormalizados al crear; `teammate_id` para agregar consumo |
| `runs.status` | + `waiting` | el run cerró aparcado; la tarea sigue |
| `actions` | `level text` (`critico · aviso · informativo`), `expires_at timestamptz NULL` | CHECK: `expires_at IS NULL` solo si el hilo tiene `teammate_id` (trigger o CHECK vía función) |
| `actions.kind` | + `local_exec` | payload `{execution_request: {executable, args, cwd_relative, client_ref}, argv_signature}` |
| `local_executions` | `task_id uuid NULL`, `teammate_id uuid NULL` | trazabilidad; **sin** salida |
| `local_executions.denial_reason` | + `politica_nunca` | vocabulario cerrado |
| `local_argument_grants` | `by_policy bool default false` | concedido por `always`, con la persona como `decided_by` |

## Vocabulario de auditoría (0112)

`teammate.created` · `teammate.updated` · `teammate.archived` ·
`local_policy.ceiling_changed` · `local_policy.pref_changed` ·
`local_exec.allowed_once` · `local_exec.allowed_by_policy` ·
`local_exec.denied_by_policy` — todas con `{actor}` = persona; `target`
`teammate:<id>` o `partner:<id>`; tenant NULL.

## Permisos (`core/console_auth.py`)

| Permiso | Roles | Puerta de |
|---|---|---|
| `teammates:use` | owner, admin, builder | roster, hilos, bandeja, crear, preferencias propias |
| `teammates:policy` | owner, admin | techo del partner (página de equipo) |

## Derivados que la API calcula

- **`last_done`** (roster): título de la última `teammate_task` en `terminada` de
  esa persona con ese teammate; `null` si no hay.
- **`can_decide`** (bandeja): el permiso de la herramienta que hay detrás de la
  acción (`action.kind` → permiso del router que la aplica) está en
  `permissions_for(role)` de la persona. Es el mismo permiso que `resume` exige.
- **Nota de cambio de teammate**: al cambiar oficio o permisos se inserta en cada
  hilo activo un mensaje `role=system`, `kind=teammate_changed`, con `seq`; se ve
  al cargar el historial. No hay evento nuevo.
- **`teammate_tasks.expires_at`** se desplaza con cada run que termina y con
  cada decisión.

## Identificadores

Sin tildes en enums y columnas (`esperandote`, `critico`); la prosa de la spec
lleva tilde. Dos nombres para el tope a propósito, porque son dos entidades: la
**tarea** está `pausada_por_tope` (columna), el **hilo** se pinta
`en_pausa_por_tope` (derivado de `budget.paused`).

## Estados de la pantalla (derivados, nunca almacenados)

- **Hilo**: `normal · cargando · vacío · error · reconectando · parcial` (de
  `companion-ui/state.ts`) + `esperandote` (tarea) + `en_pausa_por_tope`
  (`budget.paused`) + `maquina_ausente` (presencia de 002 y `local_exec`).
- **Roster**: por teammate y persona: `en_marcha` (run vivo) ·
  `esperandote` (tarea) · `en_pausa_por_tope` · `en_espera` (nada vivo); `unread`
  si hay eventos desde la última lectura.

## Índices y consultas calientes

- `actions (status, thread_id)` para la bandeja; `threads (principal_id,
  teammate_id)`; `runs (teammate_id, started_at)` para el consumo del mes;
  `teammate_tasks (state, expires_at)` para el barrido de caducidad (job
  programado existente, cada 10 min).
