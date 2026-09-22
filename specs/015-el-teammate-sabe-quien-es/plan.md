# Plan de implementación: El teammate sabe quién es, qué día es y qué puede hacer de verdad

**Rama**: `015-el-teammate-sabe-quien-es` | **Fecha**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Entrada**: `specs/015-el-teammate-sabe-quien-es/spec.md` · evaluación cerrada
con `go` en `.specify/assessments/teammate-sabe-quien-es/`

---

## Resumen

El teammate gana **dos mensajes de sistema propios** —identidad en la posición 2,
entorno justo antes del turno— y el texto compartido con el Companion deja de
afirmar capacidades. Lo que el teammate lee sobre sí mismo **se deriva del mismo
cálculo** que decide qué herramientas recibe, así que no puede separarse de la
realidad sin que una puerta lo ponga rojo. Más un campo de instrucciones que
escribe el partner, y una frontera escrita entre lo que se obedece y lo que se
lee.

**Superficie `0`.** Una migración, la última. Nada gasta más salvo unos cientos
de tokens de entrada por turno, acotados por el Requisito 3.

---

## Contexto técnico

**Lenguaje**: Python 3.11 (`apps/api`, `apps/worker`, `uv`) · TypeScript 5 +
React 19 (`apps/desktop`, Electron)

**Dependencias principales**: ninguna nueva. FastAPI, SQLAlchemy 2, Alembic,
LangGraph, LiteLLM, Pydantic v2 — todas ya en el árbol

**Almacenamiento**: PostgreSQL. Una columna nueva en `teammates` y un `CHECK`
que se ensancha en `teammate_changes`

**Pruebas**: `pytest` (unit, integration, isolation) · `vitest` (escritorio)

**Tipo de proyecto**: monorepo — servicio web + trabajador + aplicación de
escritorio

**Objetivo de rendimiento**: sin cambio de latencia. El coste por turno crece
solo el tamaño de los dos bloques nuevos (≈600-1.100 caracteres), y **el texto
compartido se sigue cacheando una vez para todos** (Requisito 3.1)

**Restricciones**: `SYSTEM_PROMPT` estable byte a byte y sin interpolaciones ·
`not_in_catalog` y el recorte por modo no se tocan · dos de los cuatro puntos de
corte de caché de Anthropic ya están en uso en esta ruta

**Escala/alcance**: 44 herramientas · **2⁵ = 32** estados de interruptores × 2
modos × 2 de presencia de máquina = **128 combinaciones**, que la puerta recorre
**enteras**. Son pocas: no hace falta muestrear

---

## Constitution Check

*Puerta rellenada antes de la Fase 0 y re-comprobada tras el diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto; whitelist exhaustiva | ✅ | Ninguna garantía se debilita y **la 2 se refuerza**: `unknown_tool` deja de enumerar las 44 del catálogo y enumera solo las del teammate. Las instrucciones **no amplían el catálogo** (R6.3) y hay test. `test_33_teammate_catalog_is_subset.py` sigue verde sin tocarlo |
| II | Corte por superficie; no se abre una nueva | ✅ | Superficie `0`, declarada en la spec. No hay puerto, ni ruta, ni credencial nueva. La única ruta que cambia de forma es `PATCH /console/teammates/{id}`, que ya existe |
| III | Lo leído es dato, nunca instrucción | ⚠️ **con enmienda razonada** | **Es el punto caliente.** Ver «La frontera del §III» abajo: esta spec no relaja el principio — **escribe una frontera que hoy existe sin estar escrita** (`job` ya mete 80 caracteres del partner en un `role: "system"` desde la spec 003) |
| IV | Acción `mutates` con aprobación durable; auditoría con nombre | ✅ | Editar un teammate ya es `mutates` y ya deja `teammate.updated` con la persona. El campo nuevo entra en `TeammateChange.fields` (R6.6) |
| V | Estados honestos; la ausencia se diseña | ✅ | El campo de instrucciones vacío **no se pinta como pendiente** — es opcional y así se lee. Y R2.5 es §V de frente: un teammate sin herramientas hoy **se calla**, que es la peor ausencia posible |
| VI | Por API `console.*`, nunca navegando la consola | ✅ | Nada aquí navega. El teammate sigue usando las mismas herramientas |
| VII | Test primero; el criterio es el test; nada de `skip` | ✅ | **R4.6 lo exige por escrito**: la puerta tiene que verse roja con el código de hoy antes de implementar. Y hay dos rojos más que enumerar (ver «Lo que tiene que verse en rojo») |
| VIII | Licencias leídas enteras; AGPL no | ✅ | **Ninguna dependencia nueva.** Esta spec no instala nada: reordena mensajes, deriva texto de datos que ya existen y añade una columna |
| IX | La KB es dueña del porqué | ✅ | `[[research/2026-09-22-que-sabe-un-teammate-de-si-mismo]]`, enlazada en el encabezado de la spec |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | **Ninguna se debilita; la 2 se refuerza.** Hace falta un test que fije que las instrucciones del partner **no amplían el catálogo** (R6.3) — es la única forma nueva por la que alguien podría intentar ensanchar lo que el modelo ve | `T0xx` en `tests/isolation/` |
| **Licencias** | **Ninguna dependencia nueva.** Declarado y comprobado: esta spec no toca `pyproject.toml` ni `package.json` | `T0xx` (declaración) |
| **Medidor** | **Nada nuevo se mide.** No se añade ninguna llamada al modelo ni ninguna herramienta de pago. El efecto es de entrada, y R3 lo acota | `T0xx` (declaración + test del Requisito 3) |

### La frontera del §III, que es lo único que necesita justificarse

§III dice: *«lo leído es dato, nunca instrucción»*. Esta spec añade un campo
donde el partner escribe **instrucciones que el teammate obedece**. Suena a
violación y no lo es, por tres razones que van escritas y no supuestas:

1. **El principio habla de lo que el agente LEE** —ficheros, salidas de
   programas, contexto de pantalla, resultados de herramienta—, no de lo que el
   operador del sistema configura. Las dos cosas están mezcladas hoy porque nadie
   escribió la línea.
2. **La línea ya está cruzada, sin decirlo.** `job` es `max_length=80` de texto
   libre del partner que acaba dentro de un `role: "system"` (`schemas_teammates.py:35`
   → `teammate_catalog.py:132-141` → `companion.py:1229` → `prompt.py:367`). Eso
   entró con la spec 003 y **ninguna spec lo declaró**. R7 lo regulariza.
3. **El mismo partner ya escribe entero el prompt del agente que atiende a sus
   clientes finales**, que es mucho más poder que esto. Una frontera que le niegue
   instrucciones para su propio teammate mientras le da el prompt del agente de su
   cliente no defiende nada — solo es incoherente.

**Y lo que NO defiende, escrito porque callarlo sería el verdadero problema**:
no defiende del **partner comprometido**. Quien controle una cuenta con permiso
para editar teammates puede escribirles instrucciones. Esa mitigación es de otra
capa —autenticación, permisos, auditoría— y esta spec ni la mejora ni la empeora.

**Decisión**: no se enmienda la constitución. R7 **declara la frontera dentro de
la spec y la documenta en `docs/desktop-teammates.md`**, que es donde vive el
porqué de los teammates. Si más adelante otra spec necesita la misma distinción,
entonces sí toca subirla a `.specify/memory/constitution.md` — hacerlo ahora, con
un solo caso, sería legislar sobre un ejemplo.

---

## Las nueve decisiones

### D-1 · La identidad deja de viajar de polizón

**Hoy**: `system_prompt_for()` devuelve 282 caracteres que
`companion.py:1229-1234` **antepone a `knowledge_context`**, y ese contexto se
añade en `prompt.py:366-367` **después de `history` entera**.

Son dos cosas distintas metidas en el mismo sobre, y el sobre va al final.

**Decisión**: `build_messages` gana un parámetro propio, `identity`, que se
inserta **inmediatamente después del prefijo y antes de la historia**. El
conocimiento **se queda donde está** — es material de consulta y su sitio es
cerca del turno, no al principio.

**Por qué separarlos y no mover los dos**: el conocimiento puede ser largo y
cambia con el cliente del contexto; la identidad es corta y constante para todo
el hilo. Juntos, o la identidad llega tarde o el conocimiento se cachea sin
poder. Separados, cada uno va donde le toca.

**Quién la construye**: se queda en `services/teammate_catalog.py`, que es quien
ya conoce al teammate y su catálogo. Mudarla obligaría a leer el catálogo dos
veces desde dos sitios, que es exactamente cómo nacen las dos fuentes que el
Requisito 2.1 prohíbe.

**Rechazado — meterla en `SYSTEM_PROMPT`**: daría un prefijo por teammate,
ninguno reutilizado, y `test_companion_graph.py:49` lo congela por esa razón.
**Rechazado — dos prefijos**: 7 KB copiados que divergen; este repositorio acaba
de pagar por un vocabulario escrito dos veces (spec 012, `WorkstationAction`).

### D-2 · Dos puntos de corte en la cabecera, y el segundo es el que ahorra

**Esto es lo que la evaluación midió y por qué la decisión obvia es cara.**

`_with_prompt_caching` (`llm.py:204-249`) **fusiona todos los mensajes de sistema
iniciales contiguos** en un solo mensaje con bloques, y pone **un**
`cache_control` en el último. Un mensaje de identidad en la posición 2 es un
mensaje de sistema inicial contiguo: se fusionaría, el corte se movería detrás de
él, y **los 7 KB compartidos se escribirían una vez por teammate**.

**Decisión**: dos puntos de corte en la cabecera —uno tras el último bloque del
texto compartido, otro tras el bloque de identidad—. El primero lo comparten
todos los teammates y el Companion; el segundo es propio de cada teammate y solo
escribe su delta.

> **El vocabulario, fijado aquí para los cinco documentos.** Se numeran **por
> posición**, como en el contrato: **corte 1** tras el texto compartido, **corte
> 2** tras la identidad, **corte 3** el móvil del final (`_cache_the_tail`). El
> que esta spec añade es el **corte 2**. Llamarlo «el tercero» —porque es el
> tercero que existirá— también es cierto y **no se usa**: dos números para la
> misma cosa es cómo alguien implementa el que no era.

**Hay sitio, y está contado**: Anthropic admite cuatro por petición. Esta ruta usa
**dos** hoy —el del prefijo y el móvil de `_cache_the_tail`, que está encendido
solo aquí (`companion.py:1720`, `cache_tail=True`)—. El corte 2 cabe.

**Quién lo decide**: `llm.py`. Quien arma los mensajes no sabe de caché y no
debe: `prompt.py` decide **el orden**, `llm.py` decide **dónde se corta**. Hoy ya
es así y no hay razón para romperlo.

**Cómo se comprueba sin llamar al proveedor (R3.2)**: `_with_prompt_caching` es
una función pura de lista a lista. El test le da una lista con prefijo +
identidad + historia y afirma **dónde caen los `cache_control` y qué queda en
cada tramo**. Es la misma forma que ya tienen los tests del prefijo.

### D-3 · La enumeración sale de donde sale el catálogo, o no sale

**Decisión**: una función nueva **al lado de `for_teammate`**, en
`teammate_catalog.py`, que recibe lo mismo que `for_teammate` y devuelve la
descripción por familias. Las dos leen `ALL_TOOLS`, `READ_TOOLS`,
`PROPOSE_TOOLS`, `TRIAL_TOOLS`, `APPLY_TOOLS` y `MACHINE_TOOL` del mismo módulo.

**Por qué al lado y no dentro**: `for_teammate` devuelve nombres y lo consume el
toolbelt; la descripción devuelve prosa y la consume el prompt. Un solo retorno
mezclado obligaría a todos los llamantes a cargar con lo que no usan.

**Qué se dice de lo que falta, y de dónde sale «qué lo cambiaría»**: los cinco
interruptores ya tienen nombre técnico (`read`, `write`, `publish`, `spend`,
`contact`) y el escritorio ya los traduce a algo legible (`apps/desktop/src/app/i18n.ts`).
La descripción **dice el nombre legible del interruptor**, no el técnico, y para
`shell_local` dice la condición real: vincular una máquina y que esté presente.

> **Cuidado documentado**: ese mapa interruptor→texto es **una segunda fuente en
> potencia**. Vive en el mismo módulo que las familias, con el comentario de por
> qué, y la puerta de D-8 lo recorre. Si crece un interruptor y el mapa no, falla.

### D-4 · Qué se le quita exactamente al prefijo

`prompt.py:108-121` es `<lo_que_puedes_hacer_ahora>` y tiene **tres partes
distintas** mezcladas:

| Parte | Qué dice | Qué se hace |
|---|---|---|
| Afirmación de lecturas (`:109-114`) | «Tienes herramientas de **lectura** sobre la consola: puedes consultar…» | **Se va.** Es falsa para tres de las cinco combinaciones |
| Afirmación de propuestas (`:116-118`) | «Y tienes herramientas de **propuesta**: dar de alta un cliente…» | **Se va.** Ídem |
| Lo prohibido siempre (`:128-131`) | «borrar clientes, tocar facturación o el plan, crear o rotar claves, enseñar una clave en el chat, y desactivar la revelación de IA» | **Se queda.** Es verdad para todos, no depende de ningún interruptor, y es lo que protege |
| El párrafo del pack (`:119`) y el de la propuesta (`:121-126`) | Cómo funciona proponer y que aplicar lo hace el motor tras confirmar | **Se queda.** Describe el mecanismo, no promete tener nada |

**Lo que lo sustituye**: una frase que remite al bloque propio —*lo que puedes
hacer te lo dice tu propio bloque; esto es lo que nadie puede hacer nunca*—. Es
una afirmación que **no caduca con el catálogo**, que es todo el punto.

**El mínimo cacheable, medido y no estimado**: el bloque que se retira son
**631 caracteres exactos** (de «Tienes herramientas de» hasta «Un pack es un
YAML»). El prefijo pasa de **7.044 a 6.413**, que sigue muy por encima del
mínimo cacheable. **Aun así hay tarea de verificación**, porque la conversión a
tokens sigue siendo por caracteres y no por el contador del proveedor.

### D-5 · La `<regla_madre>` se matiza en el bloque propio, no en el prefijo

`prompt.py:158-172` ordena «Si no lo has leído en este turno con una herramienta,
no lo afirmes». Para un teammate con cero lecturas eso es **silencio**.

**Decisión**: la regla **no se toca en el prefijo**. El bloque de identidad, que
es por teammate, añade la salida cuando corresponde: *no tienes lecturas, así que
no puedes comprobar nada — dilo y di qué haría falta*.

**Por qué ahí y no en el prefijo**: el prefijo es compartido y cacheado, y esta
excepción **solo aplica a algunos teammates**. Meterla arriba obligaría a
escribir una condición en un texto que por contrato no tiene condiciones — y
sería el mismo error de la prosa incondicional, con el signo cambiado. Y
tocarla afecta también al Companion, que siempre tiene lecturas y para el que la
regla está bien como está.

### D-6 · La zona horaria viaja aparte, no en el contexto de página

`PAGE_CONTEXT_KEYS` son cuatro (`route`, `client_ref`, `tab`, `selection`) y el
esquema es **cerrado**: `_canonical_page_context` descarta lo demás. Sería fácil
añadir una quinta clave.

**Decisión: no.** El contexto de página **se valla con `fence_only`** porque lleva
nombres de cliente y títulos escritos por terceros. Una zona horaria es un
identificador IANA que **el sistema valida**, no texto de tercero. Meterla en la
caja vallada sería decirle al modelo que desconfíe de un dato que sí es fiable —
y, peor, normalizaría mezclar dentro de la valla cosas que no son del mismo tipo.

La zona viaja **como parte del bloque de entorno**, que es el sitio que D-1 crea
y que existe justo para esto.

**`_now_note` se reutiliza, no se copia.** Vive en `runtime/pipeline.py:652-673`,
es una función pura de `(zona, ahora) → texto`, y ya resuelve lo difícil: el día
de la semana en español, el ISO, la instrucción de no deducir el año, y el
repliegue a UTC **con aviso** cuando la zona viene malformada (`:657-662`).

> **Y hay un detalle de arquitectura que hay que nombrar**: `pipeline.py` es del
> worker y el companion lo consume desde `apps/api`. Ese cruce **ya existe** —
> `companion.py:1712` importa `nexus_worker.runtime.llm`— así que no se inventa
> una dependencia. Lo que sí hace falta es **mover `_now_note` a un módulo que
> nombre lo que hace** en vez de importarlo de `pipeline`, que es el grafo del
> agente de canal entero. Copiarlo sería la tercera fuente del mismo texto.

### D-7 · El campo de instrucciones, y el `CHECK` que casi se escapa

**La columna**: `instructions`, `Text`, **nullable**, sin `server_default`. Nula
significa «no escritas», que es distinto de cadena vacía, y el Requisito 6.2
depende de esa distinción.

**El tope: 4.000 caracteres.** Defendible por dos vías y no por gusto:
- Son ≈1.000 tokens, que caben de sobra en el segundo tramo de caché sin
  acercarse al tamaño del prefijo compartido (7.044 caracteres).
- Es cincuenta veces `job` (80) y dos veces el prompt más largo de las plantillas
  verticales que un partner ya escribe hoy. Si alguien necesita más, lo que quiere
  es conocimiento, no instrucciones — y eso ya existe.

Se valida en el esquema (`Field(max_length=4000)`) y **se anuncia en el
formulario antes de rebasarlo** (R6.5), nunca se trunca en silencio.

**El `CHECK` que casi se escapa, y es el de la lección de la spec 012.**
`TeammateChange` tiene:

```
CheckConstraint("fields <@ ARRAY['job', 'permissions', 'local_exec', 'model']::text[] …")
```

(`db/models/teammate.py:110-116`). Registrar un cambio de instrucciones
**violaría esa restricción**. Hay que ensancharla en la misma migración, y hay
**tres sitios más** que enumeran los mismos cuatro valores y tienen que crecer a
la vez:

| Dónde | Qué es |
|---|---|
| `db/models/teammate.py:113` | el `CHECK` |
| `apps/desktop/src/app/bridge.ts:79` | la unión `"job" \| "permissions" \| "local_exec" \| "model"` |
| `apps/desktop/src/app/i18n.ts:115` | `changes.field.*`, el texto de cada campo |
| `apps/desktop/src/app/routes/change-notes.tsx:37` | la frase que los enumera |

> Es **exactamente** la forma del defecto que la spec 012 pagó: un vocabulario
> escrito en cuatro sitios, dos lenguajes, sin constante compartida. Aquí se
> conoce de antemano, así que va enumerado en el plan y **con una tarea que lo
> barre**, no con buena voluntad.

**El vocabulario de auditoría NO necesita migración**: `teammate.updated` ya
existe (`0110_teammate_audit_vocab.py:32`) y es la acción que ya se escribe al
editar. Lo que cambia es qué campos se nombran, no qué acción se registra.
*(Comprobado leyendo la migración, que es lo que faltó en la spec 012.)*

### D-8 · La puerta, escrita al revés

Primero **qué cambio futuro tiene que ponerla roja**, y de ahí la forma:

| Cambio futuro | ¿Lo caza? | Cómo |
|---|---|---|
| Añadir una herramienta al catálogo sin tocar la descripción *(pasó el 2026-09-20 con `shell_local`)* | ✅ | La herramienta nueva no cae en ninguna familia descrita |
| Mover una herramienta de familia *(pasó con `console.apply`)* | ✅ | La descripción de la combinación deja de coincidir con `for_teammate` |
| Añadir un interruptor sin ampliar el mapa a texto legible | ✅ | La combinación nueva produce una descripción sin nombre |
| Devolver prosa incondicional al prefijo | ✅ | Mitad (a): barrido de texto sobre `SYSTEM_PROMPT` |
| Renombrar una herramienta citada en el prefijo | ✅ | Ya lo cubre la mitad (a) ampliada |

**Forma**: dos mitades en el mismo fichero.
- **(a)** El texto compartido **no afirma capacidades**: barrido sobre
  `SYSTEM_PROMPT` buscando las formas de afirmación que se retiran en D-4.
- **(b)** Recorrido de **las 128 combinaciones** (2⁵ estados de interruptores × 2
  modos × máquina presente/ausente) comparando la descripción generada contra
  `for_teammate`. Son pocas y baratas: se recorren enteras, no se muestrean. Cada herramienta que `for_teammate` entrega tiene que estar
  cubierta por una familia descrita, y ninguna familia descrita puede cubrir
  herramientas que no se entregan.

**Dónde vive**: `apps/api/tests/isolation/`. No toca RLS, pero **es la costura del
principio «la whitelist de herramientas es exhaustiva»** — la garantía 2 — y ese
es el sitio donde este repositorio pone las costuras de los principios. Precedente
directo: `test_33_teammate_catalog_is_subset.py`, que vigila lo mismo un paso más
abajo.

**R4.6 exige verla en rojo.** Con el código de hoy la mitad (a) falla
inmediatamente —las dos afirmaciones están ahí— y la (b) no puede ni
construirse, porque la función que describe no existe. La tarea tiene que
**dejar constancia del rojo** antes de implementar.

### D-9 · Dónde se escribe la frontera del §III

**Decisión**: en **`docs/desktop-teammates.md`**, que es la spec viva de los
teammates y donde ya vive el porqué de su catálogo y sus permisos. Sección
propia, con los tres puntos del Constitution Check de arriba **y el párrafo de
contra quién no protege**.

**La constitución no se enmienda ahora.** Legislar §III sobre un solo caso es
peor que declararlo en la spec: si una segunda spec necesita la misma distinción,
ahí ya hay patrón y la enmienda se escribe con dos ejemplos en vez de uno.

`docs/desktop-teammates.md` **se actualiza en el mismo commit** que cambia lo que
describe — regla de la spec viva, `docs/spec-driven-development.md` §3.

---

## Lo que tiene que verse en rojo antes de implementar (§VII)

Tres rojos, y ninguno es el camino feliz:

1. **La puerta, mitad (a)** — falla hoy porque las dos afirmaciones están en el
   prefijo. Es el rojo que R4.6 exige por escrito.
2. **La derivación por familias** — el test de R2 se escribe contra una función
   que no existe. Falla por `ImportError`, que **no cuenta**: tiene que fallar
   por la aserción, así que primero va la firma vacía.
3. **Las instrucciones no amplían el catálogo (R6.3)** — es el test de
   aislamiento, y **no se prueba por el camino feliz**. Hay que escribirle a un
   teammate instrucciones que pidan explícitamente una herramienta que no tiene y
   comprobar que el catálogo no se mueve. Si pasa sin haber intentado el ataque,
   no está probando nada.

---

## Orden de entrega

Los cuatro tramos de la evaluación, cada uno soltable solo:

| # | Historia | Qué deja entregado | Migración |
|---|---|---|---|
| 1 | **H1** — lo que dice tener es lo que tiene | La identidad en su sitio, las capacidades derivadas, el prefijo callado, `unknown_tool` acotado | No |
| 2 | **H2** — la puerta | El desajuste no vuelve | No |
| 3 | **H3** — sabe cuándo está | Fecha, hora, zona, máquina | No |
| 4 | **H4** — instrucciones propias | Dos teammates con los mismos permisos son dos agentes | **Sí, la única** |

**H1 no depende de nada de H4**, y se ha comprobado: H1 toca el armado del turno
y la derivación; H4 toca la tabla y el formulario. La única costura entre ellas
es que H4 mete texto **dentro del bloque que H1 crea** — una línea, no una
dependencia de diseño.

**H2 va inmediatamente después de H1 y no al final**, aunque sea «solo tests»:
sin ella, H1 se degrada con el primer catálogo que alguien toque, y el trabajo se
deshace solo.

---

## Estructura del proyecto

### Documentación de esta feature

```text
specs/015-el-teammate-sabe-quien-es/
├── plan.md              # este fichero
├── spec.md
├── research.md          # Fase 0
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/
│   └── lo-que-el-teammate-lee.md
└── checklists/requirements.md
```

### Código (raíz del repositorio)

```text
apps/api/src/nexus_api/
├── services/teammate_catalog.py      # D-1, D-3: identidad + descripción por familias
├── companion/tools/runner.py         # R2.6: unknown_tool acota a las suyas
├── api/console/companion.py          # D-1: la identidad deja de ir pegada al conocimiento
├── api/console/schemas_teammates.py  # D-7: instructions, max_length=4000
├── api/console/teammates.py          # D-7: PATCH lo acepta y lo registra
├── db/models/teammate.py             # D-7: columna + CHECK ensanchado
└── alembic/versions/0127_*.py        # la ÚNICA migración, y va en H4

apps/worker/src/nexus_worker/runtime/
├── companion/prompt.py               # D-1: parámetro identity · D-4: el prefijo calla
├── llm.py                            # D-2: el corte 2, tras el bloque de identidad
└── turn_clock.py                     # D-6: _now_note sale de pipeline.py a su propio módulo

apps/desktop/src/app/
├── routes/new-teammate.tsx           # D-7: el campo, opcional
├── routes/teammate-settings.tsx      # D-7: ídem
├── routes/change-notes.tsx           # D-7: el cuarto sitio del vocabulario
├── bridge.ts                         # D-7: la unión de campos
└── i18n.ts                           # D-7: changes.field.instructions + el tope

apps/api/tests/
├── isolation/test_40_prompt_matches_catalog.py   # D-8, las dos mitades
├── isolation/test_41_instructions_do_not_widen.py # R6.3
└── unit/…                                         # D-2 (puntos de corte), D-3, D-6

docs/desktop-teammates.md             # D-9: la frontera del §III, mismo commit
```

**Decisión de estructura**: **la consola no se toca**. Lo comprobé al planificar y
**corrige una premisa mía**: el formulario del teammate vive en
`apps/desktop/src/app/routes/`, no en `apps/console`. La consola solo consume la
API de teammates (`lib/backend/teammates.ts`) y retransmite el inbox; ninguna
pantalla suya edita un teammate. Se tocan **tres** aplicaciones: `apps/api`,
`apps/worker` y `apps/desktop`.

---

## Verificación

`./scripts/verify.sh` entero. **Aquí el worker se toca de lleno**, que es
exactamente donde este repositorio ha roto la tubería dos veces —y las dos por lo
mismo: no correr el worker y no correr `mypy --strict`—.

Lo que se mueve, por suite:

| Suite | Por qué |
|---|---|
| `pytest · api` | catálogo, runner, companion, esquemas, migración, las dos puertas nuevas |
| `pytest · worker` | **el prompt y el armado de mensajes** — la suite que se olvida |
| `mypy --strict` | firmas nuevas en tres módulos; la otra que se olvida |
| `desktop · test` | el formulario, el puente y las notas de cambio |
| `desktop · typecheck` | la unión de campos, que es un tipo |
| `consola · next build` | no debería moverse; se corre igual, porque «no debería» no es una comprobación |

**Una sola ejecución de `pytest` a la vez**: las suites de integración y
aislamiento comparten la base de desarrollo.

---

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple, y por qué se rechaza |
|---|---|---|
| El **corte 2** de caché, tras la identidad | Sin él, los 7 KB compartidos se escriben una vez por teammate — medido, no supuesto | Dejar solo el corte 1 (lo de hoy): funciona y **multiplica el coste por el número de teammates**. La spec lo prohíbe en R3.1 |
| `turn_clock.py`, módulo nuevo | `_now_note` vive dentro del grafo del agente de canal y ahora lo usan dos agentes | Importarlo de `pipeline.py`: ataría el companion al grafo entero del canal. Copiarlo: tercera fuente del mismo texto, que es el defecto que esta spec viene a cerrar |
| Un **mapa interruptor→texto legible** | R2.3 exige decir «qué lo cambiaría», y los nombres técnicos no sirven para eso | Enseñar el nombre técnico: el partner no los conoce — los ve traducidos en la aplicación |
