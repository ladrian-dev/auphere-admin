# CO-01 · Cimientos del runtime del Companion

> Plan de ejecución del primer paquete del Companion de la consola de partners.
> Fuente de diseño: `Auphere/nexus/research/2026-08-17-companion-agente-de-consola.md`
> — **Parte II (§21-§27) manda sobre la Parte I**.
>
> Este documento vive en el repo a propósito: el cambio cruza `apps/api`,
> `apps/worker` y `apps/console` y toca más de tres archivos. Sobrevive a la
> compactación; el historial de chat no.

---

## 0. Qué entrega CO-01

Los cimientos del runtime. Al terminar:

- una pregunta de solo lectura responde **en streaming**, con **coste real por
  turno** y **porcentaje de ventana de contexto real** (`input_tokens` de la
  última llamada contra `model_profiles.max_context`, nunca estimado por
  caracteres);
- el hilo sobrevive a un F5, a cerrar el portátil y a un **reinicio de la API**;
- el consumo cae en `source='companion'`, con **tope propio** que no compite con
  el del playground ni se le factura al cliente final.

Fuera de alcance: herramientas `console.*` (CO-02), cajón y burbuja (CO-03),
propuestas/HITL/ejecución (CO-04), y todo lo posterior.

---

## 1. Las cinco correcciones de la Parte II, y dónde aterriza cada una

| # | Corrección | Dónde se implementa en CO-01 |
|---|---|---|
| **C1** | El run no muere con la conexión | `POST …/runs` devuelve **202 inmediato**; el log del run vive en un **Redis Stream** (`companion:run:{id}`), no en un búfer de proceso; el SSE es un **lector puro** del log; hay endpoint REST de historial |
| **C2** | `interrupt()` re-ejecuta el nodo entero | No hay HITL en CO-01, pero el terreno queda preparado: `await_confirmation` existe, documentado y **sin cablear**, y `companion.actions` se crea con `id` **sin default** — se derivará del `(run_id, índice de paso)` y se escribirá con UPSERT, porque un INSERT duplicaría la fila en cada confirmación |
| **C3** | El pensamiento llega vacío si no se pide | `COMPANION_THINKING = {"type": "adaptive", "display": "summarized"}` explícito en cada llamada. **Nunca `disabled`**; para bajar coste se baja `effort` |
| **C4** | `page_context` rompe el caché en el prompt de sistema | El prompt de sistema es **estable y cacheado**; el hueco de `page_context` se emite como mensaje `{"role": "system", …}` **dentro de `messages`**. En CO-01 el hueco existe y está probado; el cajón lo rellena en CO-03 |
| **C5** | La verificación es código, no una instrucción al modelo | Ni una palabra de auto-verificación en el prompt. El único guardián de CO-01 (catálogo cerrado de eventos) es **código determinista** en el publicador |

---

## 2. Decisiones abiertas — con recomendación

### D1 · ¿Extender `qa_streaming.py` o módulo nuevo? → **Módulo nuevo**

`api/companion_streaming.py`, importando de `qa_streaming` lo que ya es correcto
(`SSEEvent`, `translate_event`, `_TranslatorState`) y **sin duplicar una línea**
de traductor.

Por qué no extender:

1. **El almacenamiento es distinto, no un parámetro.** `qa_streaming` es un
   registro en memoria con `deque(maxlen=256)` y retención de 60 s. El Companion
   necesita un log durable con reanudación exacta. Eso no es una bandera: cambia
   `_push_event`, `subscribe`, `cancel`, el ciclo de vida y la unidad de prueba.
2. **`qa_streaming` es carga viva.** Lo usan el playground interno (`api/qa.py`)
   y el de la consola (`api/console/playground.py`), con 692 tests detrás.
   Reescribir su almacenamiento para un consumidor que aún no existe es
   arriesgar un camino probado sin ganar nada hoy.
3. **El catálogo de eventos diverge.** El Companion añade siete eventos (§8 de la
   investigación) y —decisión de abajo— los publica contra un **catálogo cerrado**
   que el playground no tiene ni quiere.
4. **La migración inversa es barata.** Si mañana el playground quiere log durable,
   pasa a usar `companion_streaming` con otro prefijo de clave. Al revés no: un
   `qa_streaming` con dos almacenamientos es un condicional en cada función.

Lo que **sí** se comparte, por import y no por copia: el formato de cable
(`SSEEvent.to_wire`), el traductor LangGraph→SSE, el intervalo de heartbeat.

### D2 · El choque con `test_console_scope.py` (decisión C8) → **Opción B + test propio**

`tests/isolation/test_console_scope.py::test_no_response_carries_bodies_or_internal_ids`
recorre el OpenAPI de **todas** las rutas `/console/*` y rechaza cualquier
propiedad llamada `content`, `text`, `body`, `transcript`… con una lista blanca
de tres entradas: `{"system_prompt", "summary", "detail"}`.

El Companion **sí** sirve su propia transcripción por REST
(`GET …/runs/{id}/events`) — es trabajo del partner, no conversación de un
cliente final. Hay dos caminos legítimos; se elige el segundo:

**Opción A — ampliar `ALLOWED_RESPONSE_FIELDS`.** Rechazada. La lista blanca es
**global**: se resta del conjunto de infractores de *todas* las rutas. Meter
`text` ahí para que pase el Companion ciega la comprobación en los otros ~60
endpoints de la consola para siempre. Se cambia un guardián estrecho por un
agujero ancho.

**Opción B — nombrar los campos para que no colisionen, + un test propio.**
Elegida. Concretamente:

- El modelo de respuesta es `CompanionEventOut = {seq: int, event: str, data: dict}`.
  `data` es un objeto **sin propiedades declaradas** (los payloads son
  heterogéneos por diseño: `text.delta`, `cost.updated`, `phase.changed`…), así
  que el recorrido del OpenAPI no encuentra ningún nombre prohibido. Un modelo
  tipado con unión discriminada sería peor: obligaría a declarar `text` como
  propiedad y a mentirle al guardián, o a inventar un nombre torcido para el
  campo más obvio del protocolo.
- **Pero un `dict` opaco no es una garantía**, es la ausencia de una. Por eso el
  guardián real se construye aquí y es más fuerte que el genérico:
  `COMPANION_EVENTS: dict[str, frozenset[str]]` — **catálogo cerrado** de nombre
  de evento → claves permitidas en su payload. El publicador
  (`companion_streaming.publish`) **rechaza** un evento fuera del catálogo y
  **elimina** cualquier clave no declarada. Es código, no convención (C5).
- El test nuevo `tests/isolation/test_companion_no_customer_bodies.py`:
  1. el catálogo es cerrado y ninguna clave nueva entra sin tocar el test;
  2. `text` solo está permitido en eventos **autorados por el Companion**
     (`text.delta`, `reasoning.delta`) y en ningún otro; el resto del conjunto
     prohibido de `test_console_scope` (`content`, `body`, `transcript`,
     `interactive_payload`, `takeover_context`…) **no aparece en ninguna clave
     del catálogo**;
  3. el publicador filtra de verdad: se le pasa un payload con `content` y sale
     sin él (control del control, como el que ya tiene `test_console_scope`).
- Y se deja **comentado en `test_console_scope.py`**, junto a
  `ALLOWED_RESPONSE_FIELDS`, por qué el Companion pasa el recorrido genérico y
  dónde vive su guardián real. Un lector futuro no puede concluir que se coló.

En una frase: *la transcripción del Companion no es texto de un cliente final —
es lo que Auphere le dijo al partner y lo que el partner le dijo a Auphere—, y
la prueba de que nunca llevará texto de un cliente final es un catálogo cerrado
aplicado por el publicador, no una lista blanca ampliada.*

---

## 3. Entregables, en orden de construcción

### 3.1. Migración `0090_companion.py`

`alembic heads` → **`0088_console_identity`**. PLAN-CONSOLE-V1 reserva 0089 para
`partner_billing`, que aún no existe: `down_revision = "0088_console_identity"` y
**se deja el hueco de numeración**. Cuando llegue 0089 se rebasa esa, no esta.

Contenido:

- `CREATE SCHEMA companion`.
- `companion.threads` — `id, principal_id (text), partner_id, tenant_id?, title,
  mode, created_at, updated_at, archived_at, last_run_at`.
- `companion.messages` — `id, thread_id, seq, role, content, tool_calls jsonb,
  input_tokens, output_tokens, model, created_at`. **Sin razonamiento
  persistido** (§8.2: es caro y sus divagaciones se leen luego como compromisos).
- `companion.runs` — `id, thread_id, principal_id, status, started_at, ended_at,
  input_tokens, output_tokens, error`.
- `companion.actions` — `id, thread_id, run_id, kind, payload, diff, state_hash,
  status, proposed_at, decided_at, decided_by, applied_at, result`. Se crea en
  CO-01 aunque la escriba CO-04: el esquema completo en una migración evita una
  segunda pasada de RLS y grants sobre las mismas tablas.
- **RLS forzada por `principal_id`** en las cuatro, mismo patrón fail-closed que
  `qa.*` por `operator_id` (`NULLIF(current_setting('app.principal_id', true), '')`).
  `messages` y `actions` no llevan `principal_id`; se cubren por
  `EXISTS (SELECT 1 FROM companion.threads …)` sobre el hilo, que sí lo lleva.
- `usage_records.source` admite `'companion'` — se reemplaza el CHECK
  `ck_usage_source` (0079) por uno de tres valores.
- `partners.companion_monthly_token_cap bigint NOT NULL DEFAULT 500000` +
  `companion_cap_notes text`. **Defecto conservador a propósito**: 500k tokens/mes
  ≈ 300-500 turnos del Companion; es el orden de magnitud de un piloto y una
  pérdida acotada. Se sube por fila, como el del playground.
- `tenant_model_bindings_role_check` **se altera** para admitir `'companion'` —
  el CHECK fija la lista y tocar solo `MODEL_ROLES` en
  `db/models/model_profile.py` dejaría un rol que la base rechaza al escribir.
- `downgrade()` real: quita policies, tablas, esquema, columnas y restaura los
  dos CHECK a su forma anterior.

`principal_id` es **TEXT**, no UUID: `partner_memberships.user_id` es texto (los
tests usan `user_a_ab12cd34`), y `qa.runs.operator_id` ya sentó ese precedente en
la 0026.

### 3.2. Registro de runs durable — `api/companion_streaming.py`

```
POST …/runs   →  202 {run_id}                        (arranca y devuelve YA)
                 ├─ fila companion.runs (status=running)
                 └─ asyncio.Task  ──► grafo ──► publish(evento)
                                                   │
                          Redis Stream companion:run:{id}  (MAXLEN ~2000, TTL 24 h)
                                                   │
GET …/events?since_seq=N  ─ XRANGE  ───────────────┤   historial (REST, paginado)
GET …/stream?since_seq=N  ─ XRANGE + XREAD BLOCK ──┘   SSE en vivo, sin pérdida
```

- **El SSE es un lector puro del log.** Cualquier réplica sirve cualquier stream;
  la reanudación es exacta (filtro por `seq`), no *best-effort*.
- **`seq`** es un entero monótono por run, escrito como campo de la entrada. El
  escritor es único por run (una tarea), así que un contador en memoria basta y
  es determinista. El id de entrada de Redis se usa solo como cursor de `XREAD`.
- **Cancelación entre réplicas**: `DELETE …/runs/{id}` marca la fila y pone
  `companion:run:{id}:cancel`; el driver lo comprueba entre pasos y, si el run es
  local, además `task.cancel()`. Cerrar el `fetch` **no** cancela nada — eso es
  exactamente lo que el artículo de Ably dice que hay que construir.
- **Reaper de arranque + caducidad por el lado del lector.** En el `lifespan`,
  los `companion.runs` en `running` **más viejos que `companion_run_max_seconds`**
  pasan a `interrupted` y se les añade al log un `run.completed`. El corte NO es
  cero: un proceso que arranca no sabe qué runs son suyos y cuáles está
  ejecutando otra réplica ahora mismo, así que barrer todo mataría los turnos
  vivos en cada despliegue rodante. Lo que un proceso sí puede afirmar sin saber
  de quién es el run es que ninguno legítimo dura más que su propio techo. El
  hueco que deja (un huérfano de hace diez segundos) lo cubre el **lector**: el
  `terminal_check` del stream trata un `running` caducado como `interrupted`, así
  que el usuario ve el cierre sin esperar a que nadie reinicie nada.
- **Catálogo cerrado** (`COMPANION_EVENTS`) aplicado en `publish` — ver D2.

### 3.3. Grafo mínimo — `apps/worker/src/nexus_worker/runtime/companion/`

`entender → investigar → responder`. Sin herramientas (CO-02), sin escrituras,
sin HITL. Checkpointer Postgres siguiendo `core/qa_checkpointer.py` (se reutiliza
el mismo `AsyncPostgresSaver`, esquema `langgraph`; el `thread_id` del
checkpointer es el `companion.threads.id`, que solo alcanza su dueño por RLS).

- `state.py` — `CompanionState` (mensajes, fase, page_context, uso).
- `prompt.py` — prompt de sistema **estable** (prefijo cacheable) + el hueco de
  `page_context` como mensaje de sistema a mitad de conversación (C4).
  Sin instrucciones de auto-verificación (C5). Con disciplina de alcance,
  concisión y `<tone_preference>` al final, según la guía de Opus 5 (§24).
- `graph.py` — `StateGraph` con los tres nodos + el nodo `await_confirmation`
  **reservado y vacío** para CO-04 (C2), no cableado todavía.
- `llm.py` (del paquete companion) — la llamada en streaming, con
  `COMPANION_THINKING` explícito. Emite por `adispatch_custom_event`:
  `phase.changed`, `text.delta`, `reasoning.delta`, `cost.updated`,
  `context.updated`.

**Por qué eventos personalizados y no `on_chat_model_stream`**: el runtime no usa
modelos de LangChain, usa LiteLLM directamente (`runtime/llm.py`). El traductor
existente extrae texto de `on_chat_model_stream`, que en este stack **nunca se
dispara** — el playground de hoy pinta desde `ucm.final`. El Companion emite sus
deltas explícitamente y el traductor los pasa por el camino de `on_custom_event`,
que ya existe.

### 3.4. Streaming real en el proveedor — `runtime/llm.py`

`LiteLLMProvider` hoy solo tiene `acomplete` / `acomplete_with_tools`, ambos sin
streaming. Se añade `astream_complete`, que:

- llama a `litellm.acompletion(stream=True, stream_options={"include_usage": True})`;
- va cediendo `(kind, text)` con `kind ∈ {"text", "thinking"}`;
- al cerrar, pasa por **el mismo bloque de telemetría** que `_raw_complete`
  (`log`, `record_llm_call`, `record_llm_usage`, `record_generation`) — extraído
  a `_record_call()` y compartido por los dos caminos. El punto de estrangulamiento
  del consumo sigue siendo uno solo: si se duplicara, el gasto del Companion se
  perdería en silencio.

`InMemoryProvider` gana el método equivalente para que las pruebas no toquen red.

### 3.5. Endpoints — `api/console/companion.py`

```
POST   /console/companion/threads
GET    /console/companion/threads
PATCH  /console/companion/threads/{thread_id}
POST   /console/companion/threads/{thread_id}/runs   → 202 {run_id}
GET    /console/companion/runs/{run_id}/events?since_seq=N
GET    /console/companion/runs/{run_id}/stream?since_seq=N
DELETE /console/companion/runs/{run_id}
GET    /console/companion/budget
```

Reglas duras, sin excepción:

- **Ningún endpoint acepta `tenant_id` ni `partner_id`.** El cliente opcional del
  hilo se nombra con `client_ref` (`external_client_ref`) y se resuelve con
  `resolve_mapping` bajo el principal — 404 opaco si no es suyo.
- **Sin meta-tenant.** El sujeto es el `ConsolePrincipal`.
- Permiso nuevo **`companion:use`** en `core/console_auth.py` **y** en
  `apps/console/src/lib/permissions.ts` + el snapshot de
  `lib/__tests__/permissions.test.ts` (el test de deriva es lo que impide que se
  olvide un lado). Roles: `owner`, `admin`, `builder` — los mismos que
  `playground:run`, por el mismo motivo (gasta tokens y, desde CO-04, escribe).
- Limitador de ráfaga por miembro, como el playground: el tope mensual se mide
  sobre runs terminados.
- Arranque del run **fuera** de la transacción, igual que
  `console/playground.py`: la fila del hilo y la del run se comprometen antes de
  que la tarea empiece a publicar.

### 3.6. Proxy SSE en Next

`apps/console/src/app/api/companion/runs/[id]/stream/route.ts`, clon del de
playground, con **`export const maxDuration`** explícito (C1: el techo por
defecto de Vercel corta el stream a mitad y hoy nadie lo ha fijado). Más el
cliente de API tipado en `src/lib/backend/companion.ts` y su entrada en
`backendFor`.

> Acción de infra, **fuera de este código y anotada para el corte a AWS**:
> verificar que el *idle timeout* del ALB está por encima del heartbeat de 15 s
> (60 s por defecto vale, pero nadie lo ha comprobado).

### 3.7. Medición

- `SOURCE_COMPANION = "companion"` en `metering/collector.py` + `USAGE_SOURCES`;
  el consumidor lo acepta al validar y el desglose pasa a tres columnas.
- **Tope propio**: `partners.companion_monthly_token_cap`, sumado desde
  `companion.runs` (input+output) de los miembros del partner en el mes UTC —
  mismo razonamiento que CP-16 para el playground: la API cierra la fila al
  terminar el run, así que es síncrono y no depende del consumidor de metering.
  Al alcanzarlo, **429 con `Retry-After`** (la pausa con estado del §23.2 es
  CO-08, no CO-01; aquí se replica el comportamiento ya probado del playground).
- **Límite conocido y documentado**: `usage_records.tenant_id` es `NOT NULL`, así
  que un hilo del Companion **sin cliente** no deja fila en `usage_records`. El
  tope se mide en `companion.runs`, que siempre la tiene, y el desglose de
  `source='companion'` cubre los hilos que sí están atados a un cliente. Relajar
  `tenant_id` a NULL rompería la policy RLS de una tabla particionada de alta
  escritura; no se hace por comodidad de un panel.

### 3.8. Tests

| Suite | Qué prueba |
|---|---|
| `tests/unit/test_companion_streaming.py` | catálogo cerrado (filtra claves, rechaza eventos), `seq` monótono, reanudación con `since_seq` sin pérdida ni duplicados, ping en inactividad, evento terminal cierra el generador |
| `tests/unit/test_companion_graph.py` | el prompt de sistema no contiene `page_context`; `page_context` viaja como `role: system` dentro de `messages`; `thinking` explícito con `display: summarized`; ninguna instrucción de auto-verificación |
| `tests/unit/test_companion_context_window.py` | `context.updated.percent` sale de `input_tokens / model_profiles.max_context`, nunca de caracteres |
| `tests/isolation/test_companion_no_customer_bodies.py` | el guardián de D2 |
| `tests/isolation/test_companion_scope.py` | hilo de otro principal → 404 opaco; run de otro principal → 404; `client_ref` de otro partner → 404 idéntico al inexistente |
| `tests/isolation/test_console_scope.py` | (existente, parametrizado) las rutas nuevas entran solas y pasan sin excepciones |
| `tests/integration/test_companion_endpoints.py` | crear hilo → run → stream → matar la conexión → reconectar con `since_seq` → **cero eventos perdidos, cero duplicados**; reinicio simulado → `interrupted` visible |

---

## 4. Riesgos asumidos

1. **`thinking: {"type":"adaptive","display":"summarized"}` no se puede verificar
   contra el proveedor real desde aquí.** LiteLLM 1.83 lo declara como parámetro
   soportado y lo pasa verbatim al adaptador de Anthropic; el test unitario
   comprueba que sale en los kwargs. **Queda pendiente una prueba de humo real**
   antes de CO-03 — si `reasoning.delta` llega vacío, es esto.
2. **El run vive en la réplica que lo arrancó.** El log es durable y cualquier
   réplica lo *sirve*, pero el trabajo no migra: si esa réplica muere, el reaper
   lo marca `interrupted`. Ejecutar en el worker es el paso 3 del §13.2 y no toca
   ahora (el consumidor es secuencial y es un cuello conocido).
3. **`companion.actions` se crea sin usarse.** Es deuda deliberada de una
   migración: crearla en CO-04 exigiría repetir RLS y grants sobre el mismo
   esquema.
