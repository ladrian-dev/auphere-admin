# Especificación: La conversación es el producto

**Rama**: `013-la-conversacion-es-el-producto` · **Creada**: 2026-09-20 · **Estado**: Borrador

**Entrada**: descripción del usuario: «La spec 010 arregló el armazón alrededor de un
chat que sigue siendo el cajón de la consola trasplantado. El partner no puede confiar
en una conversación que no recuerda lo que él dijo, no le enseña lo que su agente hizo,
y no se puede leer.»

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — la API de la consola. **No se abre ninguna nueva.** |
| **Garantías de aislamiento tocadas** | Ninguna de las 7. Sí roza el **eje cliente-dentro-del-tenant** (el que `tests/isolation/test_35_*` defiende desde el 2026-09-20) y la RLS por `principal_id` de `companion.threads` (migración 0090): varios hilos por teammate multiplican filas bajo esa misma política, no la cambian. |
| **Nota de KB que la justifica** | `[[research/2026-09-19-auditoria-clase-mundial/_index]]` §5 fila 013 y `[[research/2026-09-19-auditoria-clase-mundial/04-diseno-app-escritorio]]` (tabla de paridad), en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | Nada nuevo. La conversación no gasta por sí misma; lo que gasta es el turno, y ya lo mide la 004. |

> La superficie es la que ya está abierta. Todo lo que pide esta spec se sirve con
> datos que la plataforma **ya tiene** —el registro durable del turno— o que ya
> viajan en vivo por el canal de eventos. No hace falta abrir nada para entregarlo.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El hilo recuerda la conversación entera (Prioridad: P1)

Adrián le pide a Sofía que analice las ventas de agosto. Sofía contesta. Adrián cierra
la aplicación, vuelve al rato y abre el mismo hilo. **Ve lo que él escribió y lo que
Sofía respondió**, en orden, como una conversación.

Hoy ve solo las respuestas de Sofía: sus propias preguntas eran un efecto local que
desapareció al recargar. La consecuencia no es estética — sin la pregunta delante, la
respuesta es ininteligible y no hay forma de saber qué se pidió.

**Por qué esta prioridad**: es la que convierte el hilo en un hilo. Sin esto, las otras
historias pulen algo que no se puede leer.

**Prueba independiente**: escribir, recargar, y comprobar que sigue estando. No
necesita ninguna de las demás.

**Escenarios de aceptación**:

1. **Dado** un hilo con varias vueltas, **cuando** la persona lo reabre, **entonces**
   ve sus propios mensajes y los del teammate en el orden en que ocurrieron.
2. **Dado** un turno en marcha, **cuando** la persona recarga, **entonces** su mensaje
   sigue visible y el turno continúa donde estaba.
3. **Dado** un hilo de otra persona del mismo partner, **cuando** alguien intenta
   leerlo, **entonces** no existe para ella — la RLS por `principal_id` no cambia.

---

### Historia 2 — Lo que el agente escribe se puede leer (Prioridad: P1)

Sofía responde con una lista de pasos, una tabla de ventas y un bloque de código
Python. Adrián lo lee como lista, tabla y código, con el código copiable de un gesto.

Hoy todo eso se pinta como texto plano: las comillas triples se ven, la tabla es una
fila de tuberías, y copiar el código significa seleccionar a mano sin arrastrar el
resto.

**Por qué esta prioridad**: el agente ya escribe en Markdown —el prompt del Companion
se lo pide— así que el producto ya está produciendo algo que el producto no sabe
enseñar. Es la distancia más corta entre lo que hay y lo que se espera.

**Prueba independiente**: una respuesta con lista, tabla y código se renderiza; el
texto plano sigue igual.

**Escenarios de aceptación**:

1. **Dado** un mensaje con Markdown, **cuando** se pinta, **entonces** se ven títulos,
   listas, tablas, énfasis y código con su formato.
2. **Dado** un bloque de código, **cuando** la persona lo copia, **entonces** obtiene
   el código y nada más.
3. **Dado** un mensaje que **parece** Markdown pero es texto de un cliente final,
   **cuando** se pinta, **entonces** no se ejecuta ni se carga nada de fuera.

---

### Historia 3 — Se ve lo que el comando hizo (Prioridad: P1)

Adrián aprueba que Sofía ejecute `make build`. El comando corre en su máquina. **Adrián
ve lo que el programa escribió**, mientras ocurre, en la tarjeta que él aprobó.

Hoy no lo ve. Desde el 2026-09-20 **el modelo sí lo recibe**, así que Sofía puede
decirle «falla en `main.c`» mientras la persona que aprobó el comando no tiene forma de
comprobarlo. Aprobar a ciegas y no ver el resultado es el hueco de confianza más grande
que queda en la aplicación.

**Por qué esta prioridad**: es lo que separa «le dejo ejecutar en mi ordenador» de «le
dejo ejecutar en mi ordenador y sé qué hizo». Y el dato ya viaja: solo falta enseñarlo.

**Prueba independiente**: aprobar un comando que falla y leer el error en pantalla.

**Escenarios de aceptación**:

1. **Dado** un comando aprobado, **cuando** la máquina devuelve su salida, **entonces**
   la persona la ve en la tarjeta de esa ejecución.
2. **Dado** un comando que falla, **cuando** el motivo va por el flujo de error,
   **entonces** ese motivo se ve — es donde `make` y `tsc` lo escriben.
3. **Dado** un hilo reabierto más tarde, **cuando** la persona lo lee, **entonces**
   ve **qué se ejecutó y cómo acabó**, y **NO** lo que el comando imprimió.
4. **Dado** que la salida contiene algo con forma de orden, **cuando** se pinta,
   **entonces** se presenta como dato leído y no como instrucción (§III).

---

### Historia 4 — Una conversación por asunto (Prioridad: P2)

Adrián le pide a Sofía el análisis de agosto. Tres días después quiere pedirle otra
cosa sin arrastrar aquello. Empieza **una conversación nueva** con la misma Sofía, y
puede volver a la anterior cuando quiera.

Hoy hay un hilo eterno por teammate: todo se acumula para siempre en el mismo sitio.

**Por qué esta prioridad**: P2 porque se puede vivir con un hilo largo; deja de poderse
cuando el hilo tiene meses. También es lo que da sentido a buscar.

**Prueba independiente**: crear una segunda conversación y alternar entre las dos.

**Escenarios de aceptación**:

1. **Dado** un teammate, **cuando** la persona empieza una conversación nueva,
   **entonces** se crea vacía y la anterior se conserva íntegra.
2. **Dado** varias conversaciones, **cuando** la persona vuelve a la aplicación,
   **entonces** aterriza en la última en la que trabajó.
3. **Dado** una tarea en marcha en una conversación, **cuando** la persona abre otra,
   **entonces** la primera sigue corriendo y se dice dónde.

---

### Historia 5 — Se puede corregir el tiro (Prioridad: P2)

Adrián escribe mal la pregunta. En vez de escribirla entera otra vez, **la edita y la
reenvía**. O copia una respuesta para pegarla en otro sitio. O pide que lo vuelva a
intentar cuando la respuesta no sirvió.

**Por qué esta prioridad**: quita fricción diaria, y no bloquea a nadie si falta.

**Prueba independiente**: editar el último mensaje, reintentar y copiar.

**Escenarios de aceptación**:

1. **Dado** un mensaje propio, **cuando** la persona lo edita y reenvía, **entonces**
   el turno se rehace desde ahí y la conversación no queda con dos versiones mezcladas.
2. **Dado** una respuesta, **cuando** la persona la copia, **entonces** obtiene el
   texto tal cual se escribió, no el que se pintó.
3. **IF** el turno está en marcha, **THEN** editar y reintentar no están disponibles, y
   se dice por qué en vez de fallar al pulsar.

---

### Historia 6 — Al abrir, se puede escribir (Prioridad: P2)

Adrián abre la aplicación y lo primero que ve es dónde escribir, con su equipo a mano.
Hoy lo primero que ve es un panel de estado: «Tu máquina: sin emparejar», «Nada espera
tu decisión», «Crea el primero».

**Por qué esta prioridad**: es la primera impresión y marca qué clase de producto es
—una herramienta de trabajo o un panel de administración—. P2 porque la aplicación se
puede usar sin ello: son dos clics más.

**Prueba independiente**: abrir y escribir sin pasar por ninguna otra pantalla.

**Escenarios de aceptación**:

1. **Dado** que hay al menos un teammate, **cuando** la aplicación abre, **entonces**
   hay un sitio donde escribir y se ve a quién se le escribe.
2. **Dado** que **no** hay ninguno, **cuando** la aplicación abre, **entonces** lo
   primero es crear uno — y no un composer que no lleva a ningún sitio (§V: la ausencia
   se diseña).
3. **Dado** que la máquina no está, **cuando** la aplicación abre, **entonces** se
   puede conversar igual, porque conversar no la necesita.

---

### Historia 7 — Encontrar lo que se dijo (Prioridad: P3)

Adrián recuerda que Sofía le explicó algo sobre la clínica Boreal hace semanas.
Escribe «Boreal» y lo encuentra.

Hoy ⌘K solo navega entre secciones: no busca dentro de lo hablado.

**Por qué esta prioridad**: P3 porque solo importa cuando ya hay meses de hilos, que es
después de la Historia 4.

**Escenarios de aceptación**:

1. **Dado** conversaciones con contenido, **cuando** la persona busca un término,
   **entonces** ve en qué conversaciones aparece y puede saltar ahí.
2. **Dado** una búsqueda sin resultados, **cuando** no hay coincidencias, **entonces**
   se dice que no hay, y no se confunde con «todavía cargando».

---

### Casos límite

- **Un mensaje enorme.** Una respuesta de decenas de miles de caracteres no puede
  colgar la ventana ni obligar a desplazarse minutos: se acota lo que se pinta de golpe
  y se dice que hay más.
- **Markdown roto a medias.** Mientras el texto llega en trozos, la sintaxis está
  incompleta por definición — un bloque de código abierto y sin cerrar. No puede
  parpadear entre formatos ni romper el resto del mensaje.
- **Contenido con forma de ataque.** Un cliente final escribe algo que parece Markdown
  con una imagen remota o un enlace. No se carga nada de fuera, y lo que se lee sigue
  siendo dato (§III).
- **La salida del comando ya no está.** Se reabre un hilo de la semana pasada: qué se
  ejecutó y cómo acabó, sí; lo que imprimió, no — nunca se guardó. Y **se dice**, en vez
  de dejar un hueco que parezca un fallo.
- **Cerrar mientras responde.** Se cierra la aplicación a mitad de una respuesta; al
  volver, o está entera o se dice que se interrumpió. Nunca media frase sin explicación.
- **Dos ventanas, una conversación.** La misma persona en dos sitios escribiendo al
  mismo teammate: lo que pase en una tiene que ser legible desde la otra sin recargar.

## Requisitos *(obligatorio)*

### Requisito 1 — El registro de la conversación está completo

**Historia de usuario:** Como partner, quiero que el hilo conserve lo que yo escribí,
para que la conversación se entienda al volver.

#### Criterios de aceptación

1. WHEN una persona envía un mensaje a un teammate THEN el sistema DEBE registrarlo de
   forma durable junto a la respuesta, bajo la misma persona y la misma conversación.
2. WHEN una persona reabre una conversación THEN el sistema DEBE devolver sus mensajes
   y los del teammate en el orden en que ocurrieron.
3. IF una persona pide la conversación de otra persona del mismo partner THEN el
   sistema DEBE comportarse como si no existiera, sin confirmar ni desmentir.
4. WHILE un turno está en marcha el sistema DEBE conservar visible el mensaje que lo
   originó, aunque la ventana se recargue.

### Requisito 2 — El texto se pinta como lo que es

**Historia de usuario:** Como partner, quiero leer listas, tablas y código con su
formato, para entender la respuesta sin descifrarla.

#### Criterios de aceptación

1. WHEN un mensaje contiene Markdown THEN el sistema DEBE pintar títulos, listas,
   tablas, énfasis, enlaces y bloques de código con su formato.
2. WHEN se pinta un bloque de código THEN el sistema DEBE ofrecer copiarlo, y lo
   copiado DEBE ser exactamente el código.
3. El sistema NO DEBE cargar ningún recurso externo al pintar un mensaje, ni ejecutar
   nada que venga dentro de él.
4. WHILE una respuesta llega en trozos el sistema DEBE pintar lo que hay sin que la
   sintaxis incompleta rompa el resto del mensaje.
5. WHERE un mensaje supera el tamaño que cabe de una vez EL sistema DEBE pintar una
   parte, decir que hay más, y permitir ver el resto.

### Requisito 3 — Lo que la máquina hizo se ve, y no se guarda

**Historia de usuario:** Como partner que aprueba un comando en su ordenador, quiero
ver qué hizo, para no tener que creerme al agente.

#### Criterios de aceptación

1. WHEN una ejecución aprobada devuelve su salida THEN el sistema DEBE mostrarla a la
   persona en la tarjeta de esa ejecución, incluyendo lo que el programa escribió por
   su flujo de error.
2. El sistema NO DEBE persistir **de forma durable** la salida de un comando: no
   entra en la auditoría ni en ninguna tabla, y deja de estar disponible al cabo
   de **quince minutos** desde que la máquina contestó (constitución §III).

   > **Enmendado el 2026-09-20, durante `/speckit-plan`.** Decía «en ningún sitio
   > del que se pueda volver a leer», y leído literal prohibía también el sitio
   > efímero por el que la pantalla la recibe — con lo que R3.1 era imposible de
   > cumplir. Lo que §III pide, y lo que R3.3 y CE-005 miden, es que **no sea
   > durable**. Quince minutos es el mismo reloj que ya caduca una aprobación
   > (§IV). Razonamiento en [research.md](./research.md) §2.
3. WHEN una persona reabre una conversación antigua THEN el sistema DEBE mostrar qué se
   ejecutó, dónde y cómo acabó, y DEBE decir que la salida no se conserva, en vez de
   dejar un espacio vacío.
4. WHEN se muestra la salida de un comando THEN el sistema DEBE presentarla como
   contenido leído, distinguible de lo que dice el teammate.
5. IF la salida se recortó por tamaño THEN el sistema DEBE decir que se recortó.

### Requisito 4 — Una conversación por asunto

**Historia de usuario:** Como partner, quiero separar asuntos con el mismo teammate,
para que uno no contamine al otro.

#### Criterios de aceptación

1. WHEN una persona empieza una conversación nueva con un teammate THEN el sistema DEBE
   crearla vacía y conservar las anteriores íntegras.
2. WHEN una persona abre la aplicación THEN el sistema DEBE llevarla a la conversación
   en la que trabajaba por última vez.
3. WHILE una tarea sigue en marcha en una conversación el sistema DEBE decirlo aunque la
   persona esté mirando otra.
4. WHERE una persona tiene varias conversaciones con un teammate EL sistema DEBE
   listarlas con algo que permita distinguirlas sin abrirlas.

### Requisito 5 — Corregir el tiro sin volver a empezar

**Historia de usuario:** Como partner, quiero editar, reintentar y copiar, para no
reescribir lo que ya escribí.

#### Criterios de aceptación

1. WHEN una persona edita su último mensaje y lo reenvía THEN el sistema DEBE rehacer
   el turno desde ahí, y la conversación NO DEBE quedar con dos versiones mezcladas.
2. WHEN una persona copia un mensaje THEN el sistema DEBE dar el texto tal como se
   escribió, no la versión pintada.
3. IF hay un turno en marcha THEN el sistema DEBE impedir editar y reintentar, y DEBE
   decir por qué.
4. IF hay una decisión pendiente de la persona THEN el sistema DEBE pedir esa decisión
   antes que aceptar un mensaje nuevo.

### Requisito 6 — Al abrir, se puede trabajar

**Historia de usuario:** Como partner, quiero que lo primero sea escribir, para que la
aplicación sea una herramienta y no un panel.

#### Criterios de aceptación

1. WHEN la aplicación abre y existe al menos un teammate THEN el sistema DEBE presentar
   un sitio donde escribir y decir a quién se escribe.
2. IF no existe ningún teammate THEN el sistema DEBE ofrecer crear el primero, y NO
   DEBE presentar un sitio donde escribir que no lleve a ninguna parte.
3. WHERE la máquina del partner no está presente EL sistema DEBE permitir conversar
   igualmente.
4. El sistema DEBE permitir llegar al estado de la máquina y a lo pendiente desde esa
   primera pantalla, sin que ocupen su centro.

### Requisito 7 — Encontrar lo que se dijo

**Historia de usuario:** Como partner con meses de conversaciones, quiero buscar dentro
de ellas, para no depender de mi memoria.

#### Criterios de aceptación

1. WHEN una persona busca un término THEN el sistema DEBE devolver en qué
   conversaciones suyas aparece y permitir saltar a ellas.
2. El sistema NO DEBE devolver contenido de conversaciones de otra persona.
3. IF no hay coincidencias THEN el sistema DEBE decirlo, de forma distinguible de estar
   cargando.

### Entidades clave

- **Conversación**: el sitio donde una persona y un teammate hablan de un asunto.
  Pertenece a un partner y a **una persona** (`principal_id`), y ése es el eje por el
  que la RLS de la migración 0090 la alcanza. Un teammate puede tener varias por
  persona; una conversación nunca es de dos personas.
- **Mensaje**: lo que dijo alguien, con quién lo dijo y cuándo. **La salida de un
  comando no es un mensaje** y no vive aquí: es un dato en vivo del turno.
- **Ejecución**: qué se ejecutó, dónde, quién lo aprobó y cómo acabó. Durable. Su
  salida, no.

## Criterios de éxito *(obligatorio)*

- **CE-001**: una persona reabre una conversación de hace días y puede entender qué
  pidió y qué le respondieron, sin recurrir a su memoria.
- **CE-002**: una persona que aprueba un comando que falla puede decir **por qué**
  falló leyendo la pantalla, sin preguntarle al teammate.
- **CE-003**: una respuesta con lista, tabla y código se lee sin descifrar sintaxis, y
  el código se lleva de un gesto.
- **CE-004**: en la ventana más pequeña que la aplicación permite, la conversación sigue
  siendo lo que ocupa el centro.
- **CE-005**: ninguna salida de comando aparece en la base de datos. Se comprueba
  mirando, no confiando.
- **CE-006**: una persona con tres asuntos abiertos con el mismo teammate no tiene que
  leer uno para trabajar en otro.

## Fuera de alcance

- **Adjuntar ficheros y arrastrarlos al chat** — es otra superficie de entrada, con su
  propia lectura de qué sale de la máquina. Merece su decisión.
- **Selector de modelo en el composer** — hoy el modelo del teammate ni siquiera se usa
  (B9 de la auditoría). Elegirlo por turno antes de arreglar eso sería añadir un control
  que no hace nada.
- **Abrir los ficheros que el agente nombra** — la aplicación no los abre por decisión
  de la 003, y cambiarlo es una conversación sobre qué toca la plataforma en tu disco.
- **Continuación autónoma, toolset de trabajo y sesión de terminal** — son del teammate,
  no de la conversación. Viven en `.specify/assessments/teammate-que-trabaja-en-la-terminal/`.
- **Tareas programadas** — dependen de la anterior.
- **El panel de Entorno plegable con su control** — se retira bajo 1280 desde el
  arreglo del 2026-09-20; darle un control es trabajo de esta spec **solo si** la
  Historia 6 lo necesita. Si no, se queda como deuda declarada.

## Supuestos

- **El registro durable del turno ya existe** y hoy no devuelve el mensaje de la
  persona. Se asume que completarlo es ampliar lo que se devuelve, no inventar un
  almacén nuevo. Si resultara ser lo segundo, la Historia 1 cambia de tamaño y el plan
  tiene que decirlo.
- **La salida del comando ya viaja en vivo** hasta quien espera el turno. Se asume que
  la pantalla puede recibirla por el mismo camino por el que recibe todo lo demás del
  turno, sin persistirla.
- **El teammate ya escribe en Markdown** porque su prompt se lo pide. Esta spec no
  cambia lo que escribe: cambia lo que se ve.
- **`packages/companion-ui` lo usan la aplicación y la consola.** Todo lo que aquí se
  pide del timeline aparece en las dos, y eso es deseable: una sola implementación de
  la pantalla. Lo que sea sólo de la aplicación se dice en el plan.
- **La lengua de la interfaz es la de la persona** (español o inglés), como en el resto
  de la aplicación.
- Ninguna capacidad de esta spec necesita que la máquina del partner esté presente,
  salvo la Historia 3, que sólo ocurre cuando ya hay una ejecución.
