# PLAN-CO-06 · Expediente y máquina de estados

> Agente D de la Ola 2. Ejecuta el §7 y el §7.1 de la investigación con la
> mecánica del §2 y §3 de [`CONTRACT-V2.md`](CONTRACT-V2.md).
>
> **El contrato manda.** Donde este plan y el contrato v2 difieran, gana el
> contrato. Lo que aquí se decide es solo lo que el contrato delegó
> explícitamente en D: **la forma de la persistencia del expediente** (§3.4),
> cómo se enganchan R1 y R3 a las fases (§13.5) y el mecanismo del
> `task_budget` (R6).
>
> Todo el trabajo cae en `apps/worker/src/nexus_worker/runtime/companion/**`
> y sus tests. **Ni una línea fuera de la zona de D** (§14).

---

## 0. La forma del cambio en una pantalla

```
 ── por RUN ────────────────────────────────────────────────────────────
 understand   ← borra el rastro del run anterior (hitl, verify, action_id,
      │         tool_messages, answer). El expediente NO se borra: es del hilo.
      ▼
 investigate  bucle de herramientas
      │        · cada console.propose_* alimenta el EXPEDIENTE con sus args
      │        · nota de expediente + nota de presupuesto al final de messages
      │        · puerta de tokens ANTES de cada llamada al modelo (R6)
      │        · si el turno se queda sin presupuesto → PASO DE CIERRE (E3)
      ▼
   ¿hay propuesta?
      │  sí ─── ¿el expediente del work_kind está completo?
      │           │  no  → intake   phase.changed(intake) + intake.missing{slots, work_kind}
      │           │                 y NO se planifica  ← garantía E1
      │           └─ sí  → plan → awaiting → [interrupt] → execute → verify
      │                                                        │
      │                                                   ¿verde y publica?
      │                                                        └→ publish
      └─ no ──→ (¿faltan huecos?) intake → respond

 ── emisión de fases ───────────────────────────────────────────────────
 PhaseTracker: rango monótono sobre el enum de 10. Una transición hacia
 atrás NO se emite; un salto ilegal (execute sin awaiting) LANZA.  ← E2
```

---

## 1. Decisiones que el contrato delegó en D

### D1 · La persistencia del expediente: el checkpoint del hilo, sin migración

**Decisión: el expediente vive en `CompanionState["intake"]`, y punto.**
No hay tabla nueva, no hay migración, no hay endpoint.

El razonamiento es una comprobación, no una intuición. El driver compila el
grafo con `config = {"configurable": {"thread_id": str(thread_id)}}`
(`api/console/companion.py:698`) y el checkpointer de producción es el
`AsyncPostgresSaver` del proceso. Es decir: **el checkpoint está indexado por
el hilo de la conversación, no por el run**. Lo verifiqué corriendo dos runs
seguidos sobre el mismo `thread_id` y leyendo `graph.aget_state()`: todas las
claves del estado del run 1 seguían ahí al empezar el run 2.

Consecuencias, las tres que importan:

1. Una clave nueva en `CompanionState` **sobrevive entre turnos** sin que
   nadie la reenvíe, y sobrevive **en Postgres**, así que la sirve igual otro
   proceso. Es exactamente lo que pide el §3.4 ("un slot respondido no se
   vuelve a preguntar aunque el turno lo sirva otro proceso").
2. **No hace falta migración.** El contrato §9 es explícito: si D no la
   necesita, no la escribe. No la escribo.
3. No aparece en ningún endpoint. La interfaz sigue reconstruyendo el
   expediente del timeline, como dice el §3.4.

Forma exacta:

```python
# CompanionState["intake"] — del HILO, no del run
{
  "answers": {"create_client": {"name": "Boreal", "vertical": "clínica estética"}},
  "asked":   {"create_client": ["timezone", "forbidden_behaviour"]},
  "facts":   {}          # condiciones de los slots condicionales (§3.3 nota ¹)
}
```

- `answers` se alimenta **de los argumentos con los que el modelo llamó a
  `console.propose_*`**, que el grafo ya tiene delante en `_run_tool`. No de
  parsear la prosa del usuario: adivinar un slot es el fallo que el §7.1
  existe para evitar. Se acumulan entre turnos, que es lo que hace que un dato
  dado en el turno 1 no se vuelva a pedir en el turno 3.
- `asked` es memoria de lo ya preguntado. Sirve para no repetir un chip.
- Sólo se guardan claves **del catálogo cerrado** del §3.3. Un argumento que
  no sea un slot (el `system_prompt` entero, por ejemplo) no entra: el
  expediente no es un búfer de la conversación.

### D2 · El corolario que la comprobación destapó: el rastro del run anterior

La misma comprobación enseñó un **defecto real y preexistente**, no una
consecuencia de este trabajo: como el checkpoint es del hilo, `hitl`,
`verify`, `action_id` y `tool_messages` del run anterior **siguen en el estado
cuando arranca el turno siguiente**, y el driver no los limpia (arma un
`state` nuevo sin esas claves, y LangGraph solo pisa los canales que le
mandas). Medido: tras un HITL confirmado, el turno siguiente del mismo hilo
entra por `_answer_after_action` y responde **dos veces** — una con el bucle y
otra con el informe de una acción que ya se contó. Ver §5.

Por eso el nodo `understand` pasa a **limpiar los canales del run**. Es la
otra mitad de D1: si el expediente va a ser del hilo, hay que decir en voz
alta qué es del hilo y qué es del run, y hacerlo cumplir en un sitio.

| Del **hilo** (sobrevive) | Del **run** (se limpia en `understand`) |
|---|---|
| `intake`, `thread_id`, `principal` | `hitl`, `verify`, `action_id`, `action_kind` |
| | `tool_messages`, `answer`, `unsupported`, `phase` |

`understand` no corre en un `resume` (el grafo retoma en `confirm`), así que
la limpieza **no toca** el run de continuación. Verificado con la secuencia
del §4.3 del contrato v1, que ya tiene test.

### D3 · Cómo se enganchan R1 y R3 a las fases

Ninguna de las dos se reimplementa (§13.5). Lo que se añade es el enganche:

- **R1** ya se calcula en `respond` (`grounding.is_unsupported`). El enganche
  es de orden: `respond` es la penúltima fase del enum y el veredicto se
  calcula **con el estado completo**, una sola vez. La máquina de fases
  garantiza ahora que `respond` ocurre exactamente una vez por run y siempre
  al final, que antes no estaba garantizado (el bucle podía emitirla y
  volverse atrás).
- **R3** (propose → `interrupt()` → apply) se engancha como **transición
  ilegal**: `execute` sólo se puede entrar desde `awaiting`. No es un aviso:
  el `PhaseTracker` **lanza**. Hoy es inalcanzable por construcción del grafo,
  y esa es justamente la razón de ponerlo — un reordenado futuro de nodos que
  se saltara la confirmación no compilaría un turno, en vez de escribir sin
  preguntar. La barrera de verdad (C4, la acción tiene que estar `confirmed`)
  sigue donde estaba y no se toca.

### D4 · El mecanismo de R6: cuenta atrás visible + puerta dura + cierre

Tres piezas, y la tercera es la que faltaba:

1. **`task_budget` visible** — se mantiene el mecanismo ya probado en CO-02:
   `budget_note` al final de `messages` al cruzar umbrales. No se reescribe
   ninguna nota anterior y no se toca el prompt de sistema, así que el prefijo
   cacheado sigue encajando. No lo cambio: funciona y tiene test.
2. **Puerta dura antes de cada llamada al modelo**, no un cálculo posterior
   (es la forma que el §23.2 recomienda y que el §6.3 del contrato v2 fija
   para el tope del partner). Si lo gastado ya alcanza `TURN_TOKEN_BUDGET`, el
   bucle no hace la llamada siguiente. La llamada que cruza el tope se
   completa: el tope es del trabajo nuevo, no un corte exacto.
3. **Paso de cierre (E3)** — lo nuevo. Cuando el turno se agota (tokens,
   pasos o llamadas) **y no ha escrito nada para la persona**, hoy el run
   termina con `answer` vacío: eso es cortarse en seco, que es exactamente lo
   que E3 prohíbe. Ahora se hace **una última llamada sin herramientas**, con
   una nota de sistema que dice qué se agotó y pide cerrar diciendo dónde
   quedó el trabajo. Si esa llamada tampoco produce texto —o falla— hay un
   **cierre determinista** en castellano, sin cifras (para no disparar R1).

   Una llamada más justo al agotar el presupuesto es deliberado y es la misma
   licencia del §6.3: *la llamada que cruza el tope se completa*. Un turno que
   cierra cuesta una llamada; un turno que se corta cuesta la confianza.

**R6 no emite ningún evento nuevo.** Lo dice el Companion con sus palabras en
`text.delta`. No se confunde con el tope mensual del partner (§6 del contrato
v2), que es de E.

---

## 2. La máquina de estados (§7, garantía E2)

### 2.1. El enum, cerrado y ordenado

```
understand · investigate · intake · plan · awaiting · execute · verify · publish · respond · done
```

Diez valores, en el orden del §2 del contrato v2, que **es** el orden del §7 de
la investigación. `PHASE_ORDER` fija ese orden y `PHASE_RANK` lo convierte en
número. `PHASE_LABELS[publish] = "Publicando"`, en español y sin i18n, como
todas las demás (§1.4 de la v1.1): la interfaz no pinta `label`.

### 2.2. `PhaseTracker` — quien decide que la fase ocurra

Objeto por run, construido con la fase que traiga el estado. Tres reglas:

1. **Hacia atrás no se emite.** Un nodo puede pedir una fase anterior; el
   tracker la ignora en silencio. Es la garantía E2 hecha mecanismo, no
   disciplina.
2. **Repetida no se emite.** Evita el parpadeo de la píldora.
3. **`execute` exige venir de `awaiting`.** Lanza `PhaseViolation` si no.
   Es R3 (§D3).

El payload de `phase.changed` no cambia: `{phase, label}` (§2 del contrato).

### 2.3. El bucle deja de oscilar

Hoy `_investigate` pone `respond` en cuanto llega texto y vuelve a
`investigate` si después hay herramientas. Eso es un salto hacia atrás y viola
E2 literalmente. **Se cambia**: el texto sigue saliendo por `text.delta` igual
que ahora, pero la fase entra en `respond` cuando el bucle **sabe** que ese
paso fue la respuesta (terminó sin pedir herramientas).

Coste: durante los últimos segundos del texto la píldora dice *Investigando*
en vez de *Respondiendo*. Ganancia: la píldora deja de decir *Respondiendo*
mientras corren tres herramientas, que es la mentira que sí importa — y deja
de parpadear una vez por paso.

### 2.4. `publish` — dónde entra, y por qué ahí

El §2 del contrato pide tres cosas a la vez y sólo hay un sitio que las
cumpla las tres: *la verificación del paso 7 salió verde*, *prepara la segunda
confirmación* y *un turno que solo cambia un prompt nunca entra en `publish`*.
Con `publish` situado entre `verify` y `respond` en el enum, la única
colocación monótona es **después de un `verify` verde**. Se entra en dos casos,
los dos deterministas y los dos del motor:

1. la acción aplicada es `kind: publish` — la publicación está ocurriendo; o
2. la acción aplicada cambió un borrador (`prompt`, `policy`, `tools`,
   `skills`) **y el expediente del hilo tiene un trabajo `publish`** — es
   decir, la persona ya trajo la publicación a esta conversación. Ahí el
   trabajo *desemboca* en publicar y toca preparar la segunda confirmación.

Un cambio de prompt suelto no cumple ninguno de los dos y no entra en
`publish`, que es lo que el contrato exige literalmente.

**Esto es una lectura, y el contrato admite otra.** Está anotado en el §5 como
lo primero que el orquestador debería revisar.

---

## 3. El expediente (§7.1, garantía E1)

### 3.1. El catálogo, literal

`intake.py` implementa el §3.3 palabra por palabra: cinco `work_kind`, sus
`key` obligatorios, y para cada uno `label`, `why` y `examples` (siempre
lista, nunca `null`).

| `work_kind` | `key` obligatorios | Herramienta que lo trae |
|---|---|---|
| `create_client` | `name` · `vertical` · `timezone` · `language` · `forbidden_behaviour` | `console.propose_client` |
| `connect_whatsapp` | `phone_number` · `number_owner` · `channel_role` ¹ | **ninguna** |
| `change_prompt` | `failing_behaviour` · `real_example` | `console.propose_prompt` |
| `enable_connector` | `connector_consent` | `console.propose_tools` |
| `publish` | `ai_disclosure_decision` | `console.propose_publish` |

¹ condicional: obligatorio sólo si el hecho `other_channel_active` está puesto
a `true` en el expediente. Sin el hecho **no se pregunta**: preguntar un
condicional sin condición es preguntar un deducible, y el §3.3 lo prohíbe.

Los deducibles (plantilla, prompt inicial, herramientas del vertical, el resto
del Embedded Signup, el resto del diff, la configuración del conector) no
aparecen en el catálogo y por tanto no se pueden preguntar.

### 3.2. La puerta: **satisfacible ⟹ obligatoria**

E1 dice que un `create_client` sin `forbidden_behaviour` **no llega a `plan`**,
y que falla en el motor. La puerta va en el enrutado de `investigate`: si hay
propuesta pendiente pero al expediente de su `work_kind` le falta un
obligatorio, el turno va a `intake` y **no** a `plan`. El nodo `plan` no corre,
no se persiste ninguna fila y no se emite `hitl.requested`.

Con una salvaguarda que es la diferencia entre una puerta y un atasco: **la
puerta sólo se aplica a un `work_kind` cuyos obligatorios sean satisfacibles**,
es decir, cuando cada `key` obligatoria corresponde a un parámetro que la
herramienta acepta. Se calcula en caliente leyendo el catálogo que el grafo ya
recibe (`toolbelt.specs()`), no con una lista escrita a mano.

Hace falta porque hoy `console.propose_prompt` no acepta `failing_behaviour`
ni `real_example`, y `console.propose_publish` no acepta
`ai_disclosure_decision` (comprobado en `companion/tools/catalog.py`). Sin la
salvaguarda, la puerta bloquearía **para siempre** todo cambio de prompt y toda
publicación: el modelo no tendría por dónde entregar el dato. Con ella:

- `create_client` **está protegido hoy** (sus cinco `key` son parámetros
  reales de `console.propose_client`) — que es lo que E1 exige;
- los otros tres se protegen **solos** el día que E añada los parámetros, sin
  tocar este código;
- `connect_whatsapp` queda declarado e inerte: no existe herramienta que
  proponga conectar WhatsApp.

Está en el §5 como hallazgo para el orquestador.

### 3.3. El evento

`intake.missing` pasa a llevar `{slots, work_kind}` (§3.1 del contrato v2). Lo
emite el nodo `intake` con los slots **que siguen faltando según el
expediente**, no los que la herramienta reportó: un dato dado en el turno
anterior ya no falta, y volver a pedirlo es el ruido que erosiona la
disposición a contestar.

**El catálogo de eventos no es mío** (§8). En mi worktree
`COMPANION_EVENTS["intake.missing"]` todavía no tiene `work_kind`, así que un
test que mirase el publicador saldría rojo por el banco de pruebas, no por el
código. **Mis tests miran lo que el nodo produce.** La comprobación de extremo
a extremo la hace el orquestador en la Fase 2.

### 3.4. La nota de expediente

Cuando el expediente del hilo tiene respuestas guardadas, se añade al final de
`messages` una nota de sistema que las lista. Mismo mecanismo que
`budget_note` y por la misma razón: se **añade**, no reescribe nada, y el
prefijo cacheado sigue encajando.

Sirve para el caso que de otro modo se cae: el modelo vuelve a llamar a
`console.propose_client` en el turno 3 y sólo manda el dato nuevo; sin la
nota, la herramienta ve los otros cuatro vacíos y el usuario tendría que
repetirse. La nota **no autoriza a inventar**: dice literalmente que son datos
que la persona ya dio.

---

## 4. R2, R4, R5 — lo que se mueve al motor

| Regla | Dónde estaba | Qué se añade |
|---|---|---|
| **R2** ambigüedad ⟹ pregunta | prompt (`<ambiguedad>`) + 404 opaco de `client_ref` | La puerta del expediente **es** R2 en el motor: si falta un dato, se pregunta, y ninguna prosa del modelo puede saltárselo. No se añade ningún clasificador de ambigüedad: adivinar si una frase es ambigua con una expresión regular sería la misma alucinación que se quiere evitar |
| **R4** parada al primer fallo, diciendo qué quedó aplicado | una acción por run ⟹ la parada es automática | Faltaba el *diciendo*: ahora el fallo de aplicación viaja al nodo de cierre como un hecho (`execute: {ok: false}`) y el informe al modelo dice **en voz alta que no se aplicó nada**, en vez de dejarle deducirlo de que no hay verificación |
| **R5** publicar es un acto aparte | prompt + `kind: publish` con su propia confirmación | La fase `publish` (§2.4) hace visible el acto separado, y el informe de cierre de un trabajo que desemboca en publicación dice que publicar necesita su propia confirmación |

---

## 4 bis. El nombre de cable (enmienda §17 del contrato v2.1)

Alcance añadido por el orquestador a mitad de la construcción, y cae entero en
esta zona porque es donde se arma la petición del proveedor.

Anthropic rechaza el punto en `tools[].name`
(`^[a-zA-Z0-9_-]{1,128}$`), y las 28 herramientas del catálogo lo llevan. El
catálogo **no se renombra**: se traduce en el límite, `.` → `__`.

Dónde vive: `runtime/companion/tools.py` (`to_wire`, `wire_tools`,
`WireNameCollision`), enganchado en el bucle de `graph.py`.

Cuatro decisiones:

1. **La tabla de vuelta se construye desde el catálogo**, no invirtiendo la
   cadena. Así la vuelta atrás es exacta aunque un nombre futuro traiga algo
   que la inversión no reconstruya.
2. **Una colisión rompe al construir la tabla**, que es al arrancar el turno.
   El fallo alternativo —dos herramientas en el mismo nombre de cable— no da un
   400: despacha la llamada a la herramienta equivocada, en silencio.
3. **El mensaje del asistente y el resultado de herramienta guardan el nombre
   de cable.** Son mensajes del proveedor y vuelven al proveedor tal cual: un
   `tool_use.name` que no coincida con su `tool_result` correlativo es otro
   400. `tool_messages` es el búfer de la conversación con el proveedor, no
   estado semántico; lo que sale a eventos, citas, ejecutor y expediente es
   siempre el nombre del catálogo.
4. **Un nombre sin punto pasa tal cual.** La traducción es idempotente y la
   vuelta cae al propio nombre si no está en la tabla, así que un proveedor
   guionizado que emita nombres de catálogo sigue funcionando.

Tests en `test_companion_loop.py`: el catálogo real recorrido entero (patrón +
vuelta atrás exacta), la colisión, los dos sentidos en un turno, y que el
resultado de herramienta lleva el mismo nombre que el `tool_use`.

---

## 4 ter. El pensamiento que no se puede devolver (enmienda §18 del contrato v2.2)

El segundo 400 del mismo camino, y del mismo tipo: solo se ve con clave real.
Con `display: "summarized"` el proveedor devuelve bloques de **resumen** —
`signature` vacía y `thinking` vacío—, y Anthropic los rechaza al recibirlos de
vuelta.

`_reproducible()` en `graph.py`, justo donde el mensaje del asistente entra en
`messages`. Tres reglas, y la tercera es la que se olvida:

1. se descarta el bloque **sin firma o sin texto**;
2. el bloque firmado vuelve **byte a byte** — no se reconstruye, se reusa el
   objeto. Es la regla que evita el 400 contrario, el de perderlos;
3. si no queda ninguno, **la clave se omite entera**. Una lista vacía no es
   ausencia y no está probada contra el proveedor.

`reasoning.delta` no se toca: el pensamiento que se pinta sale del *stream*, no
del mensaje que vuelve.

**La lección de los §17 y §18 juntos.** Los dos fallos viven en la misma
casilla: *pensamiento activo + herramientas + segundo paso del bucle*, contra el
proveedor real. Ningún proveedor guionizado la ocupa, y por eso ninguna suite
—incluida la mía— los encuentra. Lo que mis tests fijan es que el arreglo se
mantiene; **que el arreglo es el correcto lo dijo la llamada real**, no el test.

---

## 4 quater. La última llamada del turno (enmienda §19.1 del contrato v2.3)

Tercer 400 del mismo camino, y el menos intuitivo:

```
litellm.UnsupportedParamsError: Anthropic doesn't support tool calling
without `tools=` param specified.
```

Si `messages` lleva mensajes de asistente con `tool_calls` —y los lleva: el
turno acaba de investigar y de aplicar— la declaración de herramientas tiene
que seguir presente. **Quitar las herramientas no es la forma de decir "ya no
llames a nada"; la forma es `tool_choice: "none"`**, y hace falta por sí misma:
sin él el modelo *puede* volver a llamar, nadie ejecutaría esa llamada y el
paso de cierre dejaría de serlo.

`_stream_final_answer()` en `graph.py` es ahora el **único** sitio donde se
hace la última llamada de un turno, y lo usan los tres caminos que antes la
hacían por su cuenta:

| Camino | Cuándo | Antes |
|---|---|---|
| `_answer_after_action` | run de continuación, tras aplicar y verificar | sin `tools` — **es donde saltó el 400** |
| `_close_the_turn` | R6, turno agotado | sin `tools` |
| `_answer_without_tools` | CO-01, turno sin herramientas | sin `tools` (correcto, pero por otro motivo) |

Con catálogo declara `tools` + `tool_choice: "none"`; sin catálogo (grafo de
CO-01, sin juego de herramientas) llama por el camino simple — ahí no hay nada
que declarar y tampoco hay historial de herramientas, y un `tools: []` sería
otro cuerpo de petición sin probar.

`make_respond` recibe el `toolbelt` por esto, no por el bucle. Y los `specs`
van **traducidos a nombres de cable**, como en el bucle: el historial que se
reenvía los lleva y las dos cosas tienen que coincidir (§17).

**Lo que esto le costó a mi banco de pruebas.** El doble `FakeActionBelt`
devolvía `specs() == []`, así que la última llamada caía por el camino simple y
el test no podía ver el 400 ni aunque estuviera. Ahora publica un catálogo con
forma de catálogo. Es la tercera vez en esta pasada que el banco medía otra
cosa, y las tres veces se vio comparando contra lo que hace el sistema de
verdad.

---

## 5. Lo que hay que mirar al integrar

Se lista aquí para que no se improvise. Ninguno lo arreglo yo: dos caen fuera
de mi zona y el tercero es una lectura del contrato.

1. ~~**`publish` admite otra lectura**~~ — **cerrado por el §19.5 del contrato
   v2.3**: el rango de fase es **por run, nunca por hilo**. Dentro del run que
   ejecuta el cambio va `verify → publish → respond`, y la publicación se
   propone en el run siguiente, que arranca limpio en `understand` y llega a
   `awaiting` por su propio camino (PLAN-CO-04 D3). El enum no cambia y la
   implementación se queda. La frase vive ahora como comentario sobre
   `PHASE_RANK`, que es donde alguien la volvería a deshacer.
2. **Tres de los cinco `work_kind` no son satisfacibles hoy** (§3.2). Para que
   `change_prompt`, `publish` y `enable_connector` tengan puerta de verdad,
   `catalog.py` (zona de E) necesita los parámetros correspondientes. Mientras
   tanto la puerta se queda dormida sola, sin bloquear a nadie.
3. **`connect_whatsapp` no tiene herramienta.** El catálogo lo declara porque
   el contrato lo declara, pero no hay `propose_*` que lo dispare.
4. **El rastro del run anterior** (§D2) era un defecto vivo. Lo arreglo dentro
   de mi zona, pero conviene que el orquestador lo mire: cambia el
   comportamiento observable de un hilo con HITL previo.

---

## 6. Tests

Todos en la zona de D (`test_companion_{graph,loop,intake}*`).

| Fichero | Qué fija |
|---|---|
| `test_companion_intake.py` (nuevo) | **E1**: `create_client` sin `forbidden_behaviour` no llega a `plan` — sin fila, sin `hitl.requested`, con `intake.missing{work_kind}`. El catálogo cerrado del §3.3. El expediente que sobrevive al turno y no repregunta. La satisfacibilidad |
| `test_companion_graph_phases.py` (nuevo) | **E2**: el enum de 10; `phase.changed` nunca retrocede en ningún camino (solo lectura, intake, HITL confirmado/cancelado, fallo de aplicación); `publish` entra donde dice el §2.4 y no entra en un cambio de prompt suelto; `execute` sin `awaiting` lanza |
| `test_companion_loop.py` (existente) | **E3**: al agotarse tokens/pasos el turno cierra con texto y no a mitad de frase; la puerta dura corta antes de la llamada; el mensaje del asistente sigue volviendo con sus `thinking_blocks` |
| `test_companion_action_graph.py` (existente) | Que C2 y la secuencia del §4.3 siguen intactas, y que el run nuevo no arrastra el `hitl` del anterior |

Base `nexus_test_d`, Redis `/12`. Suite completa una sola vez al cerrar.
