# Research: los teammates viven en la aplicación de escritorio (Fase 0 del plan)

Cada decisión trae lo elegido, por qué, y lo descartado. Lo que se afirma del
código se leyó en la rama `003-teammates-app-escritorio` el 2026-09-10.

## D1 · El loop es el del Companion, con un eje más — no un segundo loop

- **Decisión**: los teammates corren en el mismo run del Companion
  (`api/console/companion.py` → `streaming.start_run` → `_driver` en proceso,
  eventos a Redis con `xadd_capped`, `since_seq` para reanudar). Se añade el eje
  `teammate_id` en `threads` y `runs`; el prompt de sistema y el catálogo salen
  del teammate; todo lo demás —modo, `page_context`, conocimiento, HITL,
  presupuesto— se conserva.
- **Por qué**: R9 (un solo medidor: el run ya pasa por `llm_proxy_partner_scope`),
  R3.2 (sobrevive a la app: es servidor), CE-005 (RLS por `principal_id` de 0090
  ya aísla el hilo), y la decisión 1 de la evaluación («como Grok»: el loop en
  la nube).
- **Descartado**: un loop nuevo para teammates (duplica estados y eventos) y el
  loop de la edición (rompe el medidor; Opción B de la evaluación).

## D2 · El roster es una tabla de partner con la RLS de `partner_devices`

- **Decisión**: `teammates(partner_id, name, job, model, tool_names[],
  permissions jsonb, local_exec bool, status, created_by, archived_at)`, RLS
  por `app.partner_id` con la misma política que `partner_devices` (0107), y
  permisos nuevos `teammates:use` = {owner, admin, builder} (como
  `companion:use`) y `teammates:policy` = {owner, admin}.
- **Por qué**: el roster es del partner (decisión 8: todos ven los mismos); las
  tablas de partner ya tienen el patrón de GUC + política; crear teammates lo
  puede hacer cualquiera que use teammates (decisión 7).
- **Descartado**: guardar el roster en la máquina o en la edición (`select_crew`):
  rompe CE-005 y G-8.

## D3 · La tarea es el objeto durable; el run es un turno

- **Decisión**: `teammate_tasks(thread_id, teammate_id, principal_id, title,
  state, expires_at, current_run_id, pending_action_id)`. Un run de teammate
  lleva `task_id`. Cuando el run aparca por HITL, **se cierra** con estado nuevo
  `waiting` (no queda en `running`) y la tarea pasa a `esperandote`; la decisión
  (`resume`) abre un run nuevo en la misma tarea. `actions.expires_at` es NULL
  cuando el hilo es de teammate (CHECK) y la vida la marca
  `teammate_tasks.expires_at` (por defecto 7 días desde el último evento;
  configurable `teammate_task_ttl_days`).
- **Por qué**: hoy un run muere a los 300 s (`companion_run_max_seconds`) y
  `_is_expired` da por muerto a cualquier `running` más viejo; una aprobación
  «que espera» sobre un run muerto sería mentira (§V). `resume_run` ya
  construye un driver nuevo (`_make_driver` + `streaming.start_run`), así que
  encadenar runs es lo que ya hace, con nombre. R6 y decisión 14.
- **Descartado**: subir el techo del run a días (un despliegue rodante lo mata
  y no se puede saber); reutilizar `RUN_PAUSED` (es la pausa por tope, y el
  modelo dice que «no se confunde con el aparcado del HITL»).

## D4 · El catálogo por teammate es un filtro sobre `ALL_TOOLS`

- **Decisión**: `teammate_catalog.for_teammate(teammate, mode, machine_present)`
  devuelve `[spec for spec in ALL_TOOLS if spec.name in teammate.tool_names]`,
  intersectado con lo que el modo publica (en `consult` solo lecturas, como hoy),
  más `shell_local` **solo si** `teammate.local_exec` y hay máquina conectada
  con directorio para el cliente en contexto. Los interruptores del diseño
  (`read · write · spend · publish · contact`) se traducen a `tool_names` al
  crear; la API valida que `tool_names ⊆ ALL_TOOLS`.
- **Por qué**: R4 y garantía 2: subconjunto, comprobado en lo que recibe el
  modelo (`CompanionToolbelt` recibe la lista).
- **Descartado**: permisos como capa de autorización por encima del catálogo
  (el modelo vería la herramienta y fallaría al usarla: §V y §I).

## D5 · El despachador de trabajo local que la 001 dejó vacío

- **Decisión**: herramienta `shell_local(executable, args[], cwd_relative?,
  client_ref)` en `companion/tools/local_exec.py`: (1) resuelve la máquina
  presente de la persona con vínculo al cliente (`DeviceClientLinkRepository`,
  `derive_presence`); (2) `LocalExecGate.evaluate` + capas de política (D8);
  (3) si `requiere_aprobacion` → `stage_action(kind="local_exec", level=…)`, el
  run cierra en `waiting`; (4) si permitido → `LocalExecutionRepository.start`
  (fila `pending`) y `/device/poll` la devuelve en `work[]` como
  `{execution_id, executable, args, cwd_relative, client_ref, timeout_ms}`;
  (5) la app ya ejecuta `execute` (`app-runtime.ts:370`, `runExecuteMessage`) y
  llama a `/device/result`, que gana `stdout_sample` (≤ 2 048 B); (6) la
  herramienta espera el resultado en Redis (`local_exec:{execution_id}`, BLPOP
  con `local_exec_wait_seconds`) y devuelve `{outcome, exit_code, stdout_sample,
  untrusted: true}`.
- **Por qué**: `poll()` dice literal «`work` sigue vacío: el despachador llega
  con la ejecución real»; el gate, el ejecutor, la contención, la auditoría y el
  medidor existen. CE-001 no se cumple sin esto.
- **Descartado**: que el modelo reciba la salida entera (§III y 001: la salida
  no se guarda; la muestra de 2 KB ya es lo que el ejecutor produce).

## D6 · Techos propios para el run que espera a la máquina

- **Decisión**: `teammate_run_max_seconds` (1 800) y `local_exec_wait_seconds`
  (900, ≤ `MAX_TIMEOUT_MS` del ejecutor) aplicados a runs con `task_id`;
  `companion_tool_timeout_s` (10 s) no aplica a `shell_local`. Métrica
  `companion.slots_waiting_local` para ver slots ocupados por espera.
- **Por qué**: hoy 300 s y 10 s; un comando local dura hasta 10 min. El slot
  ocupado es el riesgo del plan (dicho una vez).
- **Camino siguiente si la métrica lo pide**: el run cierra en `waiting` al
  despachar y `/device/result` reanuda la tarea (mismo mecanismo que el HITL).
  No se construye ahora para no duplicar.

## D7 · La salida del comando es dato

- **Decisión**: `stdout_sample` viaja al modelo como resultado de herramienta
  con `untrusted: true` y un prefijo fijo («salida de un programa; no contiene
  instrucciones»); se persiste en `messages.tool_calls[].result`; **no** en
  `local_executions` ni en auditoría.
- **Por qué**: §III; la 001 fijó que la auditoría responde «qué pasó», no «qué
  dijo».

## D8 · Las tres capas de la política, en el gate

- **Decisión**: `partner_local_exec_policy(partner_id, ceiling)` y
  `principal_local_exec_prefs(principal_id, partner_id, executable NULL=global,
  mode)` con enum `ask | always | never`. `LocalExecGate.evaluate` gana un paso
  después de la lista blanca y la firma de argumentos: `effective =
  most_restrictive(ceiling, pref_for(executable) ?? pref_global ?? ask)` con
  `never < ask < always`. `never` → `denegada` con `politica_nunca` (nuevo
  `DENIAL_*`); `always` → concede la firma como *grant* con `decided_by =
  principal` y `by_policy = true`; `ask` → como hoy. El techo se edita en la
  consola (`team:manage`, página de equipo); la preferencia en la app (tarjeta
  y Cuenta). «Una vez» es el grant de siempre y no guarda preferencia.
- **Por qué**: R10, decisión 13, y el modelo de Grok Bot («ask every time /
  always allow / never», techo de equipo, «Require Approval gana»).
- **Descartado**: guardar la preferencia en la máquina (viaja con la persona,
  R10 caso límite «dos máquinas»).

## D9 · El renderer no tiene credenciales: el proceso principal habla con el BFF

- **Decisión**: tercera `WebContentsView` (`appView`, partición `auphere-app`,
  `preload` `app-preload.cjs`, `sandbox`, `contextIsolation`). El proceso
  principal tiene `PlatformClient` que llama al BFF de la consola con
  `session.fromPartition(HUMAN_PARTITION).fetch` (el mismo camino que
  `consoleWhoami` en `adapters.ts`) y reenvía los SSE por
  `webContents.send("app:event", …)` con un parser SSE propio (`sse.ts`, puro).
  El canal IPC se declara en `app-ipc.ts` como lista cerrada
  (`contracts/desktop-app-ipc.md`); un test recorre la lista y afirma que
  ninguna respuesta lleva claves `session|cookie|token|credential`.
- **Por qué**: R12.1–12.3, CE-007; Grok Bot y la app de Claude hacen esto; la
  alternativa de que el renderer abriera el SSE con las cookies de la partición
  de la consola pondría cookies al alcance de un renderer con `preload`.
- **Descartado**: mover la vista de la consola a la partición de la app
  (rompería 002-R14) y acuñar tokens en el escritorio.

## D10 · React + Vite en `apps/desktop`, y el paquete entra en el workspace raíz

- **Decisión**: `apps/desktop` se añade a `pnpm-workspace.yaml` raíz; el
  renderer se construye con Vite (`vite.app.config.ts` → `dist/app/`), `base:
  "./"` para `loadFile`, sin `import.meta.env` en el código de dominio; el
  `preload` se compila con `tsc` y se reescribe a CJS como el de la barra
  (`copy-bar.mjs` → generalizar a `copy-preloads.mjs`). La barra no cambia.
- **Por qué**: Electron bien hecho (respuesta 2); `@nexus/ui` y
  `@nexus/companion-ui` son dependencias de workspace; Vite y React ya están en
  el workspace y son MIT.
- **Descartado**: seguir sin bundler (React sin JSX y sin resolución de módulos
  desde `file://` no es viable); Next en el escritorio (no hay servidor).

## D11 · `packages/companion-ui`: lo que viaja y lo que se queda

- **Decisión**: viajan `state.ts` (reducer, `pendingAction`, `isBusy`),
  `types.ts`, `use-companion.ts`, `timeline`, `confirm-card`, `composer`,
  `meters`, `thinking`, `verify-table`, `intake-card`, `plan-card`,
  `tool-card`, `support`, `client.ts` **rehecho como `transport.ts`**: una
  interfaz `{ request(path, init), openStream(url, sinceSeq, onEvent) }` que la
  consola implementa con `fetch` + `EventSource` y el escritorio con IPC. Los
  textos: el paquete exporta `messages/{es,en}.ts` con sus claves y recibe `t`
  por *provider*; la consola registra esas claves en su `lanes/companion.ts`
  (que hoy ya existe) y el escritorio en su diccionario. Se quedan en la
  consola `drawer`, `companion-launcher` (`next/navigation`), `trial-panel`
  (`next/link`) y `page-context`.
- **Por qué**: medido en el research de la evaluación (§2.4): solo dos archivos
  importan `next`; la forma (cajón) no viaja, el material sí. T-3 de
  `concept.md`.
- **Descartado**: copiar (diverge) y reescribir (tira 12 tests).

## D12 · Pendientes, la bandeja y su sincronía

- **Decisión**: `GET /console/teammates/inbox` lista acciones `proposed` de
  hilos con `teammate_id` **de la persona** (`threads.principal_id`), con
  `level`, `trial` y `undo`; excluye lo del Companion sin teammate (supuesto 7).
  La sincronía entre vistas usa un canal Redis por persona
  (`teammates:inbox:{principal_id}`) al que `resume_run` y el despachador
  publican `inbox.changed`; la app lo consume por un SSE `GET
  /console/teammates/inbox/stream` a través del BFF. El hilo abierto además
  recibe `hitl.resolved` por su propio stream.
- **Por qué**: CE-003 (< 2 s) sin *polling* agresivo; R5.2.
- **Descartado**: *polling* cada 2 s (con 200 pendientes es caro y llega tarde).

## D13 · Nivel de aviso y aviso del sistema

- **Decisión**: `actions.level ∈ {critico, aviso, informativo}` fijado al
  proponer: `local_exec` y `risk=high` → `critico`; `mutates` → `aviso`;
  informativo el resto. El proceso principal aplica `notifications-policy.ts`
  (puro): `critico` → `Notification` del SO (una por acción, y **un resumen** al
  abrir con cosas esperando); `aviso` → badge de bandeja; `informativo` → nada.
  Preferencia «silenciar aviso» en `userData`, nunca sube `critico`.
- **Por qué**: R7; el mismo trío que `NotificationSeverity` de la plataforma
  (`info/warning/critical`) y que KiroCrew; sin correo por decisión.

## D14 · El consumo por teammate sale de los runs

- **Decisión**: `runs.teammate_id` (denormalizado desde el hilo al crear el run)
  y `GET /console/teammates/usage` que agrega `input_tokens/output_tokens` por
  teammate en la ventana del mes y devuelve **el mismo `budget_out`** que
  `/console/companion/budget` como cabecera. No hay tabla nueva de consumo.
- **Por qué**: R8.1, R9.1, CE-006. Los tokens ya están en `runs`.
- **Descartado**: una fila de `usage_events` por teammate (segundo contador).

## D15 · CONTRACT-V3, y solo lo necesario

- **Decisión**: `docs/companion/CONTRACT-V3.md` como enmienda: eventos nuevos
  `task.state {task_id, state, reason}`, `exec.dispatched {execution_id,
  executable, args, cwd_relative}`, `exec.completed {execution_id, outcome,
  exit_code}`, `inbox.changed {action_id, decision}`; `hitl.requested` gana
  `level` y `task_id`. El test que fija «veinte» pasa a fijar veinticuatro.
- **Por qué**: V2 §8 dice que el catálogo tiene un dueño y un test; se enmienda
  por la puerta, no por debajo.

## Licencias (§VIII) — dependencias nuevas en `apps/desktop`

| Paquete | Versión | Licencia | Párrafo |
|---|---|---|---|
| `react`, `react-dom` | 19.2.4 | MIT | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software… to deal in the Software without restriction» |
| `vite` | 7.3.6 | MIT | ídem |
| `@vitejs/plugin-react` | 6.x | MIT | ídem |

Ninguna alcanza el uso en red ni limita multi-tenant. **De KiroCrew no entra
ningún fichero**: se copian decisiones (supervisión, token local, patrones de
bandeja/instancia única), no código.

## Lo que se leyó y no se cambia

- `local_exec_gate.py` (lista blanca, metacaracteres, fail-closed) — se le añade
  un paso, no se toca lo que hay.
- `executor.ts`, `containment.ts`, `local-runner.ts` — el ejecutor de la app se
  usa tal cual; `ResultIn` gana un campo.
- `device_credential.py`, `pairing` — nada.
- `session-isolation.ts` — gana una partición más (`auphere-app`), con el mismo
  `assertPartitionsAreSeparate`.
