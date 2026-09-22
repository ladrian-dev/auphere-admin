# Fase 0 — Lo que se midió antes de decidir

**Spec**: 015 · **Fecha**: 2026-09-22

> La evidencia de fondo está en `.specify/assessments/teammate-sabe-quien-es/research.md`
> y no se repite. Esto es lo que hubo que **medir al planificar**, porque una
> decisión del plan dependía del número.

---

## M-1 · El punto de corte del caché

**Pregunta**: ¿un mensaje de sistema en la posición 2 rompe el caché, lo
encarece, o da igual?

**Cómo se midió**: leyendo `_with_prompt_caching`
(`apps/worker/src/nexus_worker/runtime/llm.py:204-249`) y siguiendo sus
llamantes hasta el proveedor que usa esta ruta.

**Lo que se encontró**:

1. La función **fusiona todos los mensajes de sistema iniciales contiguos** en
   uno solo con bloques de texto, y pone **un** `cache_control` en el último
   bloque (`:220-243`).
2. Un `cache_control` cachea **todo el prefijo hasta él** (`:209-211`).
3. El proveedor de esta ruta se construye en `api/console/companion.py:1720` con
   `cache_tail=True`, así que **ya usa dos** de los cuatro puntos que Anthropic
   admite: el del prefijo y el móvil de `_cache_the_tail`.
4. El docstring de `_cache_the_tail` (`llm.py:176-179`) lo dice literalmente:
   *«Anthropic admite cuatro puntos por petición y el prefijo usa uno; este es el
   segundo.»*

**Conclusión, y no es la que se suponía**: la identidad en la posición 2 **no
rompe** el caché — cae **dentro** de él. Y eso es peor de lo que parece: como la
identidad varía por teammate, **cada teammate tendría su propia entrada de caché
de 7 KB** en vez de compartir una.

**Qué cambia**: el **corte 2** —el que va tras la identidad— deja de ser un
detalle de implementación y pasa a ser **parte del requisito** (R3.1). Hay
sitio: quedan dos libres.

> Los cortes se numeran **por posición** en los cinco documentos: corte 1 tras
> el texto compartido, corte 2 tras la identidad, corte 3 el móvil del final.
> El vocabulario lo fija `plan.md` §D-2.

---

## M-2 · El tamaño de lo que se le quita al prefijo

**Pregunta**: quitar las afirmaciones de capacidad, ¿deja el prefijo por debajo
del mínimo cacheable?

**Cómo se midió**: ejecutado contra `SYSTEM_PROMPT`, recortando desde «Tienes
herramientas de» hasta «Un pack es un YAML».

| Medida | Valor |
|---|---|
| Prefijo hoy | **7.044 caracteres** |
| Bloque que se retira | **631 caracteres** |
| Prefijo después | **6.413 caracteres** |

**Conclusión**: sobra margen. El módulo afirma que el prefijo «supera de sobra el
mínimo cacheable de Opus 5 (512 tokens)» y 6.413 caracteres siguen estando muy
por encima.

### Y ahora en tokens, no en caracteres (T003, cerrada el 2026-09-22)

| Medida | Tokens |
|---|---|
| Prefijo hoy | **1.879** |
| Prefijo tras retirar el bloque | **1.724** |
| Mínimo cacheable de Opus 5 | 512 |

**Margen: 3,4×.** El recorte se lleva 155 tokens y no acerca el prefijo al
mínimo ni de lejos.

> **La salvedad, dicha y no escondida**: se midió con `tiktoken` (`cl100k_base`),
> que es el tokenizador de OpenAI, no el de Anthropic. Los dos difieren en unos
> pocos puntos porcentuales sobre texto en español — **suficiente para un margen
> de 3,4×, insuficiente si algún día el prefijo bajara cerca de 600 tokens**.
> Quien lo lleve ahí tiene que medir con el contador de verdad, no con esto.

---

## M-3 · Cuántas combinaciones tiene que recorrer la puerta

**Pregunta**: ¿se pueden recorrer todas, o hay que muestrear?

**Cómo se midió**: contando los ejes reales en
`services/teammate_catalog.py`.

| Eje | Valores |
|---|---|
| Interruptores (`read`, `write`, `publish`, `spend`, `contact`) | 2⁵ = **32** |
| Modo (`build`, `consult`) | **2** |
| Máquina presente | **2** |
| **Total** | **128** |

**Conclusión**: se recorren **enteras**. 128 casos en un test parametrizado son
baratos, y muestrear sería dejar un agujero por donde no se mira — que es
justamente el fallo que esta puerta existe para evitar.

**Se comprobó además que no hay más ejes escondidos**: `for_teammate` recibe
exactamente `teammate`, `mode` y `machine_present`, y lo único que lee del
teammate es `tool_names` y `local_exec`. `tool_names` se deriva de los
interruptores en `permissions_to_tool_names`, así que no es un eje libre.

---

## M-4 · El `CHECK` de `teammate_changes`

**Pregunta**: ¿basta con añadir la columna, o hay algo más que se rompe al
registrar un cambio de instrucciones?

**Cómo se midió**: leyendo el modelo antes de escribir la migración —**la lección
directa de la spec 012**, donde el vocabulario de auditoría sembrado por
migración costó una enmienda a mitad de implementación.

**Lo que se encontró** (`db/models/teammate.py:110-116`):

```
CheckConstraint(
    "fields <@ ARRAY['job', 'permissions', 'local_exec', 'model']::text[] "
    "AND array_length(fields, 1) >= 1",
    name="teammate_changes_fields_check",
)
```

Registrar un cambio de instrucciones **violaría la restricción**. Y el mismo
vocabulario de cuatro valores está escrito en **otros tres sitios**, en
TypeScript, sin constante compartida:

| Dónde | Qué |
|---|---|
| `apps/desktop/src/app/bridge.ts:79` | la unión de tipos |
| `apps/desktop/src/app/i18n.ts:115` | `changes.field.*` |
| `apps/desktop/src/app/routes/change-notes.tsx:37` | la frase que los enumera |

**Conclusión**: la migración ensancha el `CHECK`, y hay **una tarea que barre los
cuatro sitios**. Es exactamente la forma del defecto que la spec 012 pagó con un
cliente muerto que sobrevivió al barrido — aquí se conoce de antemano.

**Y lo que NO hace falta**: el vocabulario de auditoría no se toca.
`teammate.updated` ya existe (`0110_teammate_audit_vocab.py:32`) y es la acción
que ya se escribe al editar un teammate. Cambia qué campos se nombran, no qué
acción se registra. *(Comprobado leyendo la migración, que es justo lo que no se
hizo en la 012.)*

---

## M-5 · Dónde vive el formulario del teammate

**Pregunta**: ¿qué aplicación hay que tocar para el campo de instrucciones?

**Por qué se midió**: porque yo había escrito «el formulario del teammate, en
`apps/console`» al encargar el plan, **y era falso**.

**Lo que se encontró**:

- El formulario vive en **`apps/desktop`**:
  `src/app/routes/new-teammate.tsx` y `src/app/routes/teammate-settings.tsx`.
- La consola **no edita teammates**. Solo consume la API
  (`lib/backend/teammates.ts:144-165`) y retransmite el inbox
  (`app/api/teammates/inbox/stream/route.ts`). Cero coincidencias de
  `rosterCreate`, `rosterUpdate` o un formulario en `apps/console/src`.

**Conclusión**: se tocan **`apps/api`, `apps/worker` y `apps/desktop`**. La
consola no. Se corre igual su `next build`, porque «no debería moverse» no es una
comprobación.

---

## M-6 · `_now_note` y de dónde sacarlo

**Pregunta**: ¿se reutiliza el bloque de fecha del agente de canal o se copia?

**Lo que se encontró** (`apps/worker/src/nexus_worker/runtime/pipeline.py:652-673`):
es una función **pura** de `(nombre de zona, ahora) → texto`. Resuelve lo difícil
—día de la semana en español, ISO, la instrucción de no deducir el año, y el
repliegue a UTC **con marca visible** cuando la zona viene malformada
(`:657-662`)—. Y no depende de nada del grafo del canal.

**El cruce de paquetes ya existe**: `api/console/companion.py:1712` ya importa
`nexus_worker.runtime.llm`. No se inventa una dependencia nueva.

**Conclusión**: se **mueve** a un módulo que nombre lo que hace
(`runtime/turn_clock.py`) y los dos agentes lo importan de ahí. Importarlo de
`pipeline` ataría el companion al grafo entero del canal; copiarlo crearía la
tercera fuente del mismo texto, que es el defecto que esta spec viene a cerrar.
