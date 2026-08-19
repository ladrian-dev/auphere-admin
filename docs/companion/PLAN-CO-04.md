# PLAN-CO-04 · Propuesta, HITL y ejecución

> Agente B de la Ola 1. Ejecuta §6.2, §6.3 y §10 de la investigación con la
> mecánica del §3 y §4 de [`CONTRACT-V1.md`](CONTRACT-V1.md).
>
> **El contrato manda.** Donde este plan y el contrato difieran, gana el
> contrato; lo que aquí se decide es solo lo que el contrato delegó
> explícitamente en el Agente B (los endpoints reales por `kind`, §3.1, y qué
> entra en el `state_hash` por `kind`, §3.5).

---

## 0. La forma del cambio en una pantalla

```
 modelo pide  console.propose_prompt(...)          ← herramienta clase "propose"
      │        lee /console/clients/{ref}/agent (GET, router, RLS)
      │        calcula diff + impacto + state_hash
      │        NO escribe nada · la deja en toolbelt.pending
      ▼
 nodo plan      phase.changed(plan) → plan.proposed
                UPSERT companion.actions (id determinista, status=proposed)
                phase.changed(awaiting) → hitl.requested{expires_at}
      ▼
 nodo confirm   interrupt()   ← UNA SOLA LÍNEA. Nada más en el nodo (C2)
      ▼                        [ el grafo para; run A queda aparcado ]

 POST /console/companion/runs/{A}/resume {action_id, decision, note?}
      → 404 opaco · 409 already_decided/expired · 412 state_changed · 202
      → status: confirmed | superseded | cancelled
      → arranca run B con Command(resume=…)
      ▼
 run B          hitl.resolved{decision, by, at, note}
 nodo execute   phase.changed(execute) → console.apply(action_id)
                 └─ ÚNICA herramienta "mutates". Falla en el MOTOR si la
                    acción no está en `confirmed` (garantía C4)
 nodo verify    phase.changed(verify) → verify.result   ← código determinista
 nodo respond   phase.changed(respond) → text.delta … → run.completed
```

---

## 1. Decisiones abiertas y cómo se cierran

### D1 · Los endpoints reales por `kind` (§3.1 delega en B)

Se verificaron uno a uno contra `app.routes`. **Cinco de nueve difieren de la
tabla del contrato**; manda la ruta real y se anota aquí, que es lo que el
contrato pide. A y C no consumen esa columna, así que no es cambio de contrato.

| `kind` | Contrato §3.1 | **Ruta real** | Cuerpo |
|---|---|---|---|
| `client` | `POST /console/clients` | ✅ igual | `ClientCreateIn` |
| `prompt` | `PUT …/agent/draft` | ❌ **`POST /console/clients/{ref}/agent/versions`** | `AgentDraftIn` |
| `policy` | `PUT …/agent/settings` | ✅ igual | `AgentSettingsIn` |
| `tools` | `PUT …/tools` | ✅ igual | `ToolsIn` |
| `skills` | `PUT …/skills` | ✅ igual | `SkillsIn` |
| `publish` | `POST …/agent/publish` | ❌ **`POST /console/clients/{ref}/agent/versions/{version}/publish`** | — |
| `channel_role` | `PATCH …/channels/{id}` | ❌ **`PATCH /console/clients/{ref}/channels/{channel_id}/role`** | `ChannelRoleIn` |
| `usage_alerts` | `PUT /console/usage/alerts` | ✅ igual | `UsageAlertsIn` |
| `invite` | `POST /console/members/invitations` | ❌ **`POST /console/team/invitations`** | `InviteIn` |

No existe `PUT …/agent/draft`: en esta plataforma el borrador **es** una versión
`staged`, y se crea con `POST …/agent/versions`. Y `publish` necesita el número
de versión en la ruta, así que la propuesta tiene que fijarlo al proponer — que
además es lo correcto: publicar "la última" cuando alguien apiló otra versión
entremedias es exactamente el fallo que el `state_hash` existe para atrapar.

### D2 · Qué entra en el `state_hash` por `kind` (§3.5 delega en B)

Regla del contrato: entra **lo que, si cambia, invalida el diff que el humano
vio**. Ni más (un hash de todo el recurso da 412 espurios cada vez que alguien
mira una página y se toca un `last_seen_at`) ni menos.

Es SHA-256 sobre JSON canónico (`sort_keys`, separadores compactos) de:

| `kind` | Se lee | Entra en el hash |
|---|---|---|
| `client` | `GET /console/me` + `GET /console/clients` | `{quota_used, quota_max, ref_taken}` |
| `prompt` | `GET …/agent` | `{base_version, prompt_sha}` de la versión sobre la que se hizo el diff |
| `policy` | `GET …/agent/settings` | `{version, settings}` completo |
| `tools` | `GET …/tools` | `{version, enabled: [...ordenado]}` |
| `skills` | `GET …/skills` | `{version, enabled: [...ordenado]}` |
| `publish` | `GET …/agent` | `{active_version, target_version, target_prompt_sha}` |
| `channel_role` | `GET …/channels` | `{roles: {channel_id: role}}` de **todos** los canales |
| `usage_alerts` | `GET /console/usage/alerts` | `{cap, recipients ordenados, enabled}` |
| `invite` | `GET /console/team` | `{emails_miembros ordenados, invitaciones_pendientes ordenadas, caller_role}` |

Dos elecciones que merecen defensa:

- **`channel_role` hashea TODOS los canales, no solo el que se toca.** La regla
  de negocio es *con más de un canal activo y ningún rol asignado se rechaza el
  envío*: el impacto de etiquetar un canal depende de cómo están etiquetados los
  demás. Un diff calculado con un canal y aplicado con dos es un diff mentiroso.
- **`invite` incluye el rol del llamante.** Si a la persona la degradan mientras
  decide, la invitación que iba a crear puede quedar por encima de su propio rol
  — que es justo lo que C6 prohíbe. El 412 la obliga a volver a proponer.

### D3 · Una acción por run, no un plan de N escrituras encadenadas

`plan.proposed.steps` es una lista y puede tener varios pasos, pero **cada run
pone en `proposed` como mucho UNA acción**.

Es lo que hace posible cumplir C2 al pie de la letra: el nodo del `interrupt()`
tiene **una llamada, incondicional**. Con N acciones por turno harían falta N
`interrupt()` correlacionados por índice, y la propia investigación avisa de que
saltarse uno según una condición desalinea toda la correspondencia.

Y es lo que dibuja la secuencia del §4.3 del contrato, que es literal:
`run B → hitl.resolved → execute → verify → respond → run.completed`. Un
segundo paso es un turno nuevo. R4 ("parar al primer fallo") sale gratis.

### D4 · El run pausado no muere ni bloquea

`astream_events` **vuelve** cuando el grafo llega al `interrupt()`. El contrato
(§4.3) dice que run A sigue en `running` hasta que el resume lo cierra, así que:

- el driver detecta la pausa al ver pasar `hitl.requested` y marca
  `handle.extras["awaiting_action"]`;
- `_run_with_lifecycle` **no publica `run.completed`** para un run aparcado — si
  lo hiciera, el cajón daría el turno por terminado con la tarjeta de
  confirmación en pantalla y el stream se cerraría;
- se aparca la fila (`_park_run`): se guardan tokens y la respuesta parcial,
  `status` sigue `running` y `ended_at` sigue `NULL`. Sin esto los tokens del
  turno no cuentan contra el tope mensual;
- **un run aparcado no cuenta en `_guard_concurrency` ni lo barre el reaper ni
  lo cierra `terminal_check`.** El predicado es "tiene una acción en
  `proposed`". Sin esta exclusión, el techo de duración (300 s) mataría cada
  espera humana mucho antes de los 15 minutos de caducidad;
- al caducar la acción (15 min, lectura perezosa) el run deja de estar aparcado
  y el reaper lo cierra solo. Se cura sin cron.

### D5 · `superseded` y `applying` no caben en el CHECK de la 0090

El contrato §3 dice "la migración no cambia: todas las **columnas** necesarias
existen" — y es cierto. Lo que no existe son dos **valores**:
`ck_companion_actions_status` de la 0090 admite
`proposed · confirmed · cancelled · expired · applied · failed`, y el §3.3 exige
además `superseded` (decisión `edit`) y `applying`.

Se añade **`0091_companion_action_states`**: un archivo nuevo que solo amplía
ese CHECK. No toca la 0090, no toca ninguna otra tabla y no colisiona con las
zonas de A ni de C. Queda anotado en el informe como lo único que se construye
fuera de la zona estricta.

### D6 · `diff` se persiste envuelto, se sirve como lista

`CompanionAction.diff` está tipado `Mapped[dict | None]` (`db/models/companion.py`,
fuera de mi zona). El contrato sirve `diff` como **lista** de operaciones. Se
persiste `{"lines": [...]}` y se desenvuelve al construir el evento y el
`CompanionActionOut`. La columna es JSONB opaca; nadie más la lee.

### D7 · `console.apply` está en el catálogo que ve el modelo

Podría no estarlo: en el camino normal la llama el nodo `execute`, no el modelo.
Se deja visible **a propósito**, porque es lo que da contenido a C4: el modelo
*puede* pedirla y el motor la rechaza si la acción no está en `confirmed`. Una
puerta cerrada que nadie puede empujar no demuestra nada.

El nodo `execute` la invoca por el mismo camino (`toolbelt.call`), así que los
eventos `tool.call.started` / `tool.call.completed` salen solos y la secuencia
del §4.3 se cumple sin código especial.

### D8 · Clases de herramienta y la invariante de Managed Agents

`ToolSpec` gana `tool_class` ∈ `read|propose|mutates` y `permission_policy` ∈
`always_allow|always_ask`, comprobadas en `__post_init__` — un `mutates` con
`always_allow` **no se puede construir**, no es que falle un test después.

- las 18 de CO-02 → `read` + `always_allow` (por defecto, sin tocar sus filas);
- las 9 `propose_*` → `propose` + `always_ask`;
- `console.apply` → `mutates` + `always_ask`, y **es la única**.

`READ_TOOLS` se queda **intacta** y sigue siendo solo-GET: el test de
aislamiento `test_every_tool_reads_a_console_route_and_nothing_else` la recorre
exigiendo `method == "GET"`. Las nuevas viven en `PROPOSE_TOOLS` y `APPLY_TOOLS`;
`TOOLS_BY_NAME` es la unión y `tool_specs()` publica las tres.

### D9 · El modo del hilo se comprueba en el motor, no solo en el catálogo

Publicar solo las lecturas en modo *Consultar* (`tool_specs(mode=…)`) cambia lo
que el modelo **ve**, no lo que el ejecutor **acepta**. Un modelo que se invente
el nombre de una herramienta que no le dieron —y pasa— la ejecutaría igual.

El gate vive en `CompanionToolbelt.call()`: en `consult`, cualquier herramienta
que no sea `read` se rechaza antes de validar argumentos. Lo destapó el test de
integración del hilo en modo Consultar, que con el gate solo en `specs()` pasaba
en verde mientras creaba la acción.

### D10 · `intake.missing` se emite de verdad

El contrato lo declara y la Ola 1 no trae el expediente como máquina de estados
(eso es CO-06), así que era fácil dejarlo declarado y sin emisor — y entonces lo
que pinta el Agente A sería código muerto.

Se emite: `console.propose_client` comprueba los cuatro campos del §7.1
(`vertical`, `timezone`, `language`, `forbidden_behaviour`) **antes de leer
nada**, y si falta alguno lanza `IntakeRequired` en vez de construir la
propuesta. El nodo `intake` emite el evento y el turno termina preguntando.

`forbidden_behaviour` es obligatorio a propósito y viaja en `placeholders` del
alta: si se quedara fuera del aprovisionamiento se perdería justo el dato por el
que se preguntó.

### D11 · `GET /console/companion/threads/{thread_id}/runs` (contrato v1.1 §5.2)

Añadido a mitad de sesión por decisión del orquestador. Cae dentro de la zona B.
Orden ascendente por `started_at`, sin paginación, 404 opaco, metadatos y nada
más (`run_id`, `status`, `started_at`, `ended_at`). El caso que lo justifica es
justo el de CO-04: una confirmación parte la conversación en **dos** runs, y el
cajón necesita enumerarlos para reconstruir el timeline del hilo al recargar.

### D12 · Ni una palabra de auto-verificación en el prompt (C5)

`<lo_que_puedes_hacer_ahora>` se reescribe (el propio CO-01 dejó anotado que
había que hacerlo al añadir escrituras) para decir que ahora **propone** y que
nada se aplica sin confirmación. No entra "revisa tu trabajo", ni
"double-check", ni subagentes. La verificación es el nodo `verify`, y es una
relectura por HTTP con comparación en Python.

---

## 2. Archivos

| Archivo | Qué hace |
|---|---|
| `companion/tools/catalog.py` | `tool_class` + `permission_policy` + las 9 `propose_*` + `console.apply` |
| `companion/tools/proposals.py` | **nuevo** — el cálculo por `kind`: lectura, diff, impacto, `state_hash`, riesgo, petición de aplicación |
| `companion/tools/actions.py` | **nuevo** — persistencia (UPSERT), caducidad perezosa, revalidación de hash, aplicación y verificación determinista |
| `companion/tools/runner.py` | ramas `propose` / `mutates` en `call()`; implementa el puerto de acciones del grafo |
| `companion/tools/errors.py` | tres errores nuevos (`not_confirmed`, `state_changed`, `action_expired`) |
| `api/companion_streaming.py` | los 5 eventos nuevos en `COMPANION_EVENTS` |
| `api/console/schemas_companion.py` | `CompanionResumeIn` · `CompanionResumeOut` · `CompanionActionOut` |
| `api/console/companion.py` | `POST …/runs/{run_id}/resume`, `GET …/actions/{action_id}`, aparcado del run, exclusiones del reaper y del tope |
| `core/console_auth.py` | **solo** la rama de `ConsolePrincipal.actor` → `companion:{user_id}` |
| `config.py` | `companion_action_ttl_seconds` (900) — añadido, nada reescrito |
| `worker/runtime/companion/state.py` | 4 fases nuevas + claves de estado del HITL |
| `worker/runtime/companion/graph.py` | nodos `plan`, `confirm`, `execute`, `verify` + enrutado |
| `worker/runtime/companion/tools.py` | el puerto `ActionPort` que el grafo usa sin conocer HTTP |
| `worker/runtime/companion/prompt.py` | `<lo_que_puedes_hacer_ahora>` + `<escrituras>` |
| `alembic/versions/0091_companion_action_states.py` | `superseded` + `applying` en el CHECK |
| `tests/unit/test_companion_actions.py` | propuestas, hash, caducidad, diff |
| `tests/unit/test_companion_action_graph.py` | C2: el nodo del interrupt, UPSERT, id determinista |
| `tests/isolation/test_companion_action_guarantees.py` | C4, C5 (secreto y verificación), C6 |
| `tests/integration/test_companion_action_resume.py` | el ciclo entero por HTTP: 202/409/412/404 |

---

## 3. Orden de construcción

1. Migración 0091 (sin ella nada de lo demás persiste).
2. Catálogo: clases, invariante, las 10 filas nuevas.
3. `proposals.py` — el cálculo por `kind`. Es donde está el trabajo.
4. `actions.py` — UPSERT, caducidad, hash, aplicar, verificar.
5. `runner.py` + puerto del grafo.
6. Eventos + fases + nodos del grafo.
7. Endpoints `resume` y `actions/{action_id}`.
8. `actor` de auditoría.
9. Tests, en el orden de las garantías: C2 → C4 → C6 → C5.

## 4. Lo que este plan NO hace

- `companion.run_playground_turn` (CO-05) ni `companion.run_eval`.
- El expediente como máquina de estados (CO-06). `intake.missing` se emite,
  pero el expediente es contexto del hilo, no estado de servidor.
- La pausa con estado del §23.2 (CO-08). El tope mensual sigue siendo 429 en
  `POST …/runs`; lo único que cambia es que **no** se aplica en `resume`.
- La rama de `_human_actor` en `api/console/audit.py`: es del orquestador.
- Cualquier `kind` de la lista prohibida del §6.5. No se añaden, y hay un test
  que comprueba que el mapa de endpoints no toca `/console/keys`,
  `/console/billing` ni ningún `DELETE`.
