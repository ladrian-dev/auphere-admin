# Los teammates en la aplicación de escritorio

**Spec viva.** Describe lo que existe hoy en `apps/desktop`, `apps/api`,
`apps/console` y `packages/companion-ui` para operar con teammates desde la
aplicación. Si cambias lo que describe, este documento va **en el mismo commit**
(`docs/spec-driven-development.md` §3). Especificación de origen:
`specs/003-teammates-app-escritorio/`. Lo anterior sigue vivo y se lee aparte:
`docs/desktop-workstation.md` (identidad, emparejamiento, puesto, contención).

## La frase que ordena todo

**La consola es para configurar y administrar; la aplicación es para operar el
día a día.** De ahí salen las decisiones que más sorprenden al leer el código:
la consola **no** tiene pantalla de teammates (R14.3), la aplicación **sí**
tiene pantallas propias —lo que la 001 prohibía, y por eso ese criterio quedó
anotado como superado—, y el timeline no se escribe dos veces: se comparte como
paquete.

## Una ventana, un armazón

| Vista | Partición | `preload` | Qué carga |
|---|---|---|---|
| Armazón | `auphere-app` (no persistente) | `app-preload.cjs`, lista cerrada | `dist/app/index.html`, **toda** la ventana |
| Consola | `persist:auphere-console` | **ninguno** | la consola **entera**, encima, desde la franja hacia abajo |

La tercera partición es la del ambiente del agente (`auphere-agent`), que no
alcanza ninguna de las otras dos. `assertPartitionsAreSeparate()` lo comprueba
**al arrancar** y aborta si alguien las iguala en un refactor.

**Una ventana, dos superficies, y una puerta entre ellas.** El armazón —franja
con los semáforos integrados y lista lateral— es lo que se ve por defecto. La
lista lateral es **sólo lo que se opera**: Hoy, Pendientes y tus teammates, con
la identidad y la máquina al pie.

La consola se abre por **una sola puerta** («Abrir la consola», o cualquier
sección desde ⌘K) y entra **entera**: su barra, su búsqueda y sus avisos,
ocupando todo lo que hay bajo la franja. La franja se queda visible porque la
ventana no tiene barra de título nativa — ahí viven los semáforos, el arrastre y
**«Volver al equipo»**.

> **Enmienda del 2026-09-18.** La spec 010 construyó otra cosa: la lista lateral
> espejaba las diez secciones de la consola y ésta se pintaba **dentro del
> panel**, sin su armazón (modo embebido por user-agent). Se miró funcionando y
> en la misma ventana había **dos barras laterales, dos buscadores, dos campanas
> y dos identidades** — con el glosario ya divergiendo: «Playbook» en una,
> «Conocimiento» en la otra. El modo embebido se retiró y `apps/console` vuelve
> a no saber que la aplicación existe.

⌘1 y ⌘2 no vuelven: la persona no elige superficie, elige **entrar en la consola
o volver al equipo**. La lista canónica de secciones sigue en `src/sections.ts`,
y ahora sirve para una sola cosa: **por qué ruta abrir la consola**, que es lo
que hace que un tope lleve a `/billing` y no a «búscalo tú».

Cuando la consola no carga, la ventana vuelve al armazón y se dice en su idioma
con un reintento (`app:console.failed`): antes se veía la página de error de
Chromium dentro de la ventana.

## El canal con el proceso principal

`apps/desktop/src/app-ipc.ts` **es** el contrato: 41 canales de invocación y 17
de empuje, cada uno con la forma de su entrada. El `preload` expone una función
por canal y nada más — ni `ipcRenderer`, ni `send`, ni `invoke` genérico.

Dos reglas que tienen test propio:

- la entrada **se valida, no se adivina** (`validateInput`): canal desconocido,
  uuid mal formado o decisión inventada lanzan antes de tocar la red;
- nada de lo que sale lleva sesión, cookie, token ni credencial: `redact()` las
  quita a cualquier profundidad, y `no-credentials-over-ipc.test.ts` lo afirma
  con cuerpos envenenados.

La pantalla no sabe de red. El proceso principal habla con el BFF de la consola
con la **sesión de la persona** (`session.fromPartition(HUMAN_PARTITION).fetch`),
y por eso cerrar sesión en la consola detiene también la pantalla.

## El hilo corre en la plataforma

Un hilo tiene dos ejes: el **teammate** y la **persona**. `companion.threads`
gana `teammate_id`; la RLS por `principal_id` (0090) no cambia, así que el hilo
de otra persona no se lee aunque sea del mismo teammate.

El turno es el del Companion: mismo grafo, mismo medidor, mismo catálogo
declarativo. Lo que cambia es **qué herramientas ve el modelo**:
`services/teammate_catalog.py` traduce los cinco interruptores del formulario a
nombres de `ALL_TOOLS`. El catálogo de un teammate es siempre un **subconjunto**
del catálogo del Companion: la aplicación no puede añadir nada que la plataforma
no publique (garantía 2, `test_33`).

## La tarea: lo que sobrevive a cerrar el portátil

`companion.teammate_tasks` es el objeto durable que encadena turnos. Un run que
necesita una decisión humana **cierra en `waiting`** y la tarea queda en
`esperandote`; la aprobación no caduca por un reloj propio, se cierra cuando la
tarea termina, se cancela, se archiva su teammate o alcanza su tope de vida (el
barrido es un cron del worker, cada 10 minutos).

Pendientes (`GET /console/teammates/inbox`) lista lo que espera a **esta**
persona, con su nivel (`critico · aviso · informativo`). El nivel lo decide
`core/action_level.py`, código determinista, no el modelo.

## Ejecutar en la máquina: tres capas, gana la más restrictiva

| Capa | Dónde se decide | Qué puede hacer |
|---|---|---|
| Lista blanca de ejecutables | consola, por cliente (spec 001) | **la única que permite** |
| Techo del partner | página de equipo de la consola | solo restringir |
| Preferencia de la persona | Cuenta y panel de entorno de la app | solo restringir |

`most_restrictive` vive junto al vocabulario (`db/models/local_workstation.py`)
para que la regla no se reimplemente con un `if` distinto. Dos detalles que
cuestan una tarde si se olvidan:

- **un techo ausente no restringe.** Leerlo como «preguntar» convertiría la
  ausencia de una decisión en una decisión, y nadie podría elegir «permitir
  siempre» sin pasar antes por una pantalla de equipo;
- **«permitir siempre» no escribe un permiso de argumentos.** Ese permiso es del
  *tenant* (001): escribirlo aquí dejaría pasar también a quien prefiere que le
  pregunten.

La puerta única es `POST /console/clients/{ref}/workstation/executions`. Aplicar
una acción ya confirmada entra por ahí también, y la acción **se busca** por
contenido: no hay ningún campo que el modelo pueda rellenar para decir «esto ya
lo aprobaron».

## El despacho, de punta a punta

1. la ruta decide (máquina presente → lista blanca → techo → preferencia), deja
   el asiento y escribe una fila `pendiente` en `local_executions`;
2. la máquina la recoge en su `GET /device/poll` —`FOR UPDATE SKIP LOCKED` y
   `dispatched_at`: **el mismo trabajo no se entrega dos veces**—;
3. ejecuta con la contención de la 001 y contesta en `POST /device/result` con
   el desenlace, el código de salida y una **muestra acotada** de la salida —
   los dos flujos, stdout y stderr, en el orden en que llegaron, hasta 16 KB
   con cabeza y cola y el hueco declarado (`OUTPUT_SAMPLE_LIMIT`);
4. la muestra viaja por Redis a quien espera y llega al modelo marcada
   `untrusted: true`. **No se persiste**: la auditoría dice qué pasó, nunca qué
   dijo el comando (§III).

> **Corrección del 2026-09-20.** Los dos puntos de arriba describían una
> intención, no lo que pasaba. La muestra eran los **primeros 2 KB de stdout**
> —stderr no se recogía en absoluto—, y el nodo `execute` del grafo se quedaba
> con el booleano y **tiraba el contenido**: no llegaba al modelo nada. Con 2 KB
> del principio tampoco habría cabido el motivo de un fallo, que va por stderr y
> al final. Y antes de todo eso, `shell_local` **no entraba en el catálogo de
> ningún teammate**: los dos sitios que lo montan pasaban `machine_present=False`
> escrito a mano, mientras `services/device_presence` tenía el mecanismo entero
> sin un solo llamador. Arreglado en
> `.specify/bugs/el-teammate-no-alcanza-la-maquina/`.
>
> `cwd_relative` también se arregló, con la migración **0123**: la fila de
> `local_executions` lo guarda y el poll lo manda, así que el comando corre en el
> subdirectorio que se pidió. Antes se validaba contra fugas y se tiraba, y todo
> corría en la raíz.

La espera **sondea** en vez de bloquear con `BLPOP`: un bloqueo de quince
minutos retiene una conexión del pool que comparte el webhook de WhatsApp.

## Un solo medidor

Un turno de teammate gasta por el mismo camino que el Companion y debita la
misma cartera del partner. No hay contador nuevo: `GET /console/teammates/usage`
devuelve **el mismo objeto** que `/console/companion/budget` más el reparto por
teammate. Sin importe en dólares: la fila del run no guarda con qué modelo
corrió, y el tope es en tokens.

**La spec 004 arregló la mitad que no cuadraba.** Hasta entonces ese objeto
salía de sumar `companion.runs`, que solo ve turnos de Companion y de
teammates; el libro lo gastan además los turnos de canal de los clientes y las
ejecuciones en la máquina, y el **mismo** número
(`partners.companion_monthly_token_cap`) dimensionaba las dos cosas. Un partner
podía leer «20 % usado» y recibir un `409 wallet_empty` a la vez.

Desde la 004:

- El total sale **del libro** (`partner_wallets.included_remaining`): el número
  que se enseña es el mismo entero que decide si un turno pasa.
- La suma sobre `companion.runs` baja a ser **atribución** — quién gastó, no
  cuánto. Puede sumar menos que el total, y la diferencia **se nombra** en vez
  de repartirse entre los teammates que sí aparecen.
- El período es **semanal**, anclado a la fecha de alta del partner, y lo no
  gastado no se acumula.
- El consumo de los **clientes finales** sale de los créditos comprados y ya no
  puede vaciar el pool de la aplicación.
- En pantalla, el partner ve **una barra y una fecha**, no la cifra del pool.
  El panel de operador sigue viendo las cifras: las necesita para conciliar.

## La conversación (spec 013)

Lo que la 013 cambió de la pantalla, que es lo que el partner vive a diario:

| | |
|---|---|
| **El hilo recuerda** | El resumen de cada run lleva el texto que lo originó, así que al reabrir se ven las preguntas y no solo las respuestas. El mensaje **ya se guardaba**; lo que faltaba era devolverlo |
| **Se lee** | Markdown, código y tablas con su formato (`react-markdown` sin `rehype-raw`: se construyen elementos de React, no HTML, así que un mensaje no puede ejecutar nada **por construcción**) |
| **Se ve lo que el comando hizo** | Una tarjeta de **resultado**, hermana de la de aprobación. La salida se pide por su ruta —nunca por el stream, que el contrato reserva a hechos— y **caduca a los quince minutos**: no entra en ninguna tabla |
| **Varias conversaciones** | Por teammate y por persona. Sin migración: `companion.threads` ya lo admitía desde la 003; lo que lo impedía era coger siempre el primer hilo no archivado |
| **Al abrir se escribe** | «Hoy» abre con el composer. Sin teammates no se pinta: un sitio donde escribir que no lleva a ninguna parte es peor que no tenerlo |
| **Copiar, editar, reintentar** | Se copia el original, no lo pintado. Con un turno vivo o una confirmación esperando, los controles no aparecen y se dice por qué |
| **Buscar** | ⌘K encuentra dentro de lo hablado, bajo `app.principal_id`. Sin índice nuevo |

## Qué se comparte y qué no

`packages/companion-ui` es el timeline, la tarjeta de confirmación, el composer
y los medidores, extraídos del cajón de la consola: sin `next/*`, con un
`Transport` que la consola implementa con `fetch` y la aplicación con IPC. Una
sola implementación de la pantalla que las dos enseñan.

Lo que **no** se comparte es lo que solo tiene sentido en un sitio: el roster,
Pendientes, Cuenta y el panel de entorno son de la aplicación; la página de
equipo con el techo de ejecución es de la consola.

## Comportarse como una aplicación

Instancia única (`requestSingleInstanceLock`: dos instancias serían dos puentes
con la misma credencial), la ventana recuerda dónde estaba —corrigiendo contra
las pantallas de hoy, para no restaurar fuera de vista—, icono de bandeja que
cuenta **lo que espera una decisión** (lo informativo no suma) y un atajo global
configurable en `shortcut.json` del directorio de datos.

## Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Contrato del canal IPC | `apps/desktop/src/app-ipc.ts` · `specs/003-*/contracts/desktop-app-ipc.md` |
| Pantalla | `apps/desktop/src/app/` (`App.tsx`, `routes/`) |
| Puente del proceso principal | `apps/desktop/src/electron/app-surface.ts` |
| Roster, bandeja, tareas, consumo | `apps/api/src/nexus_api/api/console/teammates.py` |
| Catálogo por teammate | `apps/api/src/nexus_api/services/teammate_catalog.py` |
| Política en tres capas | `services/local_exec_policy.py` · `services/local_exec_gate.py` |
| Despacho a la máquina | `services/local_dispatch.py` · `api/device_bridge.py` |
| Eventos (24) | `apps/api/src/nexus_api/api/companion_streaming.py` · `docs/companion/CONTRACT-V3.md` |
| Timeline compartido | `packages/companion-ui/` |
