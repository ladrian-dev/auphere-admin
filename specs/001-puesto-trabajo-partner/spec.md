# Especificación: el puesto de trabajo del teammate en la máquina del partner

**Rama**: `001-puesto-trabajo-partner` · **Creada**: 2026-09-09 · **Estado**: Borrador

**Entrada**: traspaso de
[`.specify/assessments/kirocrew-como-sustrato/decision.md`](../../.specify/assessments/kirocrew-como-sustrato/decision.md)
— veredicto **go** acotado a la beta 2.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`3a`** — ejecutar en la máquina del partner |
| **Garantías de aislamiento tocadas** | **2. Tool whitelist por agente** (de frente) · **6. Log + trace tagging** (la ejecución local y sus aprobaciones se auditan por tenant) · **1. Postgres RLS** (la lista blanca y la presencia de dispositivo son datos por tenant) |
| **Nota de KB que la justifica** | `[[15-kirocrew-y-alternativas]]` y `[[14-mvp-y-fases]]` §3, en `/Users/lmatos/Work/Auphere/teammates/`. Decisión de `shell_local` cerrada en `[[10-decisiones]]` §2.7 el 2026-09-09 |
| **Qué se mide** | **Modelo** — toda sesión de agente entra en el medidor que ve el partner. **Reloj de máquina: no** — la máquina es del partner y ya está pagada, y esa es justamente la ventaja económica de esta superficie frente a la `2` |

> **Por qué no cabe en la superficie ya abierta** (§II): la superficie `0` es la API
> de la consola, y el valor de esta spec es exactamente lo que no se puede hacer
> por API — usar el ambiente del partner: sus repos, sus credenciales de git, sus
> CLI y su red interna. Una VM (superficie `2`) tampoco lo da: ese ambiente habría
> que reconstruirlo entero, que es el trabajo que la superficie `3a` evita.
> Se abre por su **mitad barata**: ficheros y terminal, con precedente abierto en
> macOS y en Windows. La mitad cara —controlar el escritorio, `3b`— queda fuera.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El teammate arregla el build (Prioridad: P1)

El partner le pide al teammate que arregle un build que falla. El teammate abre el
proyecto en el directorio que el partner declaró, ejecuta el build, lee el log,
identifica el fallo, propone el arreglo, pide aprobación una vez, y vuelve a
ejecutar. El partner no escribe ningún comando.

**Por qué esta prioridad**: es el diferencial entero. Sin esto el teammate sigue
proponiendo y no haciendo, que es lo que ya hace en la superficie `0`.

**Prueba independiente**: con un proyecto real del partner cuyo build falla por una
causa conocida, medir si el teammate llega al resultado sin que una persona teclee
un comando. Entrega valor sola, sin las historias 2, 3 y 4.

**Escenarios de aceptación**:

1. **Dado** un proyecto en el directorio declarado y un build que falla, **cuando**
   el partner pide que lo arregle, **entonces** el teammate ejecuta el build, cita
   la línea del log que explica el fallo y propone un cambio concreto.
2. **Dado** que el arreglo requiere un comando cuyos argumentos no se han usado
   antes, **cuando** el teammate lo propone, **entonces** el sistema pide
   aprobación humana antes de ejecutarlo.
3. **Dado** que la aprobación se concede, **cuando** el comando se ejecuta,
   **entonces** el build vuelve a correr y el teammate informa del resultado real,
   no del esperado.

---

### Historia 2 — El catálogo dice la verdad sobre la máquina (Prioridad: P1)

El partner cierra el portátil a mitad de tarea. La interfaz lo dice como estado
—«el MacBook de Luis está desconectado desde las 23:10»— y el teammate deja de
tener herramientas locales: no las intenta y falla, es que no las tiene.

**Por qué esta prioridad**: es P1 y no P2 porque sin ella la historia 1 miente en
cuanto la máquina se va, y §V no admite una pantalla que mienta. Además es la
condición para que el teammate no invente resultados de comandos que no corrió.

**Prueba independiente**: desconectar la máquina a mitad de una tarea y comprobar
dos cosas —lo que dice la pantalla y lo que hay en el catálogo del turno
siguiente—. No necesita que la historia 1 esté completa.

**Escenarios de aceptación**:

1. **Dado** un dispositivo presente, **cuando** el partner mira el estado,
   **entonces** ve el dispositivo y desde cuándo está conectado.
2. **Dado** un dispositivo que deja de latir, **cuando** el teammate compone su
   siguiente turno, **entonces** las herramientas locales no están en su catálogo.
3. **Dado** un dispositivo ausente, **cuando** el partner pide algo que lo
   requiere, **entonces** el teammate dice que no puede y por qué, y la interfaz
   no muestra un control apagado.

---

### Historia 3 — La lista blanca no se negocia en el turno (Prioridad: P1)

Un ejecutable que no está en la lista blanca del tenant no se ejecuta y **no se
puede aprobar en caliente**: entra por la consola, lo añade una persona a
propósito y fuera de la conversación. Lo que sí se aprueba en el turno son
argumentos nuevos de un ejecutable ya permitido.

**Por qué esta prioridad**: la contención de ficheros no restringe la ejecución de
comandos, así que la lista blanca **es** la historia de seguridad de esta
superficie. Si se puede ampliar en caliente, no vale nada.

**Prueba independiente**: pedir al teammate un ejecutable ausente de la lista y
comprobar que se deniega sin ofrecer aprobación; después añadirlo por la consola y
comprobar que ya se puede usar, con la aprobación de argumentos donde toque.

**Escenarios de aceptación**:

1. **Dado** un ejecutable fuera de la lista blanca, **cuando** el teammate intenta
   usarlo, **entonces** la llamada se deniega y no aparece como decisión pendiente
   aprobable.
2. **Dado** un ejecutable en la lista con argumentos nuevos, **cuando** el teammate
   lo invoca, **entonces** se pide aprobación, y la auditoría guarda quién decidió.
3. **Dado** una invocación con metacaracteres de shell, **cuando** llega al gate,
   **entonces** se deniega, sin importar si el ejecutable está en la lista.

---

### Historia 4 — Ninguna herramienta ajena entra en la sesión (Prioridad: P1)

La sesión del agente en la máquina del partner expone **exactamente** la lista
blanca del tenant. Nada de lo que esa máquina tenga configurado para otros usos
llega al teammate.

**Por qué esta prioridad**: es la garantía 2 de aislamiento dicha en voz alta —«la
lista blanca es exhaustiva y por tenant: no hay globales»—. La evaluación observó
lo contrario en una máquina de desarrollo, y en esta superficie la máquina es del
partner.

**Prueba independiente**: en una máquina con herramientas ajenas configuradas,
abrir una sesión y enumerar el catálogo. No depende de las otras historias.

**Escenarios de aceptación**:

1. **Dado** una máquina con herramientas ajenas configuradas, **cuando** se abre
   una sesión, **entonces** el catálogo contiene la lista blanca del tenant y nada
   más.
2. **Dado** que el sistema no puede garantizar lo anterior, **cuando** se intenta
   abrir la sesión, **entonces** la sesión no se abre y se dice por qué.

---

### Casos límite

- ¿Qué pasa si la máquina se desconecta **mientras** un comando aprobado está
  corriendo? El resultado no vuelve: hay que decidir si la tarea queda `bloqueada`
  o `parcial`, y decirlo (§V).
- ¿Qué pasa si el directorio declarado deja de existir, cambia de sitio o pasa a
  ser un enlace simbólico entre dos turnos?
- ¿Qué pasa si un comando permitido tarda indefinidamente? Lo cubre el Requisito
  12: límite de reloj y muerte del árbol de procesos.
- ¿Qué pasa si la aplicación de escritorio se cierra con un subagente esperando
  aprobación? El Requisito 11.2 lo deniega; queda decidir si la tarea padre queda
  `bloqueada` o `parcial`.
- ¿Qué pasa si un comando permitido escribe fuera del directorio fijado por una vía
  que la contención de ficheros no cubre?
- ¿Qué ve el partner cuando su tenant no tiene ningún ejecutable en la lista
  blanca todavía? La ausencia se diseña: no hay botón apagado.
- ¿Qué pasa si dos personas del mismo partner aprueban el mismo comando a la vez?
- ¿Qué pasa si la salida de un comando contiene texto que parece una instrucción?
  Es dato, nunca instrucción (§III).

## Requisitos *(obligatorio)*

### Requisito 1 — Ejecutar dentro de un directorio declarado

**Historia de usuario:** Como partner, quiero que el teammate trabaje dentro de un
directorio que yo declaro, para que use mi ambiente sin alcanzar el resto de mi
máquina.

#### Criterios de aceptación

1. WHEN el partner declara un directorio de trabajo THEN el sistema DEBE fijar toda
   ejecución local dentro de ese directorio, y NO DEBE ejecutar fuera de él.
2. WHEN un teammate necesita ejecutar en la máquina del partner THEN el sistema
   DEBE ofrecer una herramienta de ejecución local distinta de cualquier
   herramienta de ejecución remota, y NO DEBE exponer una única herramienta con un
   parámetro que diga dónde ejecuta.
3. IF el destino de una ejecución no se puede determinar sin ambigüedad THEN la
   llamada DEBE denegarse.
4. IF el directorio declarado no existe, no es un directorio o ha dejado de
   resolver dentro de sí mismo THEN toda ejecución local DEBE denegarse hasta que
   el partner lo vuelva a declarar.

### Requisito 2 — La lista blanca de ejecutables es configuración, no una decisión del turno

**Historia de usuario:** Como responsable de Auphere, quiero que ampliar lo que el
teammate puede ejecutar sea un acto deliberado fuera de la conversación, para que
la lista blanca siga siendo una garantía y no un trámite.

#### Criterios de aceptación

1. El sistema DEBE mantener por tenant una lista blanca de ejecutables permitidos,
   modificable únicamente desde la consola y por una persona.
2. WHEN un agente solicita un ejecutable ausente de la lista blanca de su tenant
   THEN el sistema DEBE denegar la llamada, y NO DEBE presentarla como decisión
   pendiente aprobable.
3. WHEN un agente solicita argumentos no vistos antes para un ejecutable presente
   en la lista THEN el sistema DEBE exigir aprobación humana antes de ejecutar.
4. IF una invocación contiene metacaracteres de shell —tuberías, encadenamiento,
   subshells, redirecciones o sustitución de comandos— THEN la llamada DEBE
   denegarse, con independencia de que el ejecutable esté permitido.
5. WHERE se concede una aprobación de argumentos EL sistema DEBE registrarla como
   objeto durable con caducidad e identidad de la persona que decidió, y NO DEBE
   resolverla como un prompt que muere con el turno.
6. IF el gate no puede verificar una invocación THEN la llamada DEBE denegarse, y
   NO DEBE aparecer como decisión pendiente aprobable.

### Requisito 3 — Contención de escrituras

**Historia de usuario:** Como partner, quiero que lo que el teammate escribe se
quede donde dije, para que un enlace o una carrera no le den acceso al resto de mi
disco.

#### Criterios de aceptación

1. El sistema DEBE resistir los seis ataques de contención —enlace simbólico
   final, TOCTOU, enlace simbólico de padre, padre intercambiado, carrera de
   creación exclusiva y enlace duro— **en macOS**.
2. El sistema DEBE resistir los mismos seis ataques **en Windows**.
3. IF la contención no puede verificarse para una ruta THEN la escritura DEBE
   denegarse.

### Requisito 4 — Presencia de dispositivo y catálogo honesto

**Historia de usuario:** Como partner, quiero que la interfaz diga si mi máquina
está o no, para no recibir un error donde debería haber un estado.

#### Criterios de aceptación

1. WHILE el dispositivo del partner mantiene su latido —emitido cada **10 s**— el
   sistema DEBE ofrecer las herramientas locales en el catálogo del turno.
2. WHEN el latido caduca —**30 s** sin recibirlo— THEN el sistema DEBE retirar las
   herramientas locales del catálogo, y el teammate NO DEBE intentar usarlas ni
   afirmar resultados de comandos que no ejecutó.
3. WHEN el partner consulta el estado THEN la interfaz DEBE decir desde cuándo el
   dispositivo está desconectado, presentado como estado y no como error.
4. WHERE una capacidad local no está disponible EL sistema DEBE diseñar su
   ausencia, y NO DEBE mostrar un control desactivado ni una pantalla que explique
   lo que el partner no tiene.

### Requisito 5 — El catálogo de herramientas es exhaustivo por tenant

**Historia de usuario:** Como responsable de Auphere, quiero que la sesión del
agente exponga exactamente lo que su tenant tiene permitido, para que la garantía
de aislamiento nº 2 siga siendo cierta en la máquina de otra persona.

#### Criterios de aceptación

1. WHEN se abre una sesión de agente en la máquina del partner THEN el catálogo de
   herramientas DEBE contener exactamente las de la lista blanca de ese tenant.
2. IF el ambiente de la máquina declara herramientas adicionales THEN el sistema
   NO DEBE exponerlas al agente, y DEBE dejar constancia del intento.
3. IF el sistema no puede garantizar el criterio 5.1 THEN la sesión NO DEBE
   abrirse.
4. El catálogo lo configura **únicamente Auphere**. El partner NO DEBE poder
   añadir herramientas a la sesión de su teammate, ni desde su máquina ni desde la
   consola. El criterio 5.2 es una **prohibición**, no una defensa oportunista.

### Requisito 6 — El puente es saliente

**Historia de usuario:** Como partner, quiero que nada entre desde internet a mi
máquina, para que instalar esto no abra un puerto en mi casa ni en mi oficina.

#### Criterios de aceptación

1. El sistema DEBE establecer la conexión desde la máquina del partner hacia la
   plataforma, y NO DEBE aceptar conexiones entrantes hacia esa máquina.
2. WHEN la conexión se pierde THEN el dispositivo DEBE reintentar desde su lado, y
   la interfaz DEBE mostrar `reconectando` mientras tanto.
3. WHEN un dispositivo se da de alta THEN el sistema DEBE emitirle una credencial
   **propia de ese dispositivo**: acotada a su tenant, revocable por sí sola, y que
   solo autoriza latir, sondear trabajo y devolver resultados.

   No contradice el Requisito 15.2. Lo que aquel prohíbe es una **credencial de
   backend** —una llave de la cuenta, que abre todo—; ésta abre exactamente cuatro
   operaciones de una máquina concreta. La diferencia importa: sin credencial
   propia el dispositivo tendría que llevar la de la persona, que es peor.
4. IF una credencial de dispositivo se usa para pedir trabajo de **otro**
   dispositivo o de otro tenant THEN el sistema DEBE denegarlo, y el intento DEBE
   quedar registrado.

### Requisito 7 — Dos escaleras de aprobación, y una frontera clara

**Historia de usuario:** Como responsable de Auphere, quiero que lo que toca a un
cliente final pase siempre por nuestra aprobación durable, aunque el trabajo ocurra
en la máquina del partner.

#### Criterios de aceptación

1. WHEN una acción toca datos de un cliente final THEN la aprobación DEBE ser la
   durable de la plataforma, con la persona que decidió nombrada en la auditoría.
2. WHERE una acción se limita a la máquina del partner EL sistema DEBE resolverla
   con la escalera local, y NO DEBE consumir una aprobación durable.
3. IF una aprobación caduca sin respuesta THEN la acción DEBE denegarse.
4. El sistema NO DEBE introducir ninguna credencial de cliente final en el ambiente
   donde se ejecuta el agente.

### Requisito 8 — Lo que se ejecuta queda auditado

**Historia de usuario:** Como responsable de Auphere, quiero poder reconstruir qué
se ejecutó, dónde y con permiso de quién, para responder a un incidente sin
depender de la memoria de nadie.

#### Criterios de aceptación

1. WHEN se ejecuta un comando local THEN el sistema DEBE registrar tenant,
   dispositivo, ejecutable, argumentos, resultado y —si la hubo— la persona que
   aprobó.
2. El registro DEBE estar etiquetado por tenant, de modo que la garantía nº 6 lo
   alcance igual que a cualquier otra traza.
3. WHEN una llamada se deniega THEN la denegación DEBE registrarse con su motivo.

### Requisito 9 — Distribución firmada y actualizable

**Historia de usuario:** Como partner, quiero instalar esto sin que mi sistema
operativo me avise de que es software sin firmar, y que se mantenga solo.

#### Criterios de aceptación

1. El paquete de escritorio DEBE distribuirse firmado y notarizado en macOS, y
   firmado en Windows.
2. WHEN existe una versión nueva THEN la aplicación DEBE actualizarse por sí misma.

### Requisito 10 — Lo que gasta, se mide

**Historia de usuario:** Como partner, quiero ver en mi medidor lo que este trabajo
consume, para que no haya una parte del gasto que no aparece.

#### Criterios de aceptación

1. WHEN una sesión de agente consume modelo THEN ese consumo DEBE entrar en el
   medidor que ve el partner.
2. El sistema NO DEBE facturar reloj de máquina por esta superficie: la máquina es
   del partner.

### Requisito 11 — Subagentes, con una superficie que pueda contestar

**Historia de usuario:** Como partner, quiero que el teammate reparta trabajo largo
entre subagentes, para que una tarea grande no se resuelva de una sola pasada
secuencial.

#### Criterios de aceptación

1. WHERE la aplicación de escritorio está conectada EL sistema DEBE poder lanzar
   subagentes, y la aplicación DEBE ser la superficie que contesta su aprobación.
2. WHEN un subagente requiere aprobación y ninguna superficie puede contestarla
   THEN el sistema DEBE denegar el lanzamiento y decir por qué, y NO DEBE informar
   del subagente como iniciado.
3. IF un subagente se rechaza THEN su estado mostrado DEBE coincidir con lo
   ocurrido: un rechazo NO DEBE presentarse como éxito (§V).
4. WHILE un subagente espera a otro el sistema DEBE mostrarlo como `bloqueado`, y
   NO DEBE pintarlo como ocioso.

### Requisito 12 — Ninguna ejecución dura para siempre

**Historia de usuario:** Como partner, quiero que nada que el teammate lance se
quede corriendo en mi máquina sin que yo lo sepa, porque mi sistema operativo no
pone ningún techo por mí.

#### Criterios de aceptación

1. WHEN se lanza una ejecución local THEN el sistema DEBE aplicarle un límite de
   reloj de **600 s** por defecto, configurable por tenant hasta un techo de
   **3600 s**.
2. WHEN una ejecución alcanza su límite THEN el sistema DEBE terminarla junto con
   **todo su árbol de procesos hijos**, y DEBE informarlo como resultado, no como
   silencio.
3. WHEN una sesión termina THEN el sistema DEBE recoger los procesos hijos que
   hayan sobrevivido, y NO DEBE dejarlos huérfanos en la máquina del partner.
4. IF un proceso no puede terminarse THEN el sistema DEBE decírselo al partner y
   nombrar el proceso, en vez de darlo por terminado.
5. IF una ejecución no produce salida durante **300 s** THEN el sistema DEBE
   tratarla como colgada y terminarla junto con su árbol de procesos. Un proceso
   que tarda no es un proceso colgado: los dos límites son distintos a propósito.

### Requisito 13 — Lo que el sustrato trae y no se enciende

**Historia de usuario:** Como responsable de Auphere, quiero que las capacidades
que el puesto de trabajo trae de fábrica y nosotros no usamos sean **inalcanzables**
y no solo estén sin listar, para que no dependan de que nadie se acuerde.

#### Criterios de aceptación

1. El sistema NO DEBE exponer al agente el navegador ni el control de escritorio
   del sustrato, y DEBE hacerlos **inalcanzables**: no basta con que no estén en la
   lista blanca. Se distingue del criterio 5.2, que trata de
   herramientas que **el ambiente de la máquina** declara: esto son capacidades que
   **el propio sustrato trae de fábrica**.
2. El sistema DEBE arrancar con la telemetría del sustrato desactivada, fijada
   **antes del primer arranque**.
3. El sistema NO DEBE habilitar el canal de mensajería no oficial del sustrato.
4. El sistema NO DEBE permitir la carga de aplicaciones de terceros en el proceso
   que hospeda al agente.
5. El sistema DEBE fijar las tres rutas del sustrato —data home, home de familia y
   workspace del agente— dentro de una ubicación que declare el empaquetado, y NO
   DEBE materializar ninguna de ellas en el home del partner por defecto.

### Requisito 14 — El alcance de red y la ejecución local no conviven

**Historia de usuario:** Como responsable de Auphere, quiero que ninguna herramienta
que lea contenido externo esté activa en la misma sesión que la ejecución local, para
que la cadena «el agente lee una web → la web dice *ejecuta esto* → el agente lo
ejecuta en el portátil de una persona» no exista.

Esto es §III dicho para esta beta. El Requisito 13 apaga el navegador **del
sustrato**; éste cubre el caso que faltaba: una herramienta de alcance externo que
entra **legítimamente** por la lista blanca del tenant — un conector, por ejemplo.
La regla de la constitución es que *la fase que encienda la segunda de las dos paga
las guardas de las dos*, y esta beta no las paga: enciende una sola.

#### Criterios de aceptación

1. El catálogo de herramientas DEBE declarar, por herramienta, si alcanza contenido
   externo.
2. IF el alcance de una herramienta no está declarado THEN el sistema DEBE tratarla
   como si alcanzara contenido externo.
3. WHILE el tenant tenga un dispositivo presente EL sistema NO DEBE ofrecer en el
   mismo catálogo de turno herramientas de alcance externo **y** la herramienta de
   ejecución local.
4. WHEN ese conflicto se resuelve THEN el sistema DEBE conservar la ejecución local,
   retirar las de alcance externo, y **decirlo como estado** — ni como error ni en
   silencio (§V).

### Requisito 15 — La aplicación que el partner instala

**Historia de usuario:** Como partner, quiero instalar una aplicación que sea mi
ventana al teammate, sin que instalarla deje una llave de mi cuenta en el disco ni
le dé al agente acceso a mi sesión.

El Requisito 9 dice cómo se distribuye y el 11 la usa como superficie de
aprobación, pero **ninguno dice qué es**. Y hay una tensión que hay que escribir
antes de construirla: §VI prohíbe que un agente navegue la consola de Auphere
*precisamente porque* eso mete una sesión autenticada dentro de su ambiente. Esta
aplicación va a tener esa sesión **en la misma máquina** donde el agente ejecuta.
Lo que separa una cosa de la otra no es la buena intención: es el criterio 15.3.

#### Criterios de aceptación

1. La aplicación DEBE ser una cáscara sobre la consola de Auphere, y NO DEBE
   reimplementar sus pantallas — dos implementaciones de la misma pantalla
   divergen, y la que se queda atrás miente.
   > **Superado por `specs/003-teammates-app-escritorio` (R12).** La aplicación
   > sí tiene pantallas propias desde la 003: el roster, el hilo, Pendientes y
   > Cuenta. El motivo por el que este criterio decía lo contrario sigue siendo
   > válido y por eso no se ha borrado — dos implementaciones de **la misma**
   > pantalla divergen. Lo que cambió es que estas no son las mismas: la consola
   > administra y no tiene ninguna de ellas (003-R14.3), y el timeline se
   > comparte como paquete (`@nexus/companion-ui`) en vez de escribirse dos
   > veces. Lo que sigue en pie de este requisito son los criterios 2, 3 y 4.
2. La aplicación NO DEBE almacenar ninguna credencial de backend, igual que la
   consola que envuelve.
3. La sesión autenticada de la persona NO DEBE ser alcanzable desde el ambiente
   del agente. El agente llega a `console.*` por su propio servidor MCP y con su
   propia identidad; no reutiliza la sesión de quien está delante.
4. WHILE el puente no está establecido EL sistema DEBE mostrar `reconectando` como
   estado, y NO DEBE ofrecer herramientas locales mientras tanto.

### Entidades clave *(si la feature toca datos)*

- **Dispositivo del partner**: la máquina declarada, su latido y su última
  presencia. Pertenece al tenant del partner; la RLS lo alcanza por su columna de
  tenant.
- **Lista blanca de ejecutables**: el conjunto de ejecutables permitidos y su
  directorio declarado. Por tenant, alcanzada por RLS. Nunca global.
- **Aprobación de argumentos**: la decisión durable que autoriza unos argumentos
  concretos para un ejecutable permitido. Por tenant, con caducidad y con la
  persona que decidió.
- **Registro de ejecución local**: qué se ejecutó o se denegó, con su motivo.
  Etiquetado por tenant.

## Criterios de éxito *(obligatorio)*

- **CE-001**: el partner encarga «arregla el build», y la tarea termina con el
  build en verde sin que el partner escriba ni un solo comando.
- **CE-002**: los seis ataques de contención se resisten en macOS **y** en Windows
  — doce de doce.
- **CE-003**: en una máquina con herramientas ajenas configuradas, el catálogo de
  una sesión contiene **cero** herramientas fuera de la lista blanca del tenant.
- **CE-004**: al desconectar la máquina, el estado se refleja en menos de un minuto
  y el teammate no intenta ninguna herramienta local en el turno siguiente.
- **CE-005**: el 100 % de las ejecuciones locales es localizable en la auditoría
  con su tenant, su dispositivo y —cuando la hubo— la persona que aprobó.
- **CE-006**: un ejecutable fuera de la lista blanca nunca llega a ejecutarse, ni
  siquiera con una persona dispuesta a aprobarlo en el turno.
- **CE-007**: ningún proceso lanzado por el teammate sobrevive al final de la
  sesión — cero huérfanos en la máquina del partner.
- **CE-008**: el estado que el partner ve de un subagente coincide con lo que
  realmente ocurrió, incluidos los rechazos.
- **CE-009**: las capacidades que no usamos —navegador, control de escritorio,
  canal no oficial, carga de apps— son **inalcanzables**, no solo invisibles.
- **CE-010**: en ninguna sesión con dispositivo presente coexisten una herramienta de
  alcance externo y la ejecución local — cero casos, y el partner ve por qué.
- **CE-011**: desde el ambiente del agente no se alcanza la sesión de la consola de
  la persona — cero caminos, comprobado y no supuesto.

## Fuera de alcance

- **La beta 1** — intacta. Vive en la superficie `0` y ya está probada.
- **La beta 5, la VM compartida** — diferida en la evaluación; se reabre cuando
  exista su medición.
- **Controlar el escritorio (`3b`)**: ratón, teclado y lectura de pantalla. Es la
  mitad cara de la superficie y en Windows no tiene precedente abierto.
- **El navegador embebido** — encenderlo junto a la ejecución local es la
  combinación que §III prohíbe sin pagar las guardas de las dos.
- **Multi-seat dentro de un mismo partner** — es nuestro en cualquier escenario y
  no lo decide esta spec.
- **Móvil y navegador (betas 3 y 4)** — no bloquean a esta ni ella a ellas.

## Supuestos

- **El partner es el dueño de su máquina**, y el modelo mono-usuario del puesto de
  trabajo es cierto en esta superficie. En la nube no lo sería.
- **El directorio de trabajo lo declara el partner**, no lo descubre el sistema.
- **La lista blanca arranca vacía** por tenant: no hay ejecutables permitidos por
  defecto, y la primera se añade en el alta.
- **Un comando permitido puede escribir**; la contención acota dónde, no si.
- **El «primera vez» de la aprobación se refiere a argumentos**, no a ejecutables.
  Cerrado el 2026-09-09 en `[[10-decisiones]]` §2.7.
- **Los certificados de distribución se piden aparte y con antelación**: tienen
  plazo de entrega y hoy no están. No los produce esta spec.
- **La salida de un comando es dato, nunca instrucción** (§III), igual que
  cualquier otro contenido leído.
- **El coste de retirar marcas ajenas de la interfaz vive en el plan**, no aquí: es
  una decisión de cómo, no de qué.

## Clarificaciones cerradas (2026-09-09)

Las tres marcas de clarificación que llevaba el borrador se cerraron con
Luis antes de planificar. Se dejan escritas porque cada una cambió un requisito.

| Pregunta | Decisión | Qué cambió |
|---|---|---|
| ¿Puede el partner añadir sus propias herramientas a la sesión? | **No, nunca.** El catálogo lo configura solo Auphere | Requisito 5.4 — el 5.2 pasa a ser prohibición, no defensa |
| ¿Entran los subagentes en la beta 2? | **Sí**, con la aplicación de escritorio como superficie de aprobación | Requisito 11, nuevo |
| ¿Qué se hace sin techos de recursos en macOS y Windows? | **Acotarlo en el producto**: límite de reloj y muerte del árbol de procesos | Requisito 12, nuevo |

## Riesgo asumido a propósito

El Requisito 11 descansa en una capacidad **no verificada**: la evaluación observó
que un subagente no arranca si ninguna superficie puede contestar su aprobación, y
que la aplicación de escritorio pueda serlo está por comprobar. Se acepta el
riesgo con los ojos abiertos, y la consecuencia es de plan, no de spec:

**la verificación del Requisito 11.1 va junto a la del catálogo (Requisito 5) al
principio del plan, no al final.** Son las dos apuestas de esta spec, y las dos se
resuelven antes de construir encima. Si 11.1 falla, el Requisito 11 se retira y la
beta 2 entrega ejecución de un solo agente.
