# Bug Fix: el teammate alcanza la máquina, y ve lo que pasó

- **Slug**: el-teammate-no-alcanza-la-maquina
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied (D1, D2, D3). **D4 pendiente**, ver abajo.

## Summary

Tres cosas, y las tres hacen falta para que la cuarta —que el teammate trabaje—
signifique algo: la herramienta llega al catálogo cuando hay máquina, lo que el
programa imprime llega al modelo, y esa salida ya incluye stderr y el final.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `services/device_presence.py` | añadido | `principal_presence()`: ¿tiene **esta persona** una máquina lista? Hermana de `tenant_presence`, un eje más arriba |
| `api/console/companion.py` | modificado | `_machine_present_for()` y los dos sitios que tenían `False` a mano |
| `runtime/companion/graph.py` | modificado | El nodo `execute` mete el resultado en `tool_messages`, marcado `untrusted` |
| `apps/desktop/src/executor.ts` | modificado | `OUTPUT_SAMPLE_LIMIT = 16 KB`, los dos flujos, y `clampSample()` con cabeza y cola |
| `core/local_exec_limits.py` | añadido | `OUTPUT_SAMPLE_CHARS`, el techo en **un** sitio |
| `apps/desktop/src/http-transport.ts` · `api/device_bridge.py` · `companion/tools/runner.py` | modificado | Todos apuntan a esa constante |
| `tests/integration/test_teammate_reaches_the_machine.py` | añadido | 8 casos: latido, caducidad, sin directorio, revocada, sin máquina, y el catálogo siguiendo a la máquina |
| `tests/unit/test_teammate_sees_what_it_ran.py` | añadido | 2 casos: la salida llega, y llega marcada como dato |
| `apps/desktop/tests/executor-sample.test.ts` | añadido | 5 casos: stderr, los dos flujos, el final sobrevive, hay techo, y el recorte se declara |
| `apps/desktop/tests/executor.test.ts` | modificado | La guarda de §III sigue, contra el techo nuevo |

## Las cuatro decisiones que no son obvias

**1. La salida va al modelo pero no a la base de datos.**

`tool_messages` vive en el estado del turno. La auditoría sigue diciendo **qué** se
ejecutó y nunca **qué dijo** el comando. Eso es lo que legitima guardar el hilo de un
teammate (migración 0090), y no se toca. El agente ve el error de compilación; el
registro permanente, no.

**2. Viaja marcada `untrusted: true`.**

§III. Un `README` hostil en el repositorio del partner no manda sobre la máquina del
partner. El runner ya añadía esa nota al contenido de `shell_local`; ahora la marca
viaja también en el mensaje que llega al modelo.

**3. El techo subió de 2 KB a 16 KB, y eso cambia un invariante declarado.**

`executor.test.ts` tenía un test llamado «la salida no se guarda (§III)» que afirmaba
`≤ 2048`. **No se ha borrado**: sigue afirmando que hay techo, contra el número
nuevo, con el porqué al lado. Lo que se defiende ahí es *acotada, no transcripción*, y
eso sigue en pie: 16 KB es una traza de compilación, no un `find /`.

La marca de recorte cuenta **dentro** del techo, no encima. Así `OUTPUT_SAMPLE_LIMIT`
es el tamaño de lo que sale y nadie tiene que acordarse de sumar un margen en los
cuatro sitios por donde pasa.

**3 bis. La constante vive en `core/`, y eso lo decidió un test.**

El primer intento la puso en `services/local_dispatch.py`, que es donde parecía
tener dueño. La suite de aislamiento lo tumbó:
`test_companion_tools_imports.py` prohíbe que un módulo de herramientas del
Companion importe de `services/` o de `repositories/` —garantía C2: una herramienta
llama al router por HTTP en proceso, nunca al servicio, o se salta de golpe la
validación, `client_scope`, el limitador, la cuota, la auditoría y la cobertura
automática de `test_console_scope`—.

Un número que hace falta **a los dos lados de una frontera de capas** no puede vivir
en ninguno de los dos: se copia, y las copias divergen. Por eso
`core/local_exec_limits.py`.

**4. Cabeza y cola, no los primeros 16 KB.**

Cuando la salida es larga, el motivo está al final; el principio es el banner de la
herramienta. Y el hueco se **declara** («recortado: N caracteres omitidos»): callarlo
sería peor que recortar, porque el modelo leería el trozo como si fuera todo.

## Lo que este arreglo NO hace

- **D4 · `cwd_relative` sigue perdiéndose.** La puerta lo valida contra fugas
  (`..`, rutas absolutas, `~`) y el puente manda `None` fijo, así que todo corre en la
  raíz del directorio del cliente. Arreglarlo pide **columna nueva en
  `local_executions` y su migración**, más pasarlo por `dispatch()` y por el poll. Es
  el único de los cuatro que no impide trabajar, y por eso se separa en vez de
  colarlo aquí sin ensayar la migración.
- **No hay continuación autónoma.** Tras aprobar, el turno responde y termina: cada
  paso lo sigue pidiendo una persona. Es de las cosas que Luis pidió el 2026-09-20 y
  entra por `.specify/assessments/teammate-que-trabaja-en-la-terminal/`.
- **La latencia por sondeo sigue siendo de 0 a 10 s por comando**, y el proceso sigue
  siendo nuevo en cada llamada: sin `cd`, sin variables, sin servidor levantado entre
  pasos. Esa es justamente la pregunta de esa evaluación, y ahora se puede medir sin
  el ruido que metían D2 y D3.

## Deuda de documentación, en este mismo commit

`docs/desktop-teammates.md` decía «una **muestra acotada** de la salida» y que ésta
«llega al modelo». Lo primero sigue siendo verdad con otro número; lo segundo **no
era verdad** hasta hoy. El documento se actualiza aquí, que es la regla del repo:
si cambias lo que un documento describe, el documento va en el mismo commit.
