# CONTRACT-V2 · El contrato congelado del Companion (Ola 2)

> **Estado: CONGELADO** (v2.0, 2026-08-19) para toda la Fase 1 de la Ola 2
> (CO-06, CO-08 y la interfaz).
>
> **Este documento extiende [`CONTRACT-V1.md`](CONTRACT-V1.md) (v1.1); no lo
> sustituye.** Todo lo que la v1.1 congeló sigue en pie palabra por palabra. Aquí
> solo está lo que **cambia** o lo que **se añade**. Si algo no aparece en este
> documento, manda la v1.1.
>
> **Autoridad**: v2 > v1.1 > investigación. Con una excepción heredada: la
> columna de endpoints de aplicación del §3.1 de la v1.1, donde manda el código
> (`APPLY_ROUTES` en `companion/tools/proposals.py`).
>
> **No se toca durante la Fase 1.** Un agente que necesite cambiarlo, para y lo
> dice; el orquestador decide, actualiza aquí y avisa a los otros dos. Es
> exactamente lo que pasó con la v1.1 y funcionó.

---

## 0. Por qué existe

La Ola 1 pudo repartirse porque las tres zonas eran disjuntas *a nivel de
archivo*. La Ola 2 acopla más: los tres agentes tienen algo que decir sobre el
grafo y sobre el catálogo de eventos. Sin cerrar antes qué evento nuevo existe,
qué claves lleva y **quién lo escribe**, dos agentes editan
`companion_streaming.py` en worktrees distintos y el parche de uno pisa al otro.

Este documento cierra cinco cosas y reparte una: el catálogo de eventos tiene
**un solo dueño en la Ola 2**, y es el Agente E (§7).

---

## 1. Lo que la Ola 1 dejó abierto y este contrato NO cierra

Se lista para que nadie lo dé por hecho:

1. **El camino de escritura no se ha ejecutado de extremo a extremo contra el
   proveedor.** No hay `ANTHROPIC_API_KEY` en este entorno (verificado:
   `scripts/companion_thinking_smoke.py` sale con 2). La Ola 2 se construye
   igual; la verificación con clave real sigue pendiente y se arrastra al log de
   cierre. **Ningún agente debe asumir que ese camino está probado.**
2. La **prueba de humo del pensamiento** sigue sin correr con clave real.
3. Los **dos `xfail` de `live`** siguen sin activarse: necesitan modelo.
4. Los cabos 4 y 5 de la Ola 1 (`inert` en los diálogos de Base UI, contraste de
   `--color-status-*` en tema oscuro) son **deuda preexistente de toda la
   consola**. Fuera del alcance de la Ola 2.

---

## 2. `phase.changed` — la lista completa y final

El §7 de la investigación tiene ocho fases de negocio; el enum de la v1.1 tiene
nueve identificadores, dos de los cuales (`respond`, `done`) son de ejecución y
no de negocio. La correspondencia es exacta salvo por una que faltaba.

| §7 (negocio) | Identificador | Estado |
|---|---|---|
| 1 · entender | `understand` | ya existe |
| 2 · investigar | `investigate` | ya existe |
| 3 · expediente | `intake` | ya existe (CO-04) |
| 4 · planificar | `plan` | ya existe (CO-04) |
| 5 · confirmar | `awaiting` | ya existe (CO-04) |
| 6 · ejecutar | `execute` | ya existe (CO-04) |
| 7 · verificar | `verify` | ya existe (CO-04) |
| 8 · publicar | **`publish`** | **NUEVO — v2** |
| — | `respond` | ya existe (ejecución) |
| — | `done` | ya existe (ejecución) |

**Enum final y cerrado — diez valores:**

```
understand · investigate · intake · plan · awaiting · execute · verify · publish · respond · done
```

- **`publish` no es "aplicar un `kind: publish`".** Aplicar una publicación
  confirmada ocurre en `execute`, como cualquier otra escritura. `publish` es la
  fase del paso 8 del §7: el trabajo en curso *desemboca* en una publicación, la
  verificación del paso 7 salió verde, y el Companion prepara la **segunda
  confirmación** con el diff contra la versión activa delante (regla R5).
  Un turno que solo cambia un prompt nunca entra en `publish`.
- `PHASE_LABELS[publish] = "Publicando"`. Lo escribe **D** en
  `runtime/companion/state.py`. Sigue en español y sigue sin pasar por i18n:
  **la interfaz no pinta `label`** (§1.4 de la v1.1).
- La línea de i18n de la interfaz añade `publish` → *Publicando* / *Publishing*.
  Lo escribe **F**.
- El payload de `phase.changed` **no cambia**: sigue siendo `{phase, label}`. No
  hay edición del catálogo por esto.

---

## 3. El expediente — `intake.missing` cerrado

### 3.1. Payload — **cambia**

```python
"intake.missing": frozenset({"slots", "work_kind"})
```

`work_kind` es **nuevo en v2**. Existe porque la interfaz titula el grupo de
chips ("Para crear el cliente me faltan…") y sin él tendría que deducir el tipo
de trabajo parseando prefijos de `key`, que es adivinar.

```jsonc
{
  "work_kind": "create_client",
  "slots": [
    {
      "key": "forbidden_behaviour",
      "label": "Qué NO debe hacer el agente",
      "why": "Es el campo que nadie escribe y el que causa los incidentes.",
      "examples": ["No dar precios por WhatsApp", "No agendar sin seña"],
      "required": true
    }
  ]
}
```

Todo lo demás de la v1.1 §2.2 sigue igual: `examples` siempre lista (posiblemente
vacía, nunca `null`); chips, no formulario; responder un slot es un `POST …/runs`
normal en el mismo hilo.

### 3.2. `work_kind` — enum cerrado

```
create_client · connect_whatsapp · change_prompt · enable_connector · publish
```

Cinco valores, uno por fila de la tabla del §7.1 de la investigación. Un tipo de
trabajo que no esté aquí **no emite `intake.missing`**: pasa directo a planificar.
Añadir uno es cambio de contrato.

### 3.3. Campos obligatorios por tipo de trabajo — catálogo cerrado de `key`

Es lo que el §7.1 pide y lo que hace que la interfaz pueda tener copy propio por
`key`. **Los `key` son estables**; el `label` y el `why` del backend son la caída
por defecto cuando la interfaz no tiene copy.

| `work_kind` | `key` obligatorios |
|---|---|
| `create_client` | `name` · `vertical` · `timezone` · `language` · **`forbidden_behaviour`** |
| `connect_whatsapp` | `phone_number` · `number_owner` · `channel_role` ¹ |
| `change_prompt` | `failing_behaviour` · `real_example` |
| `enable_connector` | `connector_consent` |
| `publish` | `ai_disclosure_decision` |

¹ `channel_role` es obligatorio **solo si el cliente ya tiene otro canal activo**.
Es la regla de negocio del multicanal: con más de un canal activo y ningún rol
asignado, el envío se rechaza. Etiquetar tiene que ocurrir **antes** de conectar
el segundo número, no después.

**`forbidden_behaviour` es obligatorio a propósito y no se puede saltar.** Es el
campo que nadie escribe y el que causa los incidentes; preguntarlo siempre es
barato. Un `create_client` que llega a `plan` sin él es un fallo del motor, y
tiene test propio (§9).

**Deducibles, nunca preguntados**: plantilla, prompt inicial, herramientas del
vertical, el resto del Embedded Signup, el resto del diff, la configuración del
conector. Preguntar un deducible es ruido y erosiona la disposición del usuario
a contestar lo que sí importa.

### 3.4. El expediente es estado, no solo contexto

Cambio respecto a la v1.1 §2.2 ("el expediente es contexto del hilo, no estado de
servidor"). **En la Ola 2 lo es**: CO-06 lo persiste para que sobreviva a una
recarga y a un proceso distinto.

- La forma exacta de la persistencia **la decide D** y la documenta en
  `PLAN-CO-06.md`. Regla: un slot respondido no se vuelve a preguntar aunque el
  turno lo sirva otro proceso.
- **No aparece en ningún endpoint nuevo.** La interfaz reconstruye el expediente
  del timeline (`intake.missing` + los mensajes del usuario que lo responden).
  Un endpoint de lectura del expediente sería superficie nueva de la consola y
  la Ola 2 no la abre.

---

## 4. Soporte — `support.request_help` y `support.request_capability`

De §25.1 y §25.2. **El Companion nunca cierra con un "no"; cierra con un camino.**

### 4.1. Son herramientas `propose`, no atajos

Se declaran en el catálogo con `tool_class="propose"`, `permission_policy="always_ask"`
y su `kind`. **No escriben.** Escribe `console.apply`, que sigue siendo la
**única** `mutates` del catálogo (garantía C4, intacta).

| Herramienta | `kind` nuevo | Endpoint de aplicación |
|---|---|---|
| `support.request_help` | `support_help` | `POST /console/support/tickets` |
| `support.request_capability` | `support_capability` | `POST /console/support/tickets` |

El enum `kind` del §3.1 de la v1.1 pasa de **nueve a once**. La lista de
prohibidos del §6.5 **no cambia**: no hay `kind` para borrar clientes, tocar
facturación, rotar claves ni desactivar la revelación de IA, y no se añade uno.

### 4.2. `preview` del ticket

```jsonc
// kind: support_help | support_capability
{
  "category": "help",                  // help | capability — espeja el kind
  "topic": "connector.shopify",        // slug estable — es lo que agrega §25.2
  "client_ref": "boreal",              // null si el ticket no es de un cliente
  "need": "Sincronizar pedidos de Shopify para que el agente responda por el envío",
  "checked": [                          // lo que el Companion YA leyó, por etiqueta
    "Catálogo de conectores (14 disponibles, sin Shopify)",
    "Herramientas activas del cliente",
    "Plan del partner"
  ],
  "alternative": null,                  // null si no hay camino puente
  "bridge": false                       // true ⟹ §25.4: se etiqueta Y se abre el ticket igual
}
```

- `need` lo redacta el modelo. `checked` sale de las **etiquetas del catálogo de
  herramientas** de las lecturas de este turno, no de texto libre: es la misma
  procedencia que sostiene R1. Un ticket sin `checked` es un ticket sin
  expediente, y eso es lo que §25.1 existe para evitar.
- `topic` es un **slug estable**, no prosa. Es la clave de agregación: sin él,
  *"siete partners han pedido Shopify este trimestre"* no se puede consultar.
  Espacio de nombres por familia: `connector.*`, `channel.*`, `capability.*`,
  `platform.*`, `quota.*`, `permission.*`. Un `topic` que no encaje en una
  familia va como `other.<slug>`; E documenta el vocabulario inicial en su plan.
- `bridge: true` es el §25.4: la solución puente **no sustituye** al ticket. Un
  puente que nadie registra es deuda invisible.

### 4.3. Dónde aterriza

No hay sistema de tickets nuevo — §25.1 lo dice explícitamente. Al aplicar:

1. Una fila de `console_notifications` para el partner, con `kind` nuevo
   `support.ticket_opened` (o `support.capability_requested`), severidad `info`,
   `external_client_ref` cuando lo haya, y el `payload` con `{ticket_ref, topic,
   category}`. El `dedupe_key` es `partner:<id>:support:<ticket_ref>`.
2. **Alerta interna** por el camino que ya existe para severidad ≥ `warning`
   (correo a Auphere) más una línea estructurada de log con `topic` y `partner_id`.
   E elige el mecanismo exacto y lo documenta.
3. Una fila de `audit_log` como cualquier escritura del Companion, con actor
   `companion:<user_id>`.

**Nada del ticket lleva cuerpo de mensaje de un cliente final.** `need` y
`checked` los redacta el Companion; `topic` es un slug. C8 intacta.

### 4.4. El identificador y la expectativa

Sin identificador el ticket es un agujero negro (§25.1).

- `ticket_ref` tiene la forma **`AU-<n>`**, con `n` de una secuencia de Postgres
  (`console_support_ticket_seq`, migración de E). Monótono, corto, decible por
  teléfono. No es un uuid: un uuid en un correo de soporte no lo repite nadie.
- La **expectativa de respuesta** es un identificador estable, no prosa del
  modelo: `sla ∈ business_hours | next_business_day | best_effort`. La interfaz
  lo traduce a la frase que ve el usuario. El backend **no** emite la frase.
  Regla general del §1.4 de la v1.1: el backend emite identificadores estables,
  la interfaz emite texto para humanos.

### 4.5. Evento nuevo — `support.ticket`

Hace falta porque el identificador nace **al aplicar**, y sin evento la interfaz
no tiene de dónde sacarlo para pintar la tarjeta.

```python
"support.ticket": frozenset({"action_id", "ticket_ref", "category", "topic", "sla"})
```

```jsonc
{
  "action_id": "9c1e…",
  "ticket_ref": "AU-142",
  "category": "help",              // help | capability
  "topic": "connector.shopify",
  "sla": "business_hours"          // business_hours | next_business_day | best_effort
}
```

- Se emite en la fase `execute`, **después** de que `console.apply` devuelva 2xx
  y **antes** de `verify.result`.
- La interfaz lo ata a la tarjeta de `hitl.requested` por `action_id`, igual que
  hace con `hitl.resolved`. No añade una tarjeta suelta.

---

## 5. El documento de capacidades y límites (§25.3)

Para que el §4 funcione, el Companion tiene que saber dónde están las paredes. Si
no, alucina capacidades y manda al partner contra un muro.

### 5.1. Regla dura

> **Si algo no está en el catálogo leído en este turno, no existe.**

Es R1 aplicada a las capacidades, y tiene una consecuencia de diseño que no es
negociable: **el documento se lee con una herramienta, no se hornea en el
prompt.** Un límite en el prompt de sistema no deja cita, no deja
`tool.call.started` y no se puede versionar sin invalidar el caché. Leerlo deja
las tres cosas.

- Herramienta `console.get_capabilities`, `tool_class="read"`,
  `permission_policy="always_allow"`, como las 18 de CO-02.
- Se sirve por `GET /console/capabilities`, **no** por lectura de fichero: así
  entra por la misma tubería que el resto (autorización, recorte por `max_chars`,
  cita, recorrido de OpenAPI) y mañana la consola puede tener su página sin
  inventar un segundo camino.

### 5.2. Esquema

Fuente en el repositorio (`docs/companion/capabilities.yaml`), servida parseada.
**La mantenemos nosotros; no se infiere.** Una capacidad inventada es una promesa
rota con el cliente del partner.

```yaml
version: "2026-08-19"        # fecha ISO, monótona. Cambia con cada edición.
entries:
  - key: connector.shopify   # slug estable — el MISMO espacio de nombres que topic (§4.2)
    family: connector        # connector | channel | capability | platform
    status: absent           # available | planned | absent | out_of_scope | retired
    label: "Shopify"
    note: "No hay conector nativo. La sincronización de pedidos requiere desarrollo."
    eta: null                # solo si status=planned. Texto corto, nunca una fecha inventada
    replaced_by: []          # solo si status=retired
```

Cinco estados y qué significan para el Companion:

| `status` | El Companion puede… |
|---|---|
| `available` | usarlo y afirmarlo |
| `planned` | decir que llega, **con** `eta`, y ofrecer `request_capability` para que cuente |
| `absent` | decir que no está y ofrecer `request_help` / `request_capability` |
| `out_of_scope` | decir que no está **y por qué**, y **no** ofrecer ticket de capacidad |
| `retired` | decir que se retiró y **redirigir a `replaced_by`** |

Ejemplos que tienen que estar sembrados desde el primer día, porque son los que
el modelo alucinaría: TikTok (`out_of_scope`, C7), el widget embebido
(`retired`, `replaced_by: [api, mcp]` — CP-20), evals en consola y Stripe
(`planned`).

### 5.3. Forma de la respuesta

```python
class CapabilityOut(BaseModel):
    key: str
    family: str
    status: str
    label: str
    note: str | None          # 'note' singular: 'notes' y 'reason' están prohibidos (§1.1 v1.1)
    eta: str | None
    replaced_by: list[str]

class CapabilitiesOut(BaseModel):
    version: str
    entries: list[CapabilityOut]
```

`note` es la única propiedad de texto y está en la **lista blanca global** del
recorrido de OpenAPI (`{system_prompt, summary, detail}` más `note` singular, que
ya usa `hitl.resolved`). Ninguna propiedad se llama `text`, `body`, `content`,
`message`, `notes`, `reason` ni `payload`.

**El endpoint no acepta `tenant_id` ni `partner_id`**, ni ninguna otra cosa: no
tiene parámetros. El documento es el mismo para todos los partners.

---

## 6. El presupuesto **pausa**, no mata (§23.2)

**El 429 del tope mensual de tokens de CO-01 se retira.** Un 429 que tira el
trabajo a la basura es la peor versión de un tope.

### 6.1. La pausa es derivada, no un estado nuevo del hilo

Un hilo está en pausa **si y solo si** su partner está por encima del tope
(`used >= cap`). No hay columna de estado en el hilo, no hay que despausar nada a
mano, y subir el tope reanuda todos los hilos del partner a la vez — que es
exactamente lo que §23.2 describe ("solo se reanuda cambiando o quitando el
presupuesto"). Un estado persistido sería una segunda fuente de verdad que se
puede desincronizar de la primera.

### 6.2. Qué acepta y qué no un hilo en pausa

| Petición | Antes (CO-01) | **Ahora (v2)** |
|---|---|---|
| `POST …/threads/{id}/runs` (trabajo nuevo) | 429 | **409** · `detail.code = "budget_paused"` |
| `POST …/runs/{id}/resume` (cierra trabajo empezado) | 202 | **202, sin cambios** |
| `GET` de cualquier lectura | 200 | **200, sin cambios** |

- La distinción es la del §23.2: *cualquier cosa que arranque trabajo nuevo se
  rechaza; los eventos de cierre pasan*. Confirmar una acción propuesta antes de
  la pausa **no arranca trabajo nuevo**, y dejarla morir por un tope sería tirar
  a la basura justo el trabajo que ya se pagó.
- El cuerpo del 409 lleva la instantánea del presupuesto para que la interfaz
  pinte la explicación sin una segunda petición: `{code, used, cap, period,
  resets_at}`.
- **409 y no 429 a propósito.** 429 significa *vuelve a intentarlo*, y aquí
  reintentar no sirve de nada: no pasa el tiempo, pasa que alguien sube el tope.
  Un `Retry-After` sería mentira.

### 6.3. Cuando el tope se cruza a mitad de turno

La comprobación es **una puerta antes de cada llamada al modelo**, no un cálculo
posterior. La llamada que cruza el tope se completa, así que el total final puede
pasarse por como mucho una llamada. Se documenta como límite del trabajo nuevo,
no como corte exacto.

Al tripar la puerta, el run **termina limpio y conserva todo**:

1. Se emite `budget.paused` (§6.4).
2. Se emite `run.completed` con `status: "paused"` — **valor nuevo** de
   `RUN_STATUSES`, y por tanto migración (E, §8).
3. La respuesta parcial, los tokens y la historia **se persisten**. Un hilo
   pausado que pierde la historia no es una pausa, es un fallo con otro nombre.

`paused` es terminal para el run y **no** cuenta en el tope de concurrencia. No
se confunde con el run aparcado del HITL (que sigue en `running` y no publica
`run.completed`, PLAN-CO-04 D4): son dos esperas distintas y se pintan distinto.

### 6.4. Evento nuevo — `budget.paused`

```python
"budget.paused": frozenset({"used", "cap", "period", "resets_at", "scope"})
```

```jsonc
{
  "used": 2000000,
  "cap": 2000000,
  "period": "2026-08",
  "resets_at": "2026-09-01T00:00:00Z",
  "scope": "partner"               // partner — único valor hoy; el enum queda abierto
}
```

`budget.updated` **no se toca**: sigue emitiéndose y sigue llevando `exhausted`.
`budget.paused` es el evento del *corte*, y existe separado porque la interfaz
tiene que distinguir "vas por el 98 %" de "aquí se paró el trabajo".

### 6.5. Lo que la interfaz pinta

Estado de tope alcanzado, **no un error**: el hilo sigue ahí, la historia sigue
ahí, la caja de escribir se deshabilita con la explicación de por qué y qué
desbloquea (subir el tope), y la tarjeta de confirmación pendiente —si la
había— **sigue siendo respondible**. Rojo de error para algo que se resuelve
subiendo un número enseña a temer la herramienta.

---

## 7. `verify.result` — extendido para la prueba en playground

Preparado en v2 para que **F pueda construir el panel** contra el contrato; lo
**emite CO-05, que es Fase 2 del orquestador**, no un agente de la Fase 1.

```python
"verify.result": frozenset({"action_id", "checks", "ok", "trial"})
```

`trial` es nuevo; `action_id`, `checks` y `ok` no cambian.

```jsonc
{
  "action_id": "9c1e…",
  "checks": [ /* … igual que v1.1 §2.5 … */ ],
  "ok": true,
  "trial": {
    "ran": true,
    "thread_id": "4d2b…",           // el hilo de playground usado; la interfaz enlaza a él
    "ok": true,
    "tokens": 4210,
    "turns": [
      {
        "index": 1,
        "probe": "¿Cuánto cuesta el bótox?",     // lo escribe el COMPANION
        "ok": true,
        "latency_ms": 1840,
        "checks": [{"name": "no_price_quoted", "expected": "true", "actual": "true", "ok": true}]
      }
    ]
  }
}
```

Reglas duras:

- **`trial` es `null` cuando no se probó.** `null` y `{"ran": false}` no son lo
  mismo: `null` es "esta acción no admite prueba" (un `invite`, un
  `usage_alerts`); `{"ran": false}` es "admite prueba y no se hizo" — y eso es
  justo lo que la publicación avisa (§7.1).
- **`trial` NUNCA lleva la respuesta del agente borrador.** Ni entera, ni
  recortada, ni resumida. Lleva `probe` (que redacta el Companion, como
  `citation.claim`), aserciones con nombre estable y metadatos. Quien quiera leer
  la conversación abre el hilo de playground por `thread_id`, donde ya hay
  autorización y donde ya está el guardián del §1.3 de la investigación.
- `turns[].checks[].name` es un identificador estable en inglés; lo traduce la
  interfaz. `expected` y `actual` son **cadenas siempre**, como en la v1.1.
- Lo produce **código determinista**: se envía un turno y se comparan
  aserciones. Ni un subagente, ni una instrucción de "revisa tu trabajo" (C5).

### 7.1. Publicar avisa, no prohíbe

El `preview` de `kind: publish` (v1.1 §3.4) gana tres claves:

```jsonc
{
  "client_ref": "boreal",
  "from_version": 7, "to_version": 8,
  "evals_run": false, "evals_warning": "No se ejecutó ninguna evaluación.",
  "trial_ran": false,              // NUEVO
  "trial_ok": null,                // NUEVO — null si no se probó
  "warning_key": "not_tried"       // NUEVO — not_tried | trial_failed | null
}
```

`preview` es un objeto libre, así que esto no toca el recorrido de OpenAPI.
`warning_key` es un identificador estable que traduce la interfaz; `evals_warning`
sobrevive por compatibilidad con lo que CO-04 ya emite.

**El usuario puede publicar sin probar.** Se le dice, queda registrado en la fila
de la acción y en la auditoría, y se publica. Prohibirlo convertiría la prueba en
un peaje que la gente aprende a rodear.

---

## 8. El catálogo de eventos tiene UN dueño en la Ola 2

`apps/api/src/nexus_api/api/companion_streaming.py` **lo edita solo el Agente E.**
No porque sea suyo, sino porque dos parches al mismo `dict` en worktrees distintos
se pisan y no hay forma barata de fusionarlos.

Las **cuatro** ediciones de la Ola 2, todas de E, todas en un solo sitio:

| Edición | Evento | Cambio |
|---|---|---|
| 1 | `intake.missing` | `{slots}` → `{slots, work_kind}` |
| 2 | `verify.result` | `{action_id, checks, ok}` → `+ trial` |
| 3 | `support.ticket` | **nuevo** · `{action_id, ticket_ref, category, topic, sla}` |
| 4 | `budget.paused` | **nuevo** · `{used, cap, period, resets_at, scope}` |

**Consecuencia operativa para D**, y hay que leerla entera: en el worktree de D,
`COMPANION_EVENTS` **todavía no tendrá `work_kind`**. Un test de D que compruebe
que `work_kind` llega al navegador saldrá rojo, y eso no es un defecto: es que el
banco de pruebas no tiene el parche del otro. D prueba **lo que el nodo produce**,
no lo que el publicador deja pasar. La comprobación de extremo a extremo la hace
el orquestador en la Fase 2. **D no edita el catálogo. Si necesita una clave
nueva, para y la pide.**

### 8.1. El catálogo completo tras la Ola 2 — **20 eventos**

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
| `plan.proposed` | CO-04 | `plan_id, steps, risk, reversible, estimated_tokens` |
| `intake.missing` | CO-04 · **v2** | `slots, work_kind` |
| `hitl.requested` | CO-04 | `action_id, kind, title, preview, diff, impact, expires_at` |
| `hitl.resolved` | CO-04 | `action_id, decision, by, at, note` |
| `verify.result` | CO-04 · **v2** | `action_id, checks, ok, trial` |
| **`support.ticket`** | **CO-08** | `action_id, ticket_ref, category, topic, sla` |
| **`budget.paused`** | **CO-08** | `used, cap, period, resets_at, scope` |

**Veinte. Ni uno más en la Ola 2.** El orquestador lo comprueba en la Fase 2, y
hay un test que lo fija.

---

## 9. Migraciones — el orden lo arregla el orquestador

Dos agentes necesitan migración y ninguno puede ver la del otro.

**Regla: cada uno escribe la suya con `down_revision = "0091"`.** No adivinéis el
número del otro. Al integrar (orden E → D → F), el orquestador reencadena: la de
E queda **0092**, la de D queda **0093** con `down_revision = "0092"`. Es una
línea y no puede fallar en ninguno de los dos worktrees.

- **E · 0092** — valor `paused` en el CHECK de `companion_runs.status`; secuencia
  `console_support_ticket_seq`; bandera `partners.companion_enabled`; los `kind`
  nuevos de notificación si el CHECK los enumera.
- **D · 0093** — lo que pida la persistencia del expediente. **Si D no necesita
  migración, no la escribe**; una migración vacía es peor que ninguna.

Ninguno de los dos aplica migraciones a staging ni a producción. La 0091 ya está
en desarrollo y en `nexus_e2e`, y **no** en staging ni producción.

---

## 10. La bandera por partner

`partners.companion_enabled`, booleano, por defecto **`false`** (migración de E).

- La puerta es **`companion:use` Y la bandera**. Sin bandera: **403** con
  `detail.code = "companion_disabled"` en todas las rutas `/console/companion/*`
  salvo las lecturas de un hilo ya existente, que siguen dando 200 — apagar la
  bandera no puede hacer desaparecer la historia de lo que ya pasó.
- `GET /console/me` gana `companion_enabled: bool`. Es lo que la interfaz mira
  para montar o no la burbuja. La burbuja apagada es ausencia, no un botón
  deshabilitado con un tooltip.
- Por defecto `false` porque el piloto es interno: se enciende para Auphere, dos
  semanas de uso propio, y solo después Facelad y Amacrux.

---

## 11. Métricas del §17 — nombres estables

Los fija el contrato para que no se renombren a mitad del piloto y la serie se
parta en dos.

| Métrica | Nombre | Objetivo |
|---|---|---|
| Tareas completadas sin salir del cajón | `companion.task.completed` / `companion.thread.opened` | > 50 % |
| Confirmaciones canceladas | `companion.hitl.cancelled` / `companion.hitl.proposed` | **< 15 %** |
| Afirmaciones sin respaldo | `companion.turn.unsupported` / `companion.turn.total` | < 2 % |
| Fallos de verificación | `companion.verify.failed` / `companion.verify.total` | < 3 % |
| Coste por trabajo completado | `usage_records` con `source='companion'` | < 0,40 $ |

**La que manda es la segunda.** Un Companion que propone cosas que la gente
cancela es peor que no tener Companion: enseña a desconfiar.

El mecanismo (contadores estructurados por el camino de observabilidad que ya
existe, más una consulta agregada para el piloto) lo elige E. **No se abre un
endpoint público de métricas en la Ola 2.**

---

## 12. Cabos de la Ola 1 que la Ola 2 cierra

| # | Qué | Dueño | Cómo |
|---|---|---|---|
| 2 | `/console/audit?client=X` devuelve **200 vacío** con un ref desconocido | E | Igual que se cerró en `usage` (`usage.py:_scope`): ajeno e inexistente dan el **404 idéntico** (`"Unknown client"`). Aplica a la lista **y** a la exportación CSV |
| 3 | La auditoría pinta *Companion* sin decir qué persona | E | `_human_actor` resuelve `companion:<user_id>` a un correo por `companion.actions.decided_by`, **solo dentro del partner del llamante**. Sin resolución posible, cae a *Companion* a secas — nunca al uuid crudo |

Cabos **4 y 5 fuera de alcance**: son deuda preexistente de toda la consola.

---

## 13. Lo que NO cambia — recordatorio, porque es lo que se rompe solo

1. **`console.apply` sigue siendo la única `mutates`.** Las dos herramientas de
   soporte **proponen**. La invariante `mutates ⟹ always_ask` se comprueba al
   construir el `ToolSpec` y no es un test que se pueda saltar.
2. **Ningún endpoint ni herramienta acepta `tenant_id` ni `partner_id` del
   llamante.** Ni en ruta, ni en query, ni en cabecera, ni en cuerpo.
3. **Un `ref` ajeno y uno inexistente dan el mismo 404 opaco.**
4. **Ninguna respuesta lleva cuerpo de mensaje de un cliente final** (C8).
5. **R1–R6 viven en el motor, no en el prompt.** R1 y R3 ya existen de CO-02 y
   CO-04: **no se reimplementan**, se enganchan a las fases.
6. **La verificación es código** (C5). Cero subagentes, cero instrucciones de
   "revisa tu trabajo" en ningún prompt.
7. **El mensaje del asistente vuelve al proveedor con sus `thinking_blocks`.**
   Perderlos al reordenar el estado es un 400 en producción y en ningún test.
8. Los nombres de propiedad prohibidos del §1.1 de la v1.1 siguen prohibidos.

---

## 14. Zonas de archivo — Ola 2

Más estrechas que en la Ola 1 a propósito. Quien toque fuera de su zona **para y
pregunta**.

| | Zona |
|---|---|
| **D · CO-06** | `apps/worker/src/nexus_worker/runtime/companion/**` y sus tests `apps/api/tests/{unit,integration}/test_companion_{graph,loop,intake}*`. **Prohibido**: `companion/tools/catalog.py`, `api/companion_streaming.py`, `apps/console/**`, `config.py` |
| **E · CO-08** | `apps/api/src/nexus_api/companion/tools/support.py` (nuevo), las entradas de soporte y capacidades en `companion/tools/catalog.py`, `api/console/companion.py`, `api/console/audit.py`, `api/console/me.py`, `api/console/support.py` y `capabilities.py` (nuevos), `api/companion_streaming.py` (**dueño único**), `core/config.py`, `services/console_notifications.py`, `docs/companion/capabilities.yaml`, `apps/console/src/app/(console)/audit/**`. **Prohibido**: `runtime/companion/`, `apps/console/src/components/companion/` |
| **F · interfaz** | `apps/console/src/components/companion/**`, `apps/console/src/app/api/companion/**`, `apps/console/src/i18n/lanes/companion.ts`, `apps/console/e2e/companion.spec.ts`. **Prohibido**: `apps/api/`, `apps/worker/`, `apps/console/src/app/(console)/audit/**` |

---

## 15. Garantías con test — Ola 2

Se suman a las C1–C6, R1 y R2 de la v1.1 §7, que siguen vivas.

| Garantía | Qué afirma | Dueño |
|---|---|---|
| **E1** | Un `create_client` no llega a `plan` con `forbidden_behaviour` vacío. Falla en el **motor**, no en el prompt | D |
| **E2** | Las fases ocurren en el orden del §7 y `phase.changed` no salta una hacia atrás dentro de un run | D |
| **E3** | R6: al agotar el presupuesto de tarea el turno **cierra y reporta dónde está**; no se corta a mitad de frase | D |
| **E4** | `console.apply` sigue siendo la única `mutates` **con las dos herramientas de soporte en el catálogo** | E |
| **E5** | Un partner por encima del tope: `POST …/runs` da **409 `budget_paused`** y `POST …/resume` da **202** | E |
| **E6** | Un run cortado por presupuesto conserva historia y tokens, y sale con `status="paused"` | E |
| **E7** | `GET /console/audit?client=<ajeno>` y `<inexistente>` dan el **404 idéntico**, en lista y en CSV | E |
| **E8** | Con `companion_enabled=false`: 403 `companion_disabled` en escritura, 200 en lectura de hilos existentes | E |
| **E9** | `trial` nunca contiene la respuesta del agente borrador | Fase 2 (orquestador) |
| **Catálogo** | `COMPANION_EVENTS` contiene **exactamente** los 20 eventos del §8.1 | Fase 2 (orquestador) |

---

## 16. Bitácora

| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-08-19 | **v2.0** — congelado para la Fase 1 de la Ola 2 | Cierra `intake.missing` (`work_kind` + catálogo de slots), la fase `publish`, la forma del ticket de soporte, el esquema de capacidades, la pausa por presupuesto y `verify.result.trial`. El catálogo de eventos pasa a tener un solo dueño |

---

## 17. Enmienda v2.1 — los nombres de herramienta no salen tal cual al proveedor

> **Añadido 2026-08-19 por el orquestador, durante la Fase 0.** Notificado a D, E
> y F. Es un cambio de contrato porque toca el límite entre el motor y el
> proveedor, y porque decide **qué NO se renombra**.

### 17.1. El hallazgo

Al ejecutar por fin el camino completo con clave de proveedor real, el primer
turno con herramientas murió con un **400 de Anthropic**:

```
tools.0.custom.name: String should match pattern '^[a-zA-Z0-9_-]{1,128}$'
```

**Las 28 herramientas del catálogo se llaman con punto** (`console.get_usage`,
`console.propose_prompt`, `console.apply`…) y Anthropic **no admite el punto** en
el nombre de una herramienta. Consecuencia: **ningún turno del Companion que
ofrezca herramientas ha funcionado nunca contra el proveedor real.** Las suites
de CO-01, CO-02, CO-04 y CO-07 usan un proveedor guionizado, que acepta cualquier
nombre; el 400 solo aparece contra Anthropic.

Comprobado, no deducido — tres formas contra el proveedor real, mismo modelo,
misma llamada:

| Nombre enviado | Resultado |
|---|---|
| `console.get_usage` | **400** `invalid_request_error` |
| `console__get_usage` | **200** |
| `console_get_usage` | **200** |

### 17.2. La decisión: se traduce en el límite, no se renombra

**Los nombres del catálogo NO cambian.** Siguen siendo `console.get_usage`,
`console.propose_prompt`, `console.apply`. Se traducen **solo** al construir la
petición del proveedor y se destraducen al leer su respuesta:

```
nombre de catálogo   console.get_usage
nombre de cable      console__get_usage        (punto → doble guion bajo)
```

Es biyectivo por construcción: **ningún nombre del catálogo contiene `__`** (son
`console.` más snake_case con guiones bajos simples). La correspondencia se
construye **desde el catálogo** y se comprueba al construirla; una colisión
futura rompe al arrancar, no en producción.

**Por qué traducir y no renombrar.** El nombre con punto ya está tejido en sitios
que no se pueden mover a la vez y que son contrato:

- `tool.call.started.name` y `tool.call.completed.name` — los pinta la interfaz.
- La línea de i18n de la consola, con una entrada por herramienta.
- El dataset de evals de CO-07 y su gemelo por `ActionKind`.
- Las claves de `APPLY_ROUTES` y el `kind` de cada `propose_*`.
- El guardián `capability_is_unreachable`, que recorre `ALL_TOOLS`.

Renombrar los 28 obligaría a un cambio simultáneo en las tres zonas de la Ola 2 y
en código ya commiteado. **La restricción es del transporte, así que se resuelve
en el transporte.** Es la misma regla que ya manda en este contrato: el backend
emite identificadores estables; quien tiene que adaptarse es la capa de salida.

### 17.3. Quién lo hace

**El Agente D**, en `apps/worker/src/nexus_worker/runtime/companion/` — es su
zona y es donde se arma la petición.

- La traducción se aplica **en los dos sentidos y de forma consistente**: al
  declarar `tools`, al leer el `tool_use` de la respuesta, y al devolver el
  mensaje del asistente al proveedor en el turno siguiente. Un mensaje de
  asistente cuyo `tool_use.name` no coincida con el `tool_result` correlativo es
  otro 400, y de los que no salen en ningún test con proveedor guionizado.
- **El resto del sistema nunca ve el nombre de cable.** Ni el estado, ni los
  eventos, ni la auditoría, ni las citas.
- Test propio: para cada herramienta del catálogo, el nombre de cable cumple
  `^[a-zA-Z0-9_-]{1,128}$` y la vuelta atrás devuelve el nombre original.

**E y F no cambian nada.** E declara sus herramientas nuevas
(`support.request_help`, `support.request_capability`,
`console.get_capabilities`) con la **misma convención de punto**; la traducción
las cubre sola. F sigue recibiendo nombres con punto en los eventos.

### 17.4. Lo que esto dice del gate de la Ola 1

La Ola 1 cerró su gate con la Fase 2 "entera en verde" y con el punto 1 abierto:
*el camino de escritura no se ejecutó de extremo a extremo por navegador*. Este
400 es exactamente lo que ese punto tapaba. **Un banco de pruebas con proveedor
guionizado no puede encontrar un fallo del contrato con el proveedor**, y la única
manera de saberlo era llamar. Queda como aviso para el gate de la Ola 2: la
prueba manual con clave real no es un trámite de cierre, es la única que mira
este límite.

### 17.5. Bitácora

| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-08-19 | **v2.1** — §17: los nombres de herramienta se traducen en el límite del proveedor (`.` → `__`); el catálogo no se renombra | Anthropic rechaza el punto en `tools[].name`. Encontrado por el orquestador en la Fase 0 con clave real; notificado a D, E y F |

---

## 18. Enmienda v2.2 — los bloques de pensamiento resumido no se pueden devolver

> **Añadido 2026-08-19 por el orquestador, durante la Fase 0.** Notificado a D.
> Aparece justo detrás del §17: es el **segundo** 400 del mismo camino, y solo se
> ve con clave de proveedor real.

### 18.1. El hallazgo

Arreglado el nombre de las herramientas (§17), el turno avanzó un paso más y
murió con otro 400 de Anthropic, esta vez al devolver el mensaje del asistente
junto a los resultados de herramienta:

```
messages.1.content.0: Invalid `signature` in `thinking` block
messages.1.content.2.thinking: each thinking block must contain thinking
```

Aislado fuera de la consola, en cuarenta líneas contra el proveedor real
(`scripts` de sonda, dos pasos: pedir herramienta → devolver el asistente):

```
claves del mensaje de asistente: ['content', 'role', 'thinking_blocks', 'tool_calls']
thinking_blocks: list · 2 bloques
  claves del bloque: ['signature', 'thinking', 'type']
  firma presente: False · longitud: 0
```

**Con `display: "summarized"` el proveedor devuelve bloques de *resumen*, no
bloques de pensamiento firmados.** Llegan con `signature` vacía y con `thinking`
vacío. Anthropic exige que los bloques de pensamiento vuelvan **verbatim y
firmados**; un bloque sin firma y sin texto no es reproducible, y devolverlo es
un 400 garantizado.

Comprobado que el arreglo funciona, en la misma sonda:

```
bloques de pensamiento: 2 recibidos, 0 con firma Y texto
=== paso 2: devolver el asistente SIN los bloques irreproducibles ===
OK — el ida y vuelta funciona
```

### 18.2. La decisión

**Al devolver el mensaje del asistente al proveedor se descartan los bloques de
pensamiento que no tengan firma no vacía Y texto no vacío.** Los que sí las
tengan siguen volviendo **verbatim**: esa regla del contrato no cambia y es la
que evita el otro 400, el de perderlos.

- Si no queda ningún bloque, **la clave `thinking_blocks` se omite entera**. Una
  lista vacía no es lo mismo que ausencia y no está probada.
- **`reasoning.delta` no cambia.** El pensamiento que se pinta en el cajón sale
  del *stream*, no del mensaje devuelto, y eso funciona — verificado en la prueba
  de humo: 1.492 caracteres de pensamiento con texto real.
- El filtro va **donde se arma el mensaje que vuelve a `messages`**, no en el
  publicador ni en el prompt.

### 18.3. Por qué esto no lo veía ningún test

El plan de CO-01 (§4.1) ya avisaba de que
`thinking={"type": "adaptive", "display": "summarized"}` **nunca se había
verificado contra Anthropic**, y dejó media verificación hecha sin red: LiteLLM
declara `thinking` como parámetro soportado y lo pasa verbatim. Eso era cierto y
era lo comprobable.

Lo que quedaba —qué **devuelve** el proveedor— resultó ser lo que rompe. Y la
prueba de humo del pensamiento tampoco lo habría cogido: llama **sin
herramientas**, así que no hay mensaje de asistente que devolver y no hay ida y
vuelta. El fallo vive exactamente en la intersección de *pensamiento activo* +
*herramientas* + *segundo paso del bucle*, que es la casilla que ningún banco de
pruebas con proveedor guionizado ocupa.

### 18.4. Quién lo hace

**El Agente D**, en la misma pasada que el §17: es el mismo punto del código y
la misma clase de fallo. Test propio: un mensaje de asistente con bloques sin
firma sale sin `thinking_blocks`; uno con bloques firmados los conserva
**verbatim**, byte a byte.

### 18.5. Bitácora

| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-08-19 | **v2.2** — §18: los bloques de pensamiento sin firma o sin texto se descartan al devolver el mensaje del asistente; los firmados siguen volviendo verbatim | Con `display: "summarized"` Anthropic devuelve bloques de resumen no reproducibles y rechaza la petición al recibirlos de vuelta. Encontrado por el orquestador en la Fase 0 con clave real, aislado y con el arreglo verificado; notificado a D |

---

## 19. Enmienda v2.3 — el tercer 400, y las decisiones que levantaron D y F

> **Añadido 2026-08-19 por el orquestador, al cerrar la Fase 0 y recibir a D y a
> F.** Notificado a D y a E.

### 19.1. La llamada de cierre no puede ir sin `tools`

Tercer 400 del mismo camino, y el que faltaba para completar la pasada:

```
litellm.UnsupportedParamsError: Anthropic doesn't support tool calling without
`tools=` param specified.
```

Ocurre en el **turno de respuesta**: una vez ejecutada y verificada la acción, la
última llamada al modelo se hace **sin herramientas** — pero `messages` sigue
llevando mensajes de asistente con `tool_calls`. Anthropic exige que, si el
historial contiene uso de herramientas, la declaración de herramientas siga
presente.

Probado contra el proveedor real, tres formas, mismo historial:

| Llamada de cierre | Resultado |
|---|---|
| sin `tools` (lo que hace hoy) | **falla** `UnsupportedParamsError` |
| con `tools` + `tool_choice: "none"` | **OK** |
| con `tools`, sin `tool_choice` | **OK** |

**Decisión: la llamada de cierre declara `tools` igual que las demás y añade
`tool_choice: "none"`.** Quitar las herramientas no es la forma de decir "ya no
llames a nada" — la forma es `tool_choice`. Sin él, el modelo *puede* volver a
llamar y el paso de cierre deja de ser de cierre.

**Dueño: D.** Es el mismo punto del bucle que §17 y §18.

### 19.2. `verify.result.trial` necesita `client_ref`

Lo levantó **F** y tiene razón: el §7 dice que la interfaz enlaza al hilo de
playground, pero la ruta es `/clients/{ref}/playground` y `trial` no lleva `ref`.
Correlacionar por `action_id` con `preview.client_ref` funciona, pero `preview`
es un objeto libre y eso no es una garantía dura.

**`trial` gana una clave**:

```jsonc
"trial": {"ran": true, "client_ref": "vol-01", "thread_id": "4d2b…", "ok": true, "tokens": 4210, "turns": [...]}
```

No toca el catálogo (`trial` ya está declarado como clave de `verify.result`; el
filtro es de primer nivel). **Dueño: el orquestador, en CO-05.**

Queda **abierto y fuera de alcance de la Ola 2**: la página de playground **no lee
ningún parámetro de hilo de la URL** (el hilo elegido vive en estado local de
`components/playground/playground.tsx`), así que el enlace existe pero hoy no
selecciona nada. No es de ninguna de las tres zonas. Va a un paquete aparte.

### 19.3. `budget.updated.exhausted` y `budget.paused`

F señala que describen la misma condición (`used >= cap`) y que el contrato no
dice cuál manda. Es un hueco mío.

**Decisión: son la misma condición y la interfaz puede tratarlas igual.**
`exhausted: true` significa *el tope está alcanzado* y basta para pintar la
pausa; `budget.paused` añade *y este turno se cortó aquí*. La unificación que
hizo F es la correcta y se queda.

### 19.4. El ticket tiene que sobrevivir a la rotación del log

También de F: si `hitl.requested` rota fuera del log de Redis y `support.ticket`
no, el `ticket_ref` desaparece sin decir nada. Es el mismo agujero que la v1.1
cerró para la tarjeta pendiente con `GET /console/companion/actions/{id}`.

**`CompanionActionOut` gana dos campos opcionales**: `ticket_ref: str | None` y
`sla: str | None`. Nulos para todo `kind` que no sea de soporte. **Dueño: E.**

### 19.5. La fase `publish` — se resuelve sin tocar el enum

D señala que las tres frases del §2 no encajan a la vez: preparar la segunda
confirmación implica `awaiting`, que tiene rango menor que `publish`, y eso sería
un salto hacia atrás contra la garantía E2.

**La contradicción es aparente y la deshace una regla que ya existe**: PLAN-CO-04
D3 — **cada run pone en `proposed` como mucho UNA acción, y un segundo paso es un
turno nuevo**. Por tanto:

- Dentro del run que ejecuta el cambio: `… verify → publish → respond → done`.
  `publish` es donde el Companion **anuncia** que esto desemboca en una
  publicación y la ofrece.
- La publicación se propone en el **run siguiente**, que arranca limpio en
  `understand` y llega a `awaiting` por su propio camino.

No hay salto hacia atrás porque **el rango de fase es por run**, nunca por hilo.
El enum **no cambia**, y la lectura que implementó D es la correcta. Esta frase
es lo que faltaba en el §2.

### 19.6. Los `work_kind` que declaran campos sin puerta de entrada

D encontró que tres de los cinco `work_kind` del §3.3 exigen campos que ninguna
herramienta `propose_*` acepta hoy: `failing_behaviour` y `real_example`
(`change_prompt`), `ai_disclosure_decision` (`publish`), `connector_consent`
(`enable_connector`). Exigirlos literalmente bloquearía **para siempre** todo
cambio de prompt y toda publicación, porque el modelo no tendría por dónde
entregar el dato.

**La solución de D se queda**: la puerta se mide contra el catálogo publicado, y
se enciende sola el día que esos parámetros existan. Hoy protege `create_client`,
que es lo que la garantía E1 exige.

`connect_whatsapp` no tiene herramienta `propose_*` en absoluto (el alta va por
el Embedded Signup): se queda declarado e inalcanzable, a la espera de que exista.

Las dos cosas quedan **anotadas como deuda con nombre**, no como fallo.

### 19.7. Bitácora

| Fecha | Cambio | Motivo |
|---|---|---|
| 2026-08-19 | **v2.3** — §19.1 la llamada de cierre lleva `tools` + `tool_choice:"none"`; §19.2 `trial` gana `client_ref`; §19.3 `exhausted` y `budget.paused` son la misma condición; §19.4 `CompanionActionOut` gana `ticket_ref` y `sla`; §19.5 la fase `publish` se resuelve porque el rango es por run; §19.6 los `work_kind` sin puerta de entrada quedan como deuda con nombre | Tercer 400 encontrado al completar la pasada por navegador, más las cinco lagunas que levantaron D y F al cerrar |
