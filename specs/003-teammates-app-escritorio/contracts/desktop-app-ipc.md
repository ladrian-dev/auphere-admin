# Contrato — el canal de la pantalla de operar (`app-ipc.ts`)

La vista `appView` (partición `auphere-app`, `preload` `app-preload.cjs`) solo
puede hablar con el proceso principal por **esta lista**. `app-ipc.ts` la
declara como datos (nombre, forma de entrada, forma de salida) y dos tests la
recorren: uno afirma que el `preload` expone exactamente estos nombres; otro,
que ninguna salida contiene claves `session`, `cookie`, `token`, `credential`,
`authorization` a ninguna profundidad (CE-007).

## Invocaciones (`ipcRenderer.invoke`)

| Canal | Entrada | Salida | Qué hace el principal |
|---|---|---|---|
| `app:whoami` | — | `{user_id, partner_slug, locale, role, permissions[]}` | `consoleWhoami` (002) — sin cookies |
| `app:roster.list` | — | `TeammateOut[]` | `PlatformClient.get('/api/teammates')` |
| `app:roster.create` | `TeammateIn` | `TeammateOut` | POST |
| `app:roster.update` | `{id, patch}` | `TeammateOut` | PATCH |
| `app:roster.archive` | `{id}` | `void` | DELETE |
| `app:roster.jobs` | — | `{jobs[], models[]}` | GET |
| `app:thread.open` | `{teammate_id}` | `{thread_id}` | busca o crea el hilo de la persona con ese teammate |
| `app:thread.events` | `{thread_id, since_seq}` | `WireEvent[]` | historial |
| `app:thread.send` | `{thread_id, text, client_ref?}` | `{run_id, task_id}` | POST run |
| `app:thread.cancel` | `{run_id}` | `void` | DELETE run |
| `app:stream.open` | `{run_id, since_seq}` | `{stream_id}` | abre el SSE en el principal; los eventos llegan por `app:event` |
| `app:stream.close` | `{stream_id}` | `void` | |
| `app:inbox.list` | — | `InboxItemOut[]` | |
| `app:inbox.decide` | `{action_id, run_id, decision, note?}` | `{ok}` | POST resume |
| `app:tasks.list` | `{state?}` | `TaskOut[]` | |
| `app:tasks.cancel` | `{task_id}` | `void` | |
| `app:policy.prefs` | — | `{ceiling, global, per_executable[]}` | |
| `app:policy.setPref` | `{executable|null, mode}` | `{effective, capped}` | |
| `app:usage` | — | `{budget, by_teammate[]}` | |
| `app:env.forThread` | `{thread_id}` | `{machine, presence, workdir, client_ref, files[]}` | de `runtime.links` y presencia (002) — solo metadatos |
| `app:openConsole` | `{path}` | `void` | muestra la vista de la consola en esa ruta |
| `app:notifications.prefs` | `{silence_aviso?}` | `{silence_aviso}` | `userData`, no plataforma |

## Suscripciones (`ipcRenderer.on`)

| Canal | Payload |
|---|---|
| `app:event` | `{stream_id, event: WireEvent}` |
| `app:inbox.changed` | `{action_id, decision}` |
| `app:task.state` | `{task_id, state, reason}` |
| `app:session` | `GateDecision` de 002 (`start · stop · pair_needed`) — la pantalla pasa a «sin sesión» o «sin emparejar» |
| `app:presence` | `{machine, presence}` |

## Lo que no existe y no existirá aquí

`fs`, `shell`, `child_process`, URLs arbitrarias (`openInBrowser` es de la barra
y solo acepta el origen de la consola), lectura de cookies, tokens, la ruta del
`workdir` como algo escribible (solo se muestra).
