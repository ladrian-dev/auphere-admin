# Idea Intake: el teammate trabaja en una terminal, no en comandos sueltos

- **Slug**: teammate-que-trabaja-en-la-terminal
- **Created**: 2026-09-20
- **Source**: sesión del 2026-09-20. Luis: «los teammates sean inteligentes, puedan
  ejecutar comandos en consola (no sé si tenemos que integrarle un [PTY] o tmux
  internamente) para que sean más eficientes y autónomos» · «replica las
  funcionalidades core de Grok Bot» · punteros:
  `apps/desktop/src/{executor,local-runner,containment}.ts`,
  `apps/api/src/nexus_api/api/console/companion.py`,
  `apps/api/src/nexus_api/services/teammate_catalog.py`,
  `apps/worker/src/nexus_worker/runtime/companion/graph.py` · auditorías:
  KB `research/2026-09-19-auditoria-clase-mundial/02-teammates-y-companion`
- **Type**: gap + improvement (una capacidad que el producto promete y no entrega, y
  la forma en que debería entregarse)

## Lo que pasa hoy

**Un teammate no puede ejecutar nada en la máquina, y no por falta de
infraestructura.** El emparejamiento, el puente saliente, la contención de escrituras
con sus seis ataques, la política en tres capas y la tarjeta de aprobación están
construidos y probados. Lo que falta es una línea: los dos únicos sitios que montan
el catálogo de un teammate pasan `machine_present=False` escrito a mano
(`api/console/companion.py:884` y `:2134`), y `for_teammate`
(`services/teammate_catalog.py:102-108`) solo publica `shell_local` cuando ese valor
es verdadero. **Verificado leyendo el código el 2026-09-19.**

Eso se arregla en la ola 1 (bug B4) y no necesita esta evaluación. Lo que sí la
necesita es lo que queda **después** de arreglarlo, porque entonces el teammate podrá
ejecutar un comando y seguirá sin poder trabajar:

| Qué | Dónde | Consecuencia |
|---|---|---|
| La salida del comando no vuelve al modelo | `graph.py:1100-1110` guarda `ok` y descarta `result.content` | El agente ejecuta a ciegas |
| La muestra son 2.048 caracteres de stdout, y stderr se tira | `executor.ts:22, 97-104` · `device_bridge.py:546` | Un build que falla es justamente stderr |
| `cwd_relative` se valida y luego se manda `None` | `device_bridge.py:471` | Todo corre en la raíz del directorio |
| Cada comando es un proceso nuevo | `executor.ts:69` (`spawn`) | No hay `cd`, ni variables, ni un servidor levantado entre pasos |
| Latencia de 0 a 10 s por comando | sondeo en `presence.ts:12` | Veinte comandos son tres minutos de espera |
| Tras aprobar, el turno responde y termina | `console/companion.py:1328` | No continúa solo: cada paso lo pide una persona |

*(Todo salvo la primera fila procede de la auditoría del 2026-09-19 y no lo he
verificado yo línea a línea.)*

## La pregunta de verdad: proceso por comando o sesión viva

Luis pregunta si hace falta un PTY o tmux. La pregunta tiene fondo y no se contesta
con una preferencia técnica, porque **cambia el modelo de seguridad entero**.

Hoy la unidad es **un comando**: ejecutable de la lista blanca, argumentos validados,
directorio fijado, aprobación por argv nuevo. Todo eso se puede inspeccionar **antes**
de ejecutar.

Una sesión viva —PTY o tmux— cambia la unidad a **una conversación con una shell**.
Y ahí la lista blanca deja de poder decidir: dentro de `bash` ya no hay un argv que
mirar, hay tecleo. La propia KB lo tiene anotado citando a Anthropic: la contención
*«es una barrera para las herramientas de fichero únicamente: **no** restringe
`bash`»*.

No es un argumento para no hacerlo. Es un argumento para que **la sesión viva sea una
decisión con su propio precio**, y no un efecto colateral de querer que el agente vaya
más rápido.

Hay una tercera vía que conviene medir antes de elegir: **mantener el proceso por
comando y arreglar lo caro de verdad**, que probablemente no es el arranque del
proceso sino los 0-10 s de sondeo, los 2 KB de salida y el `cwd` perdido. Si el coste
real está ahí, una sesión persistente compra poco y paga mucho.

## Lo que hace Grok, y lo que de eso encaja

De la investigación del 2026-09-19 (KB `06-referentes-externos`), lo que estos
productos tienen y aquí no:

- **Niveles de permiso visibles en el composer** (preguntar / una vez / la sesión /
  sin frenos), con lo destructivo preguntando siempre. Aquí la política existe y es
  correcta, pero se configura en la consola, en otra pantalla y por cliente.
- **Plan antes de ejecutar**, aprobable y editable paso a paso.
- **Diff de cada cambio de archivo, y deshacer** con sus límites escritos.
- **La tarea sigue con la app cerrada**, y si la máquina está apagada la interfaz lo
  dice como estado.
- **Tareas programadas** con historial de omitidas y un solo recuperar.

De esa lista, **el plan aprobable y los niveles en el composer son lo que convierte
«ejecuta un comando» en «hazme esto»**, y ninguno de los dos necesita una sesión
viva. Merece la pena separarlo en la evaluación: qué parte de «más autónomo» es
terminal, y qué parte es plan, permisos y continuación.

## Lo que hay que decidir, no dar por hecho

- **Si la unidad pasa a ser una sesión.** Y si sí, qué sustituye a la lista blanca
  cuando ya no hay argv que mirar: ¿un contenedor por sesión? ¿el mismo directorio
  contenido más una lista de ejecutables aplicada por un shim en el `PATH`?
- **Dónde está el coste real hoy.** Medir antes de diseñar: sondeo, tamaño de
  muestra, arranque de proceso. Es un día de trabajo y decide la forma.
- **Qué ve el modelo de la salida.** Cabeza y cola, stderr incluido, ¿16 KB? ¿32 KB?
  ¿Y qué pasa con un comando que escupe megabytes?
- **Si el teammate continúa solo tras una aprobación**, y cuántos pasos puede
  encadenar sin volver a preguntar. Es lo que Luis llama autonomía y hoy vale cero.
- **Si `spawn` sigue heredando todo el entorno** (hoy sí, `executor.ts:69`): las
  credenciales de git del partner son justo lo que hace valioso ejecutar en su
  máquina, y justo lo que un prompt inyectado querría.

## Superficie de confianza

`3a`. Una sesión viva **la amplía** respecto a lo que la spec 001 evaluó: esto no es
ejecutar un comando aprobado, es dar una shell. Modelo de amenaza escrito antes del
código y un test de aislamiento por garantía tocada, incluida la suite de contención
en Windows (T039/T043, que nunca se ha ejecutado).

## Fuera de alcance

Controlar el escritorio del partner (ratón, teclado, pantalla): es la superficie `3b`,
no tiene precedente abierto en Windows y va sola. Y la máquina en la nube, que es su
propia evaluación ([[maquina-del-teammate-sin-pc]]).
