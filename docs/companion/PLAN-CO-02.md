# CO-02 · Catálogo de herramientas de lectura del Companion

> Segundo paquete del Companion de la consola de partners.
> Fuente de diseño: `Auphere/nexus/research/2026-08-17-companion-agente-de-consola.md`
> — **Parte II (§21-§27) manda sobre la Parte I**.
> Acta de decisiones: `Auphere/nexus/decisions/ADR-033-companion-de-consola.md`.
> Paquete anterior: [`PLAN-CO-01.md`](PLAN-CO-01.md).
>
> Vive en el repo porque el cambio cruza `apps/api` y `apps/worker` y toca
> bastante más de tres archivos. Sobrevive a la compactación; el chat no.

---

## 0. Qué entrega CO-02

Las herramientas de **solo lectura** del §6.1 sobre los routers `/console/*`
existentes, y el bucle del grafo que las usa. Al terminar, los cinco trabajos
del §4.3 responden **en su forma de consulta**, con citas:

1. crear un cliente → *qué haría falta* (lee cuota, plantillas y catálogo; no
   crea nada);
2. mejorar un prompt → *lee* el prompt activo, sus herramientas y su política;
3. diagnosticar "no funciona" → encadena canales, diagnóstico, plantillas,
   auditoría y estadísticas de conversación;
4. explicar el gasto → consumo, serie y desglose;
5. enseñar la plataforma → catálogo real de herramientas y skills.

Fuera de alcance: el cajón y la burbuja (CO-03), propuestas/HITL/ejecución
(CO-04). **Ninguna herramienta de escritura, ni siquiera "preparada".**

---

## 1. La regla que define el paquete

**Las herramientas llaman a los routers `/console/*` por HTTP en proceso**
(`httpx.AsyncClient` sobre `ASGITransport`). No llaman a `services/` ni a
`repositories/`, aunque sea más rápido.

Saltarse el router se salta, todo junto: la validación Pydantic, `client_scope`
(que resuelve el `external_client_ref` bajo el principal y abre la transacción
con RLS), el limitador de ráfaga, la cuota de aprovisionamiento (0081), el
vocabulario de auditoría (0084) y la cobertura automática de
`tests/isolation/test_console_scope.py`. En seis meses el Companion sería un
camino paralelo con sus propios agujeros. El coste es ~1 ms por llamada.

Se convierte en lint bloqueante (garantía **C2**), al estilo del
`check:no-admin-token` de CP-03: un test que recorre el AST de todos los módulos
del paquete de herramientas y falla si alguno importa `nexus_api.services` o
`nexus_api.repositories`.

---

## 2. Decisiones abiertas — con recomendación

### D1 · ¿Con qué credencial llama la herramienta al router? → **Principal propagado en proceso**

Este es el hueco real del encargo. "Con el JWT del principal" **no se puede
implementar literalmente**, por dos razones que se suman:

- el JWT de consola vive **60 segundos** (`console_jwt_max_ttl_seconds`) y un
  run del Companion dura minutos;
- su `jti` es de **un solo uso** — `consume_jti` lo quema en Redis en la primera
  presentación —, así que ni siquiera valdría para dos llamadas seguidas.

Y minar uno nuevo exigiría meter la **clave privada de la consola** en la API,
que hoy solo tiene la pública. Eso convertiría a la API en capaz de fabricar la
identidad de cualquier miembro de cualquier partner: una superficie nueva a
cambio de nada, porque el llamante y el llamado son el mismo proceso.

**Recomendación (implementada):** una variable de contexto,
`console_auth.acting_as(actor)`, que el ejecutor de herramientas fija alrededor
de la llamada y limpia siempre. `require_console_principal` la consulta **antes**
de mirar la cabecera `Authorization`; si hay actor en contexto, se salta
`_verify_bearer` y **todo lo demás corre igual**:

- la membresía se **relee de la base de datos** en cada llamada (un miembro
  expulsado a mitad de run deja de poder leer);
- el partner tiene que seguir `active` y con `console_enabled`;
- el **rol sale de la fila**, no de ningún claim;
- el permiso declarado por la ruta se comprueba igual (`agents:read`,
  `usage:read`…), así que un `analyst` recibe el mismo 403 que recibiría desde
  el navegador.

Lo único que se salta es la verificación criptográfica y el anti-replay, que son
exactamente los dos controles cuya razón de ser es el tramo BFF→API por red.

Por qué no es un agujero: la variable de contexto **no se puede activar desde
fuera**. Uvicorn crea una tarea por petición a partir del contexto raíz del
servidor, no del de otra petición; solo el ejecutor de herramientas —dentro de
la tarea del run, tras un principal ya verificado— la fija. Una cabecera forjada
no la enciende. Hay un test de aislamiento que lo prueba.

Alternativas descartadas:

| Opción | Por qué no |
|---|---|
| Reenviar el Bearer del navegador | Muere a los 60 s y el `jti` ya está quemado |
| Firmar tokens en la API | Mete la clave privada de la consola en un servicio que no la necesita |
| `app.dependency_overrides` sobre un sub-app | `require_console_principal` es una **fábrica**: cada ruta tiene su propia clausura, y el override tendría que replicar la comprobación de permisos — es decir, reimplementar la autorización, que es justo lo que este paquete evita |
| Un token interno con secreto compartido | Autorización nueva. Prohibido por el encargo |

### D2 · ¿Dónde vive el paquete de herramientas? → **`apps/api`, inyectado en el grafo**

`apps/worker` **no importa `nexus_api`** en ninguna parte, y esa asimetría vale
la pena conservarla: el worker es el runtime de los agentes de cliente y no
tiene por qué conocer la superficie HTTP de la consola.

Recomendación: el paquete vive en `apps/api/src/nexus_api/companion/tools/` y el
grafo recibe un **`Toolbelt`** por parámetro, declarado en el worker como
`Protocol` de dos métodos (`specs()` y `call(name, args)`). El grafo no sabe si
detrás hay HTTP, un doble de test o nada.

Efecto colateral bueno: el lint de C2 tiene un directorio exacto que vigilar.

### D3 · ¿14 herramientas o 18? → **18, y se documenta el desajuste**

El §6.1 se titula "catorce herramientas" porque su tabla tiene 14 **filas**,
pero varias filas llevan dos nombres (`list_clients` / `get_client`,
`list_tools` / `list_skills`, `get_usage` / `usage_series`,
`get_prompt_library` / `list_seed_templates`). La enumeración del encargo lista
**18 nombres**. Se implementan los 18; `list_seed_templates` se pliega dentro de
`get_prompt_library`, que es su único endpoint.

### D4 · ¿Cómo señala el motor un turno sin respaldo (R1)? → **clave `unsupported` en `run.completed`**

El encargo fija cuatro eventos nuevos: `tool.call.started`,
`tool.call.completed`, `citation` y `phase.changed`. Ninguno es el sitio natural
de un veredicto que solo se conoce **al cerrar el turno**, y añadir un quinto
evento fuera de la lista sería salirse del encargo.

Recomendación: `run.completed` —que ya existe y ya es el evento terminal— gana
la clave booleana `unsupported`. El cajón la pinta como aviso en el turno y la
métrica se toma ahí mismo, en un punto que se ejecuta siempre, incluso si el run
falla.

### D5 · ¿Cómo se decide que una respuesta "afirma un dato del sistema"? → **patrones estrechos, y solo cuando no se leyó nada**

R1 tiene que ser código determinista (C5), no una pregunta al modelo. El riesgo
de un detector amplio es el contrario del que parece: un falso positivo
constante convierte la marca en ruido y la métrica en basura.

Recomendación: se marca `unsupported` **solo** si se cumplen las dos cosas:

1. en el turno **no se ejecutó ninguna herramienta de lectura con éxito**; y
2. la respuesta encaja con alguno de seis patrones estrechos de afirmación
   factual: porcentaje, importe con moneda, número seguido de una unidad del
   dominio (*tokens, mensajes, conversaciones, clientes, canales, plantillas,
   documentos*), fecha con forma de fecha, referencia de versión (`v7`), o un
   verbo de estado sobre un estado del sistema (*está publicado, sigue activo,
   quedó rechazada*).

Un "te lo explico en 3 pasos" no dispara nada. Una respuesta que dice "Boreal
gastó 1.200.000 tokens" sin haber leído, sí.

### D6 · ¿Qué ve el modelo del presupuesto? → **nota de sistema al cruzar umbrales**

§23.3 propone `task_budget`, que es un parámetro **en beta** del proveedor
(`task-budgets-2026-03-13`). Atarse a una beta para un contador es caro.

Recomendación: la cuenta atrás se implementa como **mensaje `role: "system"`
añadido al final de `messages`** (nunca en el prefijo cacheado, C4) y **solo al
cruzar umbrales** —quedan ≤5 llamadas, o queda <25 % del presupuesto de tokens
del turno—, no en cada paso. Se añade, no se reescribe: el prefijo crece de
forma monótona y el caché sigue encajando. Detrás queda el tope duro
(`companion_max_tool_calls_per_turn`) como red.

---

## 3. Entregables, en orden de construcción

### 3.1. Propagación del principal — `core/console_auth.py`

`InProcessActor(user_id, partner_id, jti)` + `acting_as()` (contextmanager) +
la rama en `require_console_principal`. ~30 líneas, en el archivo donde un
revisor de seguridad ya mira.

### 3.2. El cliente en proceso — `companion/tools/client.py`

`httpx.AsyncClient(transport=ASGITransport(app), base_url="http://companion")`,
uno por run, cerrado al terminar. Sin cabecera `Authorization` (D1). Timeout
propio y corto: una herramienta que tarda 30 s ya rompió la conversación.

### 3.3. El catálogo — `companion/tools/catalog.py`

Una tabla de datos, no un `if`. Cada entrada:

```python
ToolSpec(
    name="console.get_usage",
    method="GET",
    path="/console/usage",                 # o con {ref}
    params=(Param("client_ref", ...), Param("days", ...)),
    description="…",                        # prescriptiva, ver §4
    label="Consumo del partner",            # para la cita y el cajón
    max_chars=8_000,
)
```

Los 18 nombres y su endpoint de origen:

| Herramienta | Endpoint |
|---|---|
| `console.whoami` | `GET /console/me` |
| `console.list_clients` | `GET /console/clients` |
| `console.get_client` | `GET /console/clients/{ref}` |
| `console.get_agent` | `GET /console/clients/{ref}/agent` |
| `console.get_policy` | `GET /console/clients/{ref}/agent/settings` |
| `console.list_tools` | `GET /console/clients/{ref}/tools` |
| `console.list_skills` | `GET /console/clients/{ref}/skills` |
| `console.list_knowledge` | `GET /console/clients/{ref}/knowledge` |
| `console.list_channels` | `GET /console/clients/{ref}/channels` |
| `console.channel_diagnostics` | `GET /console/clients/{ref}/channels/diagnostics` |
| `console.list_templates` | `GET /console/clients/{ref}/channels/whatsapp/templates` |
| `console.get_usage` | `GET /console/usage` |
| `console.usage_series` | `GET /console/usage/series` |
| `console.conversation_stats` | `GET /console/clients/{ref}/conversations/stats` |
| `console.get_audit` | `GET /console/audit` |
| `console.get_onboarding` | `GET /console/onboarding` |
| `console.get_quota` | `GET /console/home` |
| `console.get_prompt_library` | `GET /console/seed-templates` |

Reglas del catálogo, todas comprobadas por test:

- **ninguna acepta `tenant_id` ni `partner_id`** — el cliente se nombra
  `client_ref` y lo resuelve el router bajo el principal;
- **todas son `GET`**;
- **toda ruta existe** en la aplicación (se comprueba contra `app.routes`), así
  que ninguna herramienta puede apuntar a un endpoint que ya no está;
- `console.conversation_stats` apunta a `/conversations/stats`, **nunca** a
  `/conversations` (decisión C8).

### 3.4. El ejecutor — `companion/tools/runner.py`

Por llamada: validar los argumentos contra el esquema → `tool.call.started` →
petición en proceso bajo `acting_as` → traducir el resultado o el error →
`tool.call.completed` → `citation` si fue bien.

**Traducción de errores** (que el modelo entienda qué hacer, no un volcado):

| Del router | Al modelo |
|---|---|
| 404 | `unknown_client` — "No hay ningún cliente con esa referencia bajo este partner. Pregunta cuál es o usa `console.list_clients`." |
| 403 | `forbidden` — "El rol de quien te habla no permite esto. Dilo y no lo intentes por otro camino." |
| 409 | `conflict` + el detalle del router (p. ej. WhatsApp no conectado) |
| 422 | `bad_arguments` + qué campo |
| 429 | `rate_limited` — "Demasiadas consultas seguidas; espacia el trabajo." |
| 5xx | `unavailable` — "La plataforma no respondió. Dilo, no lo inventes." |

El 404 es **opaco a propósito**: idéntico para un `ref` inexistente y para uno
de otro partner (garantía C1).

**Recorte**: cada respuesta se recorta a `max_chars` con marca explícita
(`…[recortado: N caracteres más]`). Sin esto, tres llamadas a `get_audit` llenan
la ventana de contexto y el resto del turno responde a ciegas.

### 3.5. El bucle del grafo — `runtime/companion/graph.py`

`entender → investigar (bucle) → responder`.

El nodo `investigate` deja de estar vacío y pasa a contener el bucle:

```
phase.changed(investigate)
repetir hasta N pasos:
    stream del modelo CON herramientas
      ├─ reasoning.delta
      ├─ text.delta          → primera palabra de un paso ⇒ phase.changed(respond)
      └─ tool_calls acumuladas
    si no hay tool_calls: salir
    phase.changed(investigate)
    por cada llamada: tool.call.started → ejecutar → tool.call.completed → citation
    añadir a messages: mensaje del asistente + resultados
```

Dos cosas del motor, no del prompt:

- **La fase sigue a lo que está pasando.** El pill dice *Investigando* mientras
  corre una herramienta y *Respondiendo* mientras salen palabras. Sin
  herramientas la secuencia sigue siendo `understand → investigate → respond`,
  que es lo que ya prueba CO-01.
- **La respuesta es el último mensaje del asistente sin llamadas.** No hay una
  segunda llamada al modelo para "redactar": pagarla sería duplicar el coste del
  turno para repetir lo que el bucle ya produjo.

`respond` se queda como nodo de cierre: emite `cost.updated` y `context.updated`
con los totales del turno, aplica **R1** y fija `phase = done`.

**Topes**, repartidos según quién los tiene que conocer:

- `companion_max_tool_calls_per_turn = 25` y `companion_tool_timeout_s = 10`
  viven en `config.py` (API): son del ejecutor, que es quien hace la petición, y
  se ajustan por entorno.
- `MAX_MODEL_STEPS = 12` y `TURN_TOKEN_BUDGET = 120_000` son constantes del
  **worker**, junto al grafo. El grafo no lee la configuración de la API — hoy
  no importa `nexus_api` en ninguna parte y conviene que siga así.

**Pensamiento y herramientas.** Con pensamiento activo, los bloques del
asistente tienen que volver al proveedor tal cual en el turno siguiente del
bucle; el acumulador del stream los conserva (`thinking_blocks` con su firma) y
los adjunta al mensaje del asistente. Perderlos es un 400 de Anthropic, no un
detalle estético.

### 3.6. Streaming con herramientas — `runtime/llm.py`

`astream_complete` de CO-01 no emite llamadas a herramienta. Se añade
`astream_with_tools`, hermano suyo, que cede `(kind, payload)` con
`kind ∈ {"text", "thinking", "tool_call", "assistant", "usage"}` y pasa por el
**mismo `_record_call`**. Es la regla que ya se puso en CO-01 y por el mismo
motivo: el punto de estrangulamiento del consumo es uno solo, y un tercer camino
con su propia copia dejaría de facturar el Companion en cuanto uno de los tres
se moviera. `InMemoryProvider` gana el equivalente, con llamadas programables.

### 3.7. Eventos nuevos — `api/companion_streaming.py`

Entran en `COMPANION_EVENTS` con sus claves cerradas:

```python
"tool.call.started":   {"tool_call_id", "name", "label", "args"}
"tool.call.completed": {"tool_call_id", "name", "ok", "latency_ms", "error", "citation_id"}
"citation":            {"citation_id", "claim", "source", "fetched_at"}
"run.completed":       + "unsupported"
```

`phase.changed` ya existe desde CO-01.

Ninguna clave se llama como el cuerpo de un mensaje de cliente final, y por eso
`test_companion_no_customer_bodies.py` sigue verde. `args` lleva **solo lo que
el modelo escribió** (un `client_ref`, unos días), nunca contenido leído.

### 3.8. El prompt — `runtime/companion/prompt.py`

- **Se borra `<lo_que_puedes_hacer_ahora>`**, el párrafo que dice que no hay
  herramientas. Dejarlo con las herramientas puestas haría que el agente se
  negara a usarlas — lo advirtió el log de CO-01.
- `<regla_madre>` se reescribe: *si no lo has leído con una herramienta en este
  turno, no lo afirmes*.
- Bloque `<herramientas>` con la disciplina: leer antes de afirmar, no adivinar
  una referencia de cliente, `console.whoami` cuando el rol importa, y **no
  repetir una lectura idéntica** en el mismo turno.
- Sigue sin haber **ni una palabra de auto-verificación** (C5) ni mención a
  subagentes (el Companion v1 no tiene).

---

## 4. Cómo se escriben las descripciones

La guía de migración a Opus 5 es explícita: las descripciones **prescriptivas**
—las que dicen *cuándo* llamar, no solo qué hace— dan mejora medible en modelos
recientes, que por defecto tiran poco de herramientas.

```
MAL:  "Devuelve el consumo del partner."

BIEN: "Devuelve el consumo del partner por cliente, canal y periodo. Llama a
       esto cuando el usuario pregunte por gasto, consumo, factura, proyección
       de fin de mes, o por qué subió el coste de un cliente. No lo uses para
       el coste de Auphere — eso no se expone."
```

Mínimo tres o cuatro frases por herramienta, con **condición de disparo** y
**cuándo-no**. Hay un test que lo hace obligatorio: toda descripción del
catálogo pasa de un mínimo de longitud y contiene una condición de disparo
("cuando…") y una negativa ("no lo uses…"/"no sirve…").

---

## 5. Tests

| Suite | Qué prueba |
|---|---|
| `tests/isolation/test_companion_tools_imports.py` | **C2** — ningún módulo del paquete importa `services/` ni `repositories/` (AST, no grep) |
| `tests/isolation/test_companion_tool_scope.py` | **C1** — `client_ref` de otro partner → 404 **idéntico** al de un ref inexistente; el actor en proceso no se puede activar con una cabecera; un rol sin permiso recibe 403 del router |
| `tests/isolation/test_companion_no_customer_bodies.py` | **C3** — extendido: las claves de los eventos nuevos, y que toda ruta del catálogo es un `GET` de `/console/*` cubierto por el recorrido genérico |
| `tests/unit/test_companion_tools_catalog.py` | por herramienta: esquema de entrada, ningún `tenant_id`/`partner_id`, ruta existente, descripción prescriptiva |
| `tests/unit/test_companion_tools_runner.py` | traducción de cada código de error, recorte, citas, tope de llamadas |
| `tests/unit/test_companion_loop.py` | el bucle, las fases, R1, los seis patrones factuales y la nota de presupuesto |
| `tests/unit/test_companion_graph.py` | (existente) el prompt, el pensamiento y los medidores |
| `tests/unit/test_companion_thinking_contract.py` | LiteLLM mete `thinking` verbatim en el cuerpo de Anthropic (la mitad de C3 que sí se puede probar sin red) |
| `tests/integration/test_companion_tasks.py` | los cinco trabajos del §4.3 en su forma de consulta, extremo a extremo, con los routers reales detrás |

---

## 6. Riesgos asumidos

1. **R1 es una heurística.** Estrecha a propósito (D5): prefiere no marcar a
   marcar de más. Un turno que afirma un dato del sistema con una frase que no
   encaja en ninguno de los seis patrones pasa sin marca. Es un medidor, no una
   barrera; la barrera de las escrituras es CO-04.
2. **La respuesta de una herramienta entra entera en el contexto.** El recorte
   por `max_chars` acota el daño pero no lo elimina: veinte llamadas caras
   siguen llenando la ventana. El medidor de contexto de CO-01 lo hace visible;
   la compactación es trabajo posterior.
3. **El actor en proceso es una variable de contexto.** Es correcto por cómo
   asyncio copia el contexto por tarea, y hay un test que lo fija, pero es un
   invariante del entorno de ejecución y no una barrera criptográfica. Si algún
   día el Companion corre fuera del proceso de la API, esto se sustituye por un
   token real y el resto del paquete no se entera.
