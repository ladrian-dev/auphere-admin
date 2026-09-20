# Bug Assessment: el teammate no alcanza la máquina, y si la alcanzara trabajaría a ciegas

- **Slug**: el-teammate-no-alcanza-la-maquina
- **Created**: 2026-09-20
- **Source**: auditoría del 2026-09-19 (hallazgos T1 y B8), verificada contra el código
- **Verdict**: valid
- **Severity**: high
- **Vía**: flujo de bug normal. **No es hotfix**: no hay datos en riesgo ni producción
  caída — hay una capacidad construida, pagada y apagada.

## Symptom

La spec 003 prometió que un teammate trabaja en la máquina del partner. El camino
entero está construido: emparejamiento, puente saliente, presencia por latido,
contención de escrituras con sus seis ataques, política en tres capas, despacho con
`FOR UPDATE SKIP LOCKED`, tarjeta de aprobación. **Nadie podía recorrerlo**, y aunque
se pudiera, el agente no vería el resultado.

Cuatro defectos en fila. Los tres primeros van juntos porque arreglar uno solo no
entrega nada:

| # | Defecto | Dónde | Verificado |
|---|---|---|---|
| D1 | `shell_local` nunca entra en el catálogo de un teammate: los dos sitios que lo montan pasan `machine_present=False` **escrito a mano** | `api/console/companion.py:884` y `:2134` · `services/teammate_catalog.py:102-108` | leyendo el código |
| D2 | La salida del comando **no llega al modelo**: el nodo `execute` se queda con el booleano y tira `result.content` | `runtime/companion/graph.py`, nodo `execute` | leyendo el código y con test en rojo |
| D3 | La muestra son los **primeros 2 KB de stdout**, y **stderr no se recoge en absoluto** — solo reinicia el reloj de inactividad | `apps/desktop/src/executor.ts` | test en rojo |
| D4 | `cwd_relative` se valida contra fugas y después se manda `None` fijo: todo corre en la raíz del directorio | `api/device_bridge.py:471` · la fila `local_executions` no lo guarda | leyendo el código |

## Root cause

**D1 no es un olvido de una línea: es un mecanismo entero sin enchufar.**
`services/device_presence.py` existe, está documentado contra sus requisitos
(001-R4.2, 011.1) y explica muy bien por qué la presencia se deriva del latido y no
se guarda en una columna. Tiene dos funciones públicas para esto —`tenant_presence`
y `catalog_includes_local_tools`— y **ninguna de las dos tiene un solo llamador**. Lo
único que se usa del módulo es `derive_presence`, y solo para pintar un estado en una
pantalla.

Así que había dos formas de equivocarse y se tomaron las dos: el catálogo se
decidía con una constante, y la función que sabía decidirlo no la llamaba nadie. Lo
mismo en la puerta de ejecución, donde `LocalExecGate.evaluate` recibe
`device_present=True` fijo (`api/console/workstation.py:250`) — ahí es inocuo, porque
la ruta ya ha resuelto la máquina dos líneas antes, pero es el mismo patrón.

**D2 y D3 comparten causa con el resto de la auditoría**: lo que producción recorre
no lo recorría ninguna prueba. El nodo `execute` se escribió para acciones
`console.*`, donde el resultado relevante es «se aplicó», y `shell_local` entró
después por el mismo sitio sin que nadie mirara qué llevaba dentro el resultado.

**D3 tiene además una causa legítima mal calibrada.** No guardar la salida es
deliberado y está bien razonado: §III de la constitución y la condición que legitima
persistir el hilo de un teammate (migración 0090, «no contiene texto de ningún
cliente final»). El error no fue acotar: fue **acotar por el lado equivocado** —el
principio en vez del final, un flujo en vez de los dos— y dejar el número tan bajo
que no cabe una traza de compilación.

## Reproduction

- D2: `apps/api/tests/unit/test_teammate_sees_what_it_ran.py`. Un `apply_confirmed`
  que devuelve `error: 'nombre' undeclared`; el turno responde sin haberlo visto.
- D3: `apps/desktop/tests/executor-sample.test.ts`. Un comando que escribe el motivo
  del fallo por stderr: no aparece. Un comando con 4.000 líneas de ruido y el error
  al final: se conserva el ruido.
- D1: `apps/api/tests/integration/test_teammate_reaches_the_machine.py`. La función
  que decide no existía.

## Scope

D1, D2 y D3 se arreglan aquí. **D4 no**: necesita columna nueva en
`local_executions` y su migración, y es el único que no impide trabajar —limita a
trabajar en la raíz del directorio—. Queda anotado en `fix.md` con lo que hace falta.

## Lo que este bug deja claro para la evaluación de la terminal

`.specify/assessments/teammate-que-trabaja-en-la-terminal/` pregunta si hace falta
una sesión viva (PTY/tmux). Este arreglo da el dato que esa pregunta necesitaba:
**parte de lo que parecía «hace falta una shell» era, en realidad, no ver la
salida.** Con D2 y D3 cerrados hay que volver a medir antes de abrir una superficie
nueva, porque el coste percibido cambia.
