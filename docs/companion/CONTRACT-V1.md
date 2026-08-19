# CONTRACT-V1 · El contrato congelado del Companion (Ola 1)

> **Ola 2 (desde 2026-08-19): este documento sigue vigente, pero
> [`CONTRACT-V2.md`](CONTRACT-V2.md) lo extiende.** Donde la v2 diga algo
> distinto, manda la v2. Todo lo que la v2 no toque se lee aquí.

> **Estado: CONGELADO** (v1.1, 2026-08-19) para toda la Fase 1 de la Ola 1 (CO-03, CO-04, CO-07).
>
> Derivado de §19 y §23 de
> `Auphere/nexus/research/2026-08-17-companion-agente-de-consola.md`, de §7,
> §8, §10 y §14 de la Parte I, y del código ya en `main`:
> [`PLAN-CO-01.md`](PLAN-CO-01.md) (`fff43d5`) y [`PLAN-CO-02.md`](PLAN-CO-02.md)
> (`63694ad`).
>
> **Este documento no se toca durante la Fase 1.** Un agente que necesite
> cambiarlo para, para y lo dice; el orquestador decide, actualiza aquí y avisa
> a los otros dos. Un cambio unilateral desincroniza CO-03 y CO-04, y entonces
> hay que rehacer uno de los dos.
>
> **Autoridad**: donde este documento y la investigación difieran, manda este
> documento — porque está contrastado contra el código que ya existe.

---

## 0. Por qué existe

CO-03 pinta eventos que CO-04 emite, y CO-07 escribe casos que dependen de
ambos. Los tres se construyen a la vez, en worktrees separados y sin hablar
entre ellos. Lo único que lo hace posible es que la superficie de contacto esté
cerrada **antes** de empezar: nombres de evento, claves de payload literales,
códigos HTTP, valores de `status` y la forma del objeto que la interfaz pinta.

Si el contrato se descubre sobre la marcha, CO-03 pinta `plan.steps[].title` y
CO-04 emite `plan.steps[].name`, y uno de los dos se rehace entero.

---

## 1. Restricciones heredadas — no negociables

Se listan porque un agente que las ignore produce un parche que no se puede
aplicar, y porque son la razón de varios nombres raros de este documento.

### 1.1. Nombres de propiedad prohibidos en respuestas

`tests/isolation/test_console_scope.py` recorre el OpenAPI de **todas** las
rutas `/console/*` y rechaza cualquier propiedad de respuesta que se llame:

```
content · text · body · message · messages · transcript · media_transcript
interactive_payload · tool_calls · takeover_context · outcome_feedback
notes · reason · payload · before_json · after_json · tenant_id · tenantid
```

Lista blanca global, y se queda **diminuta**: `{system_prompt, summary, detail}`.
Ampliarla ciega la comprobación en los otros ~60 endpoints de la consola.

Consecuencias directas en este contrato, todas deliberadas:

| Se quería llamar | Se llama | Motivo |
|---|---|---|
| `payload` (de la acción) | `preview` | `payload` está prohibido |
| `reason` (del rechazo) | `note` | `reason` está prohibido; `note` (singular) no |
| `notes` | `note` | `notes` (plural) está prohibido |
| `message` (de denegación) | `note` | `message` está prohibido |

`before` / `after` **sí** se pueden usar (lo prohibido es `before_json` /
`after_json`). `diff`, `impact`, `steps`, `slots`, `checks`, `preview`, `title`,
`expected`, `actual` están libres.

### 1.2. Ningún endpoint acepta `tenant_id` ni `partner_id`

Ni en ruta, ni en query, ni en cabecera, ni en cuerpo. El cliente se nombra
`client_ref` (`external_client_ref`) y lo resuelve el router bajo el principal.
Un `ref` de otro partner devuelve **el mismo 404 opaco** que uno inexistente.

### 1.3. El catálogo cerrado manda sobre el payload

`COMPANION_EVENTS` en `apps/api/src/nexus_api/api/companion_streaming.py` mapea
evento → claves permitidas. `publish()` **rechaza** un evento fuera del catálogo
y **elimina en silencio** cualquier clave no declarada.

Una clave que este contrato no declare **no llega al navegador**. No hay
mensaje de error: se cae. Por eso las claves de abajo son literales.

### 1.4. `phase.changed.label` es español hardcodeado

`PHASE_LABELS` en `apps/worker/src/nexus_worker/runtime/companion/state.py`
está en español y no pasa por i18n. **La interfaz no pinta `label`.** Pinta
`phase` traducido por su propia línea (`i18n/lanes/companion.ts`). `label` se
mantiene en el payload por compatibilidad con CO-01 y para los logs.

Esto vale para **todas** las etiquetas que vengan del backend en este contrato.
Regla general: el backend emite **identificadores estables**, la interfaz emite
**texto para humanos**. La única excepción es `citation.claim` y
`tool.call.started.label`, que ya existen desde CO-02 y salen del catálogo de
herramientas.

---

## 2. Eventos nuevos — payload literal

Van a `COMPANION_EVENTS` con exactamente estas claves. **Los escribe el Agente
B**; el Agente A los consume; el Agente C los observa en los evals.

### 2.1. `plan.proposed`

```python
"plan.proposed": frozenset({
    "plan_id", "steps", "risk", "reversible", "estimated_tokens"
})
```

```jsonc
{
  "plan_id": "3f2a…",              // uuid str, estable dentro del turno
  "steps": [
    {
      "index": 1,                   // 1-based, orden de ejecución
      "kind": "prompt",             // ActionKind del §3.1
      "tool": "console.propose_prompt",
      "title": "Ajustar el prompt de Clínica Boreal",  // redactado por el modelo
      "client_ref": "boreal",       // null si el paso no toca un cliente
      "reversible": true
    }
  ],
  "risk": "low",                    // low | medium | high
  "reversible": true,               // AND lógico de steps[].reversible
  "estimated_tokens": 18000         // entero, estimación del turno
}
```

- `steps` es **siempre** una lista, aunque tenga un elemento.
- `title` lo redacta el modelo; la interfaz lo pinta tal cual y **no lo
  traduce**. Es el único texto del plan que no está en el catálogo de
  herramientas.
- `risk` es un enum cerrado de tres valores. La interfaz mapea a token de color;
  ningún hex suelto.
- **`plan.proposed` no compromete a nada.** Un plan puede no llegar nunca a
  `hitl.requested` (el usuario cambia de idea, o la investigación lo invalida).

### 2.2. `intake.missing`

```python
"intake.missing": frozenset({"slots"})
```

```jsonc
{
  "slots": [
    {
      "key": "forbidden_behaviour",   // identificador estable, snake_case
      "label": "Qué NO debe hacer el agente",
      "why": "Es el campo que nadie escribe y el que causa los incidentes.",
      "examples": ["No dar precios por WhatsApp", "No agendar sin seña"],
      "required": true
    }
  ]
}
```

- `key` es **estable y cerrado por tipo de trabajo** (§7.1 de la
  investigación). La interfaz puede tener copy propio por `key`; si no lo
  tiene, cae a `label`/`why` del backend.
- `examples` es siempre lista (posiblemente vacía), nunca `null`.
- La interfaz lo pinta como **chips respondibles, no un formulario** (§14).
- Responder un slot **no** es un endpoint nuevo: es un `POST …/runs` normal en
  el mismo hilo, con el texto de la respuesta. El expediente es contexto del
  hilo, no estado de servidor. (CO-06 lo convierte en máquina de estados; aquí
  no.)

### 2.3. `hitl.requested`

```python
"hitl.requested": frozenset({
    "action_id", "kind", "title", "preview", "diff", "impact", "expires_at"
})
```

```jsonc
{
  "action_id": "9c1e…",             // uuid str, DETERMINISTA (§3.2)
  "kind": "prompt",                 // ActionKind del §3.1
  "title": "Publicar la v8 del agente de Clínica Boreal",
  "preview": { /* objeto libre, específico del kind — §3.4 */ },
  "diff": [                          // null si el kind no tiene diff textual
    {"op": "del", "line": 12, "before": "Responde siempre en inglés."},
    {"op": "add", "line": 12, "after": "Responde en el idioma del cliente."}
  ],
  "impact": [
    {"key": "channels_affected", "value": "2", "severity": "info"}
  ],
  "expires_at": "2026-08-18T14:33:00Z"   // ISO-8601 UTC, proposed_at + 15 min
}
```

- `diff[].op` ∈ `add | del | ctx`. `ctx` lleva `before` y `after` iguales.
- `impact[].severity` ∈ `info | warn | danger`.
- **`expires_at` es la única fuente de la cuenta atrás.** La interfaz no calcula
  15 minutos por su cuenta: si el backend cambia el plazo, la interfaz sigue.
- Cuando llega este evento la fase es `awaiting` y **el grafo está parado en
  `interrupt()`**. No llegan más eventos hasta el `resume`.
- **`aria-live="assertive"` es exclusivo de este evento** (§14). Todo lo demás
  del timeline es `polite`.

### 2.4. `hitl.resolved`

```python
"hitl.resolved": frozenset({"action_id", "decision", "by", "at", "note"})
```

```jsonc
{
  "action_id": "9c1e…",
  "decision": "confirm",            // confirm | edit | cancel
  "by": "user_a_ab12cd34",          // principal_id de quien decidió
  "at": "2026-08-18T14:21:07Z",
  "note": "Mejor sin tocar el horario."   // null si no la hubo
}
```

- **`note` vuelve al agente** (§23.1 de Managed Agents): con `edit` o `cancel`,
  el motivo entra en `messages` como texto del usuario para que el modelo
  ajuste el plan. No es solo un "no".
- `by` es el `principal_id`, no el correo. La interfaz ya sabe quién es el
  usuario en sesión; para otro miembro pinta el identificador. **Nunca correos
  completos de terceros en el chat** (§14).
- Este evento **sella la tarjeta** de `hitl.requested` en el timeline: la
  interfaz la busca por `action_id` y la marca, no añade una tarjeta nueva.
- Se emite en el **run nuevo** que abre `POST …/resume`, no en el run parado.
  Ver §4.3.

### 2.5. `verify.result`

```python
"verify.result": frozenset({"action_id", "checks", "ok"})
```

```jsonc
{
  "action_id": "9c1e…",
  "checks": [
    {"name": "active_version", "expected": "8", "actual": "8", "ok": true},
    {"name": "tools_enabled",  "expected": "3", "actual": "2", "ok": false}
  ],
  "ok": false                        // AND lógico de checks[].ok
}
```

- `name` es un **identificador estable en inglés**; la interfaz lo traduce.
- `expected` y `actual` son **cadenas siempre**, incluso para números. Evita que
  `8` y `"8"` se pinten distinto y que un float redondee.
- **Esto lo produce código determinista**, nunca el modelo ni un subagente
  (corrección C5). Es una relectura por la API y una comparación.
- Si `ok` es `false`, la interfaz lo pinta en rojo y **no** lo presenta como
  fallo del usuario: puede ser alucinación o fallo real de la plataforma.

### 2.6. `context.updated` — **ya existe, no se toca**

```python
"context.updated": frozenset({
    "input_tokens", "max_context", "percent", "compacted", "model"
})
```

Está en el catálogo desde CO-01 y CO-02 ya lo emite. Se lista aquí porque §19
lo daba como nuevo y porque la interfaz lo pinta.

- `percent` sale de `input_tokens / model_profiles.max_context`. **Nunca
  estimado por caracteres.**
- Si el modelo no está en `model_profiles`, **el evento no se emite**. La
  interfaz debe tratar "sin medidor" como estado válido — una barra al 0 % es
  peor que ninguna barra, porque la gente se la cree.
- `compacted` es booleano; en la Ola 1 es siempre `false` (la compactación es
  trabajo posterior). La interfaz lo lee igual.

### 2.7. Tabla de referencia — el catálogo completo tras la Ola 1

| Evento | Origen | Claves |
|---|---|---|
| `run.started` | CO-01 | `run_id, thread_id, started_at` |
| `run.completed` | CO-01/02 | `run_id, ended_at, status, error, unsupported` |
| `resume.gap` | CO-01 | `gap_kind, since_seq, available_from` |
| `ping` | CO-01 | `ts` |
| `phase.changed` | CO-01 | `phase, label` |
| `text.delta` | CO-01 | `message_id, text` |
| `reasoning.delta` | CO-01 | `message_id, text` |
| `cost.updated` | CO-01 | `input_tokens, output_tokens, model` |
| `context.updated` | CO-01 | `input_tokens, max_context, percent, compacted, model` |
| `budget.updated` | CO-01 | `used, cap, remaining, percent, exhausted, period, resets_at` |
| `tool.call.started` | CO-02 | `tool_call_id, name, label, args` |
| `tool.call.completed` | CO-02 | `tool_call_id, name, ok, latency_ms, error, citation_id` |
| `citation` | CO-02 | `citation_id, claim, source, fetched_at` |
| **`plan.proposed`** | **CO-04** | `plan_id, steps, risk, reversible, estimated_tokens` |
| **`intake.missing`** | **CO-04** | `slots` |
| **`hitl.requested`** | **CO-04** | `action_id, kind, title, preview, diff, impact, expires_at` |
| **`hitl.resolved`** | **CO-04** | `action_id, decision, by, at, note` |
| **`verify.result`** | **CO-04** | `action_id, checks, ok` |

Son **18 eventos**. Ni uno más en la Ola 1: `COMPANION_EVENTS` tiene que tener
exactamente estas 18 claves al terminar la Fase 2, y hay una comprobación de eso
en el paso 5 de la integración.

### 2.8. Enum cerrado de `phase`

`phase.changed.phase` ∈:

```
understand · investigate · intake · plan · awaiting · execute · verify · respond · done
```

`understand`, `investigate`, `awaiting`, `respond` y `done` existen ya en
`state.py`. **CO-04 añade `intake`, `plan`, `execute` y `verify`** y sus
entradas en `PHASE_LABELS`.

La píldora de §8.1 mapea así: *Entendiendo · Investigando · Preguntando ·
Planificando · Esperándote · Ejecutando · Verificando · Respondiendo · Listo*.
**La interfaz mantiene esa tabla en su línea de i18n**, no la lee del backend.

---

## 3. `companion.actions` — ciclo de vida

Tabla ya creada en la migración 0090 (deuda deliberada de CO-01). CO-04 la
escribe por primera vez. **La migración no cambia**: todas las columnas
necesarias existen.

### 3.1. `kind` — enum cerrado

Un valor por herramienta `propose_*`. Es lo que ata el catálogo de B, la línea
de i18n de A y el dataset de C.

| `kind` | Herramienta que lo propone | Endpoint que aplica | Reversible |
|---|---|---|---|
| `client` | `console.propose_client` | `POST /console/clients` | no |
| `prompt` | `console.propose_prompt` | `PUT /console/clients/{ref}/agent/draft` | sí |
| `policy` | `console.propose_policy` | `PUT /console/clients/{ref}/agent/settings` | sí |
| `tools` | `console.propose_tools` | `PUT /console/clients/{ref}/tools` | sí |
| `skills` | `console.propose_skills` | `PUT /console/clients/{ref}/skills` | sí |
| `publish` | `console.propose_publish` | `POST /console/clients/{ref}/agent/publish` | sí (rollback) |
| `channel_role` | `console.propose_channel_role` | `PATCH /console/clients/{ref}/channels/{id}` | sí |
| `usage_alerts` | `console.propose_usage_alerts` | `PUT /console/usage/alerts` | sí |
| `invite` | `console.propose_invite` | `POST /console/members/invitations` | sí (revocar) |

**Nueve `propose_*` y una sola `console.apply(action_id)`.** El endpoint exacto
de la columna 3 lo verifica el Agente B contra las rutas reales; si alguno no
coincide, **manda la ruta real** y B lo anota en su plan — no es un cambio de
contrato porque A y C no consumen esa columna.

**Prohibido, lista cerrada** (§6.5): borrar clientes, facturación / método de
pago / plan, rotar o revocar claves, mostrar una clave de API en el chat,
desactivar la revelación de IA, y cualquier cosa de otro partner. No hay
`kind` para ninguna de estas y no se añade uno.

### 3.2. `id` determinista

```
action_id = uuid5(NAMESPACE_COMPANION_ACTION, f"{run_id}:{step_index}")
```

Con `NAMESPACE_COMPANION_ACTION` una constante fija del módulo.

**Motivo (corrección C2)**: `interrupt()` reanuda **re-ejecutando el nodo desde
la primera línea**. Con `id` aleatorio y `INSERT`, cada confirmación duplicaría
la fila. La escritura es un **UPSERT** (`ON CONFLICT (id) DO UPDATE`), y por eso
la columna `id` se creó sin `default` en la 0090.

### 3.3. `status` — valores, transiciones y quién las mueve

```
                 ┌──────────────┐
                 │  proposed    │  ← nodo ANTERIOR al interrupt (grafo, UPSERT)
                 └──┬───┬───┬───┘
    resume:confirm  │   │   │  resume:cancel
        ┌───────────┘   │   └───────────┐
        ▼               ▼ resume:edit    ▼
  ┌───────────┐   ┌────────────┐   ┌───────────┐
  │ confirmed │   │ superseded │   │ cancelled │   (terminales salvo confirmed)
  └─────┬─────┘   └────────────┘   └───────────┘
        │ el grafo retoma
        ▼
  ┌───────────┐        ┌──────────┐
  │ applying  │───────►│ applied  │  ← verify.result emitido después
  └─────┬─────┘        └──────────┘
        │ fallo
        ▼
  ┌───────────┐
  │  failed   │
  └───────────┘

  proposed ──(15 min o hash cambiado)──► expired      (lectura perezosa / API)
```

| `status` | Quién lo escribe | Cuándo |
|---|---|---|
| `proposed` | **Grafo** (nodo anterior al `interrupt`) | Al persistir la acción, antes de emitir `hitl.requested` |
| `confirmed` | **API** (`POST …/resume`) | `decision=confirm`, tras revalidar caducidad y hash |
| `superseded` | **API** (`POST …/resume`) | `decision=edit`. La acción muere; el modelo replanifica |
| `cancelled` | **API** (`POST …/resume`) | `decision=cancel` |
| `expired` | **API** (lectura perezosa) | Al leerla pasados 15 min sin decidir, o si el hash cambió |
| `applying` | **Grafo** | Justo antes de que `console.apply` emita la petición |
| `applied` | **Grafo** | La petición devolvió 2xx |
| `failed` | **Grafo** | La petición falló, o `console.apply` lanzó |

Reglas duras:

1. **Solo `proposed` acepta una decisión.** Cualquier otra devuelve 409.
2. **Solo `confirmed` puede pasar a `applying`.** `console.apply` con una acción
   en cualquier otro estado **falla en el motor**, no en el prompt. Esta es la
   garantía C4 y tiene test propio.
3. `applied`, `failed`, `cancelled`, `superseded` y `expired` son **terminales**.
4. La caducidad es **perezosa**: no hay cron. Se calcula al leer
   (`proposed_at + 15 min < now()`) y se persiste en esa misma transacción. Es
   el mismo patrón que `_is_expired` para runs en `api/console/companion.py`.

### 3.4. `preview` por `kind`

Objeto libre (`dict[str, Any]`, sin propiedades declaradas — §1.1). La interfaz
lo pinta con un componente por `kind` y **cae a una vista genérica clave/valor
para un `kind` que no reconozca**. Eso es lo que permite que B añada un `kind`
sin romper a A.

Formas mínimas garantizadas, para que A tenga algo que pintar:

```jsonc
// kind: prompt | policy | tools | skills | channel_role | usage_alerts
{"client_ref": "boreal", "summary": "3 líneas cambiadas, 1 herramienta activada"}

// kind: publish
{"client_ref": "boreal", "from_version": 7, "to_version": 8,
 "evals_run": false, "evals_warning": "No se ejecutó ninguna evaluación."}

// kind: client
{"name": "Clínica Boreal", "vertical": "aesthetic-clinic", "timezone": "America/Caracas",
 "language": "es", "quota_used": 4, "quota_max": 10}

// kind: invite
{"email_masked": "m…a@facelad.com", "role": "builder"}
```

`summary` está en la lista blanca global, así que es seguro. `email_masked` va
**enmascarado en origen** (§14: nunca correos completos de terceros en el chat);
el enmascarado es la capa nombrada del Agente C.

### 3.5. `state_hash`

SHA-256 hexadecimal del estado leído del que depende la propuesta, calculado por
la herramienta `propose_*` en el momento de proponer.

- Qué entra en el hash **lo decide el Agente B por `kind`** y lo documenta en su
  plan. Regla: entra lo que, si cambia, invalida el diff que el humano vio.
  Para `publish`, la versión activa del agente. Para `prompt`, el borrador.
- Se recalcula en `resume:confirm` y **se compara**. Si difiere → **412** y la
  acción pasa a `expired`; el Companion vuelve a proponer con datos frescos.
- No hay CAS en los endpoints `/console/*` subyacentes: hoy no existe. **El CAS
  del Companion es este hash, y vive entero dentro de `resume`.**

---

## 4. `POST /console/companion/runs/{run_id}/resume`

### 4.1. Forma

```
POST /console/companion/runs/{run_id}/resume
Permiso: companion:use          (owner · admin · builder — el mismo que POST …/runs)
```

Nótese `{run_id}`, no `{id}`: `test_console_scope._fill()` ya sabe rellenar
`{run_id}` y añadir un nombre nuevo obligaría a tocar ese archivo.

**Cuerpo** — `CompanionResumeIn`:

```jsonc
{
  "action_id": "9c1e…",          // uuid, requerido
  "decision": "confirm",         // confirm | edit | cancel — requerido
  "note": "Sin tocar el horario." // opcional, máx 2000 chars
}
```

`note` en singular a propósito: `notes` está prohibido (§1.1).

**Respuesta 202** — `CompanionResumeOut`:

```jsonc
{
  "run_id": "7a…",               // el run NUEVO que continúa el hilo
  "thread_id": "1b…",
  "action_id": "9c1e…",
  "status": "confirmed"          // el status resultante de la acción
}
```

### 4.2. Códigos

| Código | Cuándo | `detail.code` |
|---|---|---|
| **202** | Aceptada; arranca el run de continuación | — |
| **401** | Sin principal | — |
| **403** | El rol no tiene `companion:use` | — |
| **404** | Run o acción inexistente, **o de otro principal**. Opaco e idéntico | — |
| **409** | La acción no está en `proposed`: ya decidida, aplicada o **caducada** | `action_already_decided` · `action_expired` |
| **412** | `state_hash` cambió desde que se propuso | `state_changed` |
| **422** | Cuerpo malformado, `decision` fuera del enum, `note` demasiado larga | — |
| **429** | Tope de runs simultáneos por miembro, o ráfaga | — |

Notas que cierran ambigüedades:

- **412 es exclusivamente la deriva de estado.** La caducidad por tiempo es 409
  con `action_expired`. Son causas distintas y la interfaz las pinta distinto
  ("alguien cambió esto mientras decidías" vs "se te pasó el plazo"), aunque la
  salida sea la misma: volver a proponer.
- **El 429 del tope mensual de tokens no aplica aquí.** §23.2 de Managed
  Agents: responder una confirmación **no arranca trabajo nuevo**, así que un
  hilo esperando decisión no se bloquea por presupuesto. El 429 de `resume` es
  solo por runs simultáneos. (La pausa con estado completa es CO-08.)
- **404 antes que 409.** Se comprueba la pertenencia primero. Un tercero no
  puede distinguir "no existe" de "existe y ya está aplicada".
- `decision=edit` y `decision=cancel` **también devuelven 202** y arrancan run:
  el modelo tiene que reaccionar al `note`.

### 4.3. Secuencia completa, evento a evento

```
run A  … phase.changed(plan) → plan.proposed
       … phase.changed(awaiting) → hitl.requested{action_id, expires_at}
       [ el grafo PARA en interrupt(). run A sigue en status=running ]

POST …/runs/{A}/resume {action_id, decision:"confirm"}
       → 202 {run_id: B}

run B    hitl.resolved{action_id, decision:"confirm", by, at, note:null}
       … phase.changed(execute) → tool.call.started(console.apply) → …completed
       … phase.changed(verify)  → verify.result{ok:true}
       … phase.changed(respond) → text.delta …
       … run.completed{status:"completed", unsupported:false}
       [ y run A pasa a status=completed ]
```

- **`hitl.resolved` se emite en el run B**, el primero de sus eventos. El run A
  ya no publica nada: está parado.
- **La interfaz tiene que seguir el run B.** Al recibir el 202, abre el stream
  del `run_id` devuelto. El hilo es continuo para el usuario; los runs no.
- **El timeline del cajón es del hilo, no del run.** Al recargar, la interfaz
  concatena los `…/runs/{id}/events` de los runs del hilo por orden y deduplica
  por `(run_id, seq)`.

---

## 5. `CompanionActionOut` — lo que consume la interfaz

Modelo Pydantic en `api/console/schemas_companion.py`. Es lo que devuelve el
endpoint de lectura **y** lo que la interfaz reconstruye desde `hitl.requested`.

```python
class CompanionActionOut(BaseModel):
    action_id: uuid.UUID
    thread_id: uuid.UUID
    run_id: uuid.UUID | None
    kind: str                       # ActionKind — §3.1
    title: str
    preview: dict[str, Any]         # objeto libre — §3.4
    diff: list[dict[str, Any]] | None
    impact: list[dict[str, Any]]
    risk: str                       # low | medium | high
    reversible: bool
    status: str                     # §3.3
    state_hash: str
    proposed_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    decided_by: str | None          # principal_id
    applied_at: datetime | None
    ok: bool | None                 # resultado de la verificación; null si no corrió
```

**Ninguna propiedad se llama** `payload`, `notes`, `reason`, `message`,
`content`, `text`, `body` ni `tool_calls`. `diff`, `impact` y `preview` son
objetos/listas **sin propiedades declaradas**, así que el recorrido del OpenAPI
no encuentra nada dentro. Es la misma forma honesta que `CompanionEventOut`.

**Correspondencia con `hitl.requested`**: el evento lleva el subconjunto
`{action_id, kind, title, preview, diff, impact, expires_at}`. Todo lo demás
sale del endpoint de lectura o del estado que la interfaz ya tiene.
`risk` y `reversible` los da `plan.proposed`, que siempre precede.

### 5.1. Endpoint de lectura

```
GET /console/companion/actions/{action_id}   → 200 CompanionActionOut | 404
```

Existe para el estado *parcial* de §14: recargar con una confirmación pendiente
tiene que pintar la tarjeta sin depender de que el log de Redis siga vivo.
Aplica la caducidad perezosa (§3.3) al leer.

### 5.2. Listado de runs de un hilo — **requerido** (añadido en v1.1)

```
GET /console/companion/threads/{thread_id}/runs   → 200 CompanionThreadRunsOut | 404
```

```python
class CompanionRunSummaryOut(BaseModel):
    run_id: uuid.UUID
    status: str                     # RUN_STATUSES de db/models/companion.py
    started_at: datetime
    ended_at: datetime | None

class CompanionThreadRunsOut(BaseModel):
    thread_id: uuid.UUID
    runs: list[CompanionRunSummaryOut]   # ascendente por started_at
```

**Por qué existe** (lo levantó el Agente A al cerrar CO-03, y es un hueco mío):
§4.3 dice que *el timeline del cajón es del hilo, no del run*, y que la interfaz
concatena los `…/runs/{id}/events` de los runs del hilo. Pero sin este endpoint
**el navegador no puede enumerar los runs de un hilo**. La interfaz tendría que
llevar un índice en `localStorage`, y entonces el requisito de §14 de que la URL
(`?companion=<thread>`) sea **compartible dentro del equipo** se rompe: quien
abre el enlace en otra máquina ve un hilo vacío.

Un índice local no es un fallo de la interfaz, es la ausencia del dato en el
servidor. Se añade.

- Orden **ascendente** por `started_at`. La interfaz concatena en ese orden y
  deduplica por `(run_id, seq)`.
- Sin paginación en la Ola 1. Un hilo con cientos de runs es problema de CO-06.
- 404 opaco si el hilo no es del principal, idéntico al inexistente.
- `localStorage` deja de ser la fuente del índice y pasa a ser, como mucho,
  caché.

---

## 6. La política de permiso es un dato

De §23.1. Cada `ToolSpec` gana dos campos:

```python
tool_class: Literal["read", "propose", "mutates"]
permission_policy: Literal["always_allow", "always_ask"]
```

Invariantes, con test:

1. `tool_class == "mutates"` ⟹ `permission_policy == "always_ask"`. Un
   `mutates` con `always_allow` es **imposible por construcción**.
2. `tool_class == "read"` ⟹ `always_allow`. Las 18 de CO-02 se marcan así.
3. `console.apply` es la **única** `mutates` del catálogo. Cualquier otra
   herramienta que escriba rompe CI. Esta es la garantía **C4**.
4. El motor lee la clase; **el prompt no decide nada de esto**.

`deny_message` de Managed Agents se implementa como el campo `note` de
`hitl.resolved` (§2.4): el motivo del rechazo vuelve al modelo.

---

## 7. Garantías con test — quién prueba qué

| Garantía | Qué afirma | Dueño |
|---|---|---|
| **C4** | Una `mutates` sin registro de confirmación en el mismo hilo **rompe CI**. `console.apply` con acción no `confirmed` falla en el motor | B |
| **C5 (secreto)** | Una clave de API **nunca** aparece en el transcripto, ni en `text.delta`, ni en `preview`, ni en `citation` | B |
| **C5 (verificación)** | `verify.result` lo produce código determinista. Ni un subagente, ni una instrucción de "revisa tu trabajo" en ningún prompt | B |
| **C6** | El Companion no puede escalar su propio permiso ni invitar por encima del rol del llamante | B |
| **C2** | El nodo del `interrupt()` no hace nada más; `action_id` determinista + UPSERT; ningún `try/except` genérico alrededor de `interrupt()` | B |
| **C1** | `client_ref` de otro partner → 404 **idéntico** al inexistente | B (ya existe de CO-02) |
| **R1** | `unsupported` < 2 % sobre el dataset; alarma si sube | C |
| **R2** | Petición ambigua ⟹ pregunta, nunca "el más probable" | C |
| Catálogo | `COMPANION_EVENTS` contiene **exactamente** los 18 eventos del §2.7 | Fase 2 (orquestador) |

---

## 8. Lo que este contrato NO cierra

Por si un agente lo busca y no lo encuentra:

- **CO-05** (probar antes de publicar: `companion.run_playground_turn`).
- **CO-06** (expediente como máquina de estados persistida; aquí el intake es
  contexto del hilo).
- **CO-08** (pausa con estado del §23.2, límites duros, escalado a soporte).
- `task_budget` de Anthropic (§23.3, beta) y `defer_loading` / `tool_addition`
  (§23.4, beta). La Ola 1 usa el mecanismo ya probado en CO-02: nota de sistema
  al final de `messages` al cruzar umbrales, y tope duro por detrás.
- La compactación de contexto. `context.updated.compacted` es `false` siempre.

---

## 9. Zonas de archivo — recordatorio operativo

Disjuntas por construcción. Un agente que necesite tocar fuera de su zona
**para y pregunta**.

| | Zona |
|---|---|
| **A · CO-03** | `apps/console/src/components/companion/**`, `apps/console/src/i18n/lanes/companion.ts`, `apps/console/src/lib/backend/companion.ts`, `apps/console/e2e/companion.spec.ts`, el montaje en `apps/console/src/app/(console)/layout.tsx`, `packages/ui/**` solo si falta una primitiva |
| **B · CO-04** | `apps/api/src/nexus_api/api/console/companion.py`, `api/companion_streaming.py`, `api/console/schemas_companion.py`, `companion/tools/**`, `apps/worker/src/nexus_worker/runtime/companion/**`, `core/console_auth.py` (**solo** la propiedad `actor`, §10), y sus tests `test_companion_action*` |
| **C · CO-07** | `apps/api/src/nexus_api/services/evals/**`, `apps/api/tests/evals/companion/**`, el helper de enmascarado de PII, el gate de CI |

---

## 10. Reconciliaciones asignadas a la Fase 2

Cosas que se sabe que hay que hacer y que **ningún agente hace**, porque caen
fuera de las tres zonas. Se listan aquí para que nadie las improvise.

1. **El actor de auditoría.** `ConsolePrincipal.actor` devuelve hoy
   `console:{email}`. Para las escrituras del Companion tiene que ser
   `companion:{user_id}`. B añade la rama en `core/console_auth.py` (es la única
   línea que se le concede fuera de su zona, porque sin ella no puede probar
   C4). **El orquestador** añade en Fase 2 la rama de `_human_actor` en
   `api/console/audit.py` para que la página de auditoría lo pinte como
   *Companion*; la persona sigue siendo recuperable por
   `companion.actions.decided_by`.
2. **Activar los `xfail` del Agente C** que dependían del camino de escritura.
3. **`companion:use` en el frontend.** Ya existe desde CO-01 en
   `lib/permissions.ts`; A lo consume, no lo añade.
4. **Comprobar que `COMPANION_EVENTS` tiene exactamente 18 claves** (§2.7).

---

## 11. Bitácora de cambios del contrato

| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-08-18 | v1 — congelado para la Fase 1 de la Ola 1 | — |
| 2026-08-19 | **v1.1** — `GET /console/companion/threads/{thread_id}/runs` pasa de opcional a **requerido** (§5.2) | Sin él, el timeline no puede ser del hilo y la URL compartible de §14 no funciona en otra máquina. Lo levantó el Agente A al cerrar CO-03; decisión del orquestador, notificada a A y B |
| 2026-08-19 | La Ola 2 se rige por [`CONTRACT-V2.md`](CONTRACT-V2.md) v2.0, que extiende este documento | Ver §0 de la v2 |
