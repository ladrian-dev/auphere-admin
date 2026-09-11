# Contrato — `/console/teammates/*` y lo que cambia en `/console/companion/*`

Todo bajo `/console/*`, con el principal de la consola (`test_console_scope`
lo cubre automáticamente). Ninguna ruta acepta `partner_id`, `principal_id` ni
`tenant_id`. Ningún cuerpo lleva mensajes de cliente final.

## Roster

| Método y ruta | Permiso | Cuerpo / respuesta |
|---|---|---|
| `GET /console/teammates` | `teammates:use` | `TeammateOut[]` — `{id, name, job, model, tool_names, permissions, local_exec, status, my_state, my_unread, last_done}` (`my_*` derivados del hilo de la persona) |
| `POST /console/teammates` | `teammates:use` | `TeammateIn {name, job, model, permissions}` → 201 `TeammateOut`; la API traduce `permissions` a `tool_names` y valida ⊆ `ALL_TOOLS`; 422 si el modelo no está en la lista |
| `PATCH /console/teammates/{id}` | `teammates:use` | campos de `TeammateIn`; el siguiente run usa el catálogo nuevo; el hilo recibe una nota |
| `DELETE /console/teammates/{id}` | `teammates:use` | archiva (204); cierra tareas `esperandote` como `cancelada`; nunca borra |
| `GET /console/teammates/{id}/changes` | `teammates:use` | `TeammateChangeOut[] {id, fields[], by, at}` — qué cambió y quién, nunca los valores; el hilo lo pinta al abrir |
| `GET /console/teammates/jobs` | `teammates:use` | semilla de oficios y lista de modelos `{id, note, cost_label}`; `cost_label` es relativo a la oferta del partner (`bajo·medio·alto·desconocido`), no un precio |

## Hilos y tareas (extienden el Companion)

| Método y ruta | Cambio |
|---|---|
| `GET /console/companion/threads?teammate_id=` | filtra por teammate; **sin** `teammate_id` devuelve solo hilos sin teammate (la consola no ve teammates) |
| `POST /console/companion/threads` | acepta `teammate_id`; el hilo nace con el modo del teammate |
| `POST /console/companion/threads/{id}/runs` | si el hilo tiene teammate: crea o continúa la `teammate_task` y el run lleva `task_id`/`teammate_id`; techos de D6 |
| `GET /console/teammates/tasks?state=` | tareas de la persona; `TaskOut {id, thread_id, teammate_id, title, state, expires_at, pending_action_id, current_run_id}` |
| `POST /console/teammates/tasks/{id}/cancel` | → `cancelada`; 409 si terminal |
| `POST /console/companion/runs/{id}/resume` | para acciones de teammate: sin 409 `action_expired` por reloj; abre un run nuevo en la tarea |

## Pendientes

| Método y ruta | Respuesta |
|---|---|
| `GET /console/teammates/inbox` | `InboxItemOut[]` — `{action_id, task_id, thread_id, teammate, client_ref, title, level, trial, undo_hint, proposed_at, can_decide}`; solo hilos de la persona con teammate; `can_decide=false` cuando el permiso de la herramienta detrás de la acción no está en `permissions_for(role)` — el mismo que exige `resume` |
| `GET /console/teammates/inbox/stream` | SSE por persona: `inbox.changed {action_id, decision, by}` y `task.state`; un `ping` **al abrir** (dice que la suscripción ya está hecha) y luego cada 15 s. **Sin historial**: el cliente refresca `GET /inbox` en cada (re)conexión |

## Política de ejecución local

| Método y ruta | Permiso | Cuerpo |
|---|---|---|
| `GET /console/team/local-exec-ceiling` | `team:read` | `{ceiling}` |
| `PUT /console/team/local-exec-ceiling` | `teammates:policy` | `{ceiling: ask|always|never}`; audita `local_policy.ceiling_changed` |
| `GET /console/teammates/local-exec-prefs` | `teammates:use` | `{ceiling, global, per_executable: [{executable, mode, effective}]}` — `effective` ya acotado |
| `PUT /console/teammates/local-exec-prefs` | `teammates:use` | `{executable: string|null, mode}`; audita `local_policy.pref_changed`; la respuesta trae `effective` y `capped: bool` |

## Consumo

| Método y ruta | Respuesta |
|---|---|
| `GET /console/teammates/usage` | `{budget: CompanionBudgetOut (el mismo objeto que /companion/budget), by_teammate: [{teammate_id, name, input_tokens, output_tokens, runs}]}`. **Sin `cost_usd`**: `companion.runs` no guarda con qué modelo corrió el turno, así que un importe sería una estimación con el precio de hoy — y el medidor y el tope son en tokens (C9). El reparto suma los runs de todas las personas del partner, como el medidor: el roster es del partner |

## Errores

`{detail: {code}}` con códigos cerrados: `teammate_archived`, `model_not_allowed`,
`tool_not_in_catalog`, `task_terminal`, `cannot_decide_client`, `policy_capped`.
