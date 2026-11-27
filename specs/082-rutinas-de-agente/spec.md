# Especificación: rutinas, lo que un agente hace a su hora

**Rama**: `082-rutinas-de-agente` · **Creada**: 2026-11-27 · **Estado**: Borrador

**Entrada**: maqueta aprobada por el owner y las decisiones que la acompañan. La maqueta vive en `https://claude.ai/artifact/U6foMycEUSAjVbpZuvkXqP`, que es **privado de la cuenta del owner**: quien no tenga acceso tiene lo que importa en la tabla de decisiones de más abajo. Los dos ejemplos que el owner puso como criterio de si la pieza sirve: «revisa la vista de usuarios de Notion y dame la lista de los que se dieron de alta ayer», todos los días a las nueve. Y «crea un informe del rendimiento y la cobertura del agente de Jemma Hair sobre el desempeño del servicio en los últimos quince días», una sola vez, dentro de quince días.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` API de la consola. No se abre ninguna superficie nueva: la ejecución corre en el mismo worker, con el mismo grafo de herramientas y el mismo proxy de modelos que un turno de conversación. Lo nuevo es quién dispara el turno y que al otro lado no hay nadie. |
| **Garantías de aislamiento tocadas** | **1** (dos tablas nuevas por cliente, con RLS forzada y clave foránea compuesta al agente), **2** (la lista de herramientas del turno se construye con la misma intersección de siempre), **6** (todo lo que se registra lleva su cliente) y la **8**, que se refuerza en vez de aflojarse: sin conversación, ninguna herramienta que nombre a un cliente final llega siquiera a ofrecerse. |
| **Nota de KB que la justifica** | Pendiente: la pone el owner al aprobar. Hasta entonces hace de entrada la maqueta enlazada arriba. |
| **Qué se mide** | Modelo. Cada ejecución es un turno de agente y se mide por tokens como cualquier otro, con origen propio (`schedule`) y cobrada de la bolsa del cliente. |

> La superficie es la que ya está abierta. Una rutina no da al agente ninguna herramienta que no tuviera, no abre ningún canal nuevo y no habla con nadie de fuera: reparte en el tiempo lo que el agente ya sabe hacer, y la respuesta la lee el partner dentro de la consola.

## Por qué

Hoy esto se hace a mano. Alguien del partner abre la conversación con el agente a las nueve de la mañana y le escribe la misma instrucción que escribió ayer. Funciona mientras alguien se acuerde, y deja de funcionar el día que esa persona está de vacaciones o se le pasa. La rutina es ese mismo mensaje, puesto una vez en la consola y repetido solo.

Lo que ya existe y sirve, comprobado contra el repositorio:

- **La cola de trabajos** (spec 047) es el ejecutor correcto: una fila por trabajo, RLS por cliente, clave foránea compuesta al agente, latido, caducidad y coste. Una ejecución de rutina es un tipo más.
- **La bolsa** ya cobra turnos con `usage_ref` idempotente y ya sabe cobrar algo que no es atender (las pruebas a cargo del cliente). Cobrar una rutina es el mismo molde.
- **El medidor** ya separa el gasto por origen, que es lo que permite que el partner distinga lo que gasta conversando de lo que gasta en rutinas.
- **Disparar a la hora local del negocio** ya está resuelto en los recordatorios de cobranza, con la zona del cliente y un candado por día local.
- **La pausa con motivo** ya distingue la que pone una persona de la que pone el sistema, y solo el sistema deshace la suya.
- **Los permisos por conexión** ya existen con tres valores: solo leer, preguntar antes de escribir, y leer y escribir.

Lo que no existe, y es el único trabajo de fondo de esta spec: **un turno de agente sin cliente final**. El runtime está construido alrededor de una conversación con mensajes entrantes. Clasifica intención, enruta, formatea burbujas y escala a una persona. Nada de eso aplica a una rutina, que no tiene a nadie delante y cuya salida es un informe que lee el partner. Los dos turnos sin canal que existen hoy —las pruebas y el playground— corren contra un mundo simulado. Una rutina es lo contrario: mundo real, herramientas reales, nadie al otro lado.

### Decisiones de partida

Son del owner y no se reabren en esta spec.

| | Decisión |
|---|---|
| 1 | La rutina se vincula a un agente, y ese agente es de un cliente del partner. No es del partner suelto ni de un teammate. |
| 2 | Se elige cliente primero. La lista enseña las rutinas de los agentes de ese cliente, y el alta solo ofrece esos agentes. |
| 3 | El consumo sale de la bolsa de ese cliente, y se tiene que poder distinguir lo que gastan las conversaciones de lo que gastan las rutinas. |
| 4 | Cuatro periodicidades y ninguna más: cada día, cada semana con sus días, cada mes del 1 al 28, y una vez con su fecha. Nada de cron de cinco campos. |
| 5 | La hora es la del negocio, de la ficha del cliente, no la de quien la configura. |
| 6 | La respuesta aterriza siempre en la consola, y opcionalmente por correo a quien la creó. |
| 7 | Si el agente deja de atender, la rutina se pausa sola con su motivo escrito, y vuelve sola cuando el agente vuelva. |
| 8 | Tres intentos dentro de la hora siguiente. Tres ejecuciones seguidas fallidas pausan la rutina. |
| 9 | Una rutina no añade herramientas: reparte en el tiempo las que el agente ya tiene, y eso se dice en pantalla. |
| 10 | La rutina se nombra al crearla, con un tope de sesenta caracteres, y es obligatorio como la instrucción. |
| 11 | La entrada del menú se llama «Rutinas», va entre Clientes y Consumo, y su ruta es `/schedules`. |
| 12 | Una rutina hereda el permiso que el agente ya tiene sobre cada conexión. No se degrada ni se amplía por ser una rutina *(Pedro, 2026-11-27)*. |

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — escribirlo una vez y ver la respuesta (Prioridad: P1)

El partner entra en Rutinas, elige un cliente, escribe el nombre y la instrucción para uno de sus agentes y pulsa «Ejecutar ahora». El agente hace lo que le pidió, con las herramientas que ya tenía, y la respuesta aparece en la consola.

**Por qué esta prioridad**: es exactamente lo que hoy se hace a mano, y entrega valor sin que exista todavía ningún calendario. Además obliga a resolver el turno sin cliente final, que es la única pieza de fondo: lo demás se apoya en ella.

**Prueba independiente**: con una rutina guardada y cero calendario, «Ejecutar ahora» devuelve la respuesta del agente en el historial, y lo gastado aparece cobrado de la bolsa del cliente con origen de rutina.

**Escenarios de aceptación**:

1. **Dado** un agente que atiende y tiene Notion entre sus herramientas, **cuando** el partner guarda la instrucción del ejemplo del owner y pulsa «Ejecutar ahora», **entonces** el historial de esa rutina muestra una ejecución hecha, con el texto de la respuesta y las herramientas que usó.
2. **Dado** el mismo agente, **cuando** la ejecución termina, **entonces** la bolsa del cliente tiene un cargo por ese importe y el consumo lo imputa a rutinas, no a conversaciones.
3. **Dado** un agente cuyas herramientas no incluyen Notion, **cuando** la instrucción le pide mirar Notion, **entonces** el turno no le ofrece ninguna herramienta de Notion, la ejecución queda marcada parcial y deja escrito qué no se pudo hacer.

---

### Historia 2 — que se repita sola, a la hora del negocio (Prioridad: P2)

La misma instrucción, con una de las cuatro periodicidades y una hora. El partner no vuelve a tocarla: cada día, a esa hora en la zona del negocio, hay una respuesta nueva esperándole.

**Por qué esta prioridad**: es la razón de ser de la pieza. Va después de la primera porque sin ejecución no hay nada que programar.

**Prueba independiente**: con el reloj adelantado hasta la hora del negocio, la ejecución aparece sola en el historial, y con el reloj en la zona del partner, no.

**Escenarios de aceptación**:

1. **Dado** un cliente en `America/Santiago` y una rutina diaria a las 09:00, **cuando** en Santiago son las 09:00, **entonces** la ejecución arranca, aunque quien la creó esté en Madrid.
2. **Dado** una rutina de una sola vez con fecha, **cuando** esa ejecución termina, **entonces** la rutina no vuelve a ejecutarse nunca y la lista la muestra sin próxima.
3. **Dado** una rutina semanal sin ningún día marcado, **cuando** el partner intenta guardarla, **entonces** no se guarda y se le dice que elija al menos un día.

---

### Historia 3 — el historial y lo que cuesta (Prioridad: P3)

El partner abre una rutina y ve el hilo: una tarjeta por ejecución, con la respuesta dentro, lo que usó y lo que costó. Y ve, sobre la bolsa del cliente, cuánto se va en conversaciones y cuánto en rutinas.

**Por qué esta prioridad**: sin esto la pieza funciona pero no se puede defender ante el cliente, que es quien paga la bolsa.

**Prueba independiente**: con varias ejecuciones hechas, el panel de consumo del cliente reparte el gasto en dos y la suma cuadra con la bolsa.

**Escenarios de aceptación**:

1. **Dado** un cliente con gasto en conversaciones y en rutinas, **cuando** el partner abre Rutinas de ese cliente, **entonces** ve las dos cifras por separado y las dos sobre el total de su bolsa.
2. **Dado** una ejecución terminada, **cuando** el partner la abre, **entonces** ve la respuesta, las herramientas que usó, lo que tardó y lo que costó.

---

### Historia 4 — que no se desmande (Prioridad: P4)

Una rutina que falla se reintenta, y si insiste en fallar se para. Una rutina cuyo agente deja de atender se para sola y vuelve sola. Y ninguna se come la bolsa de madrugada.

**Por qué esta prioridad**: es lo que separa una pieza que se puede dejar sola de una que hay que vigilar. Va después del historial porque sin historial no se ve lo que pasó.

**Prueba independiente**: con una herramienta que falla siempre, la rutina queda en pausa después de tres ejecuciones fallidas, con su motivo escrito, y no vuelve a intentarlo.

**Escenarios de aceptación**:

1. **Dado** un agente que se pausa, **cuando** llega la hora de una de sus rutinas, **entonces** no se ejecuta, y la rutina aparece en pausa con el motivo de la pausa del agente.
2. **Dado** ese mismo agente, **cuando** vuelve a atender, **entonces** sus rutinas vuelven solas, sin que nadie las toque.
3. **Dado** una rutina creada para un agente que está en pausa, **cuando** se guarda, **entonces** nace en pausa y se le dice al partner en el momento.

---

### Historia 5 — que te llegue sin entrar a mirar (Prioridad: P5)

La respuesta avisa en la campana de la consola, y si el partner lo pidió, también le llega un correo.

**Por qué esta prioridad**: la respuesta ya está guardada y accesible sin esto. Es comodidad, y es lo primero que se recorta si hay que recortar.

**Prueba independiente**: al terminar una ejecución, aparece el aviso en la campana, y con el correo encendido sale además el correo a quien la creó.

**Escenarios de aceptación**:

1. **Dado** una ejecución que termina, **cuando** se guarda la respuesta, **entonces** la campana del partner enseña un aviso que lleva a esa ejecución.
2. **Dado** una rutina con el correo encendido, **cuando** la ejecución termina, **entonces** quien la creó recibe un correo con el enlace a la respuesta.

---

### Casos límite

- **La hora que no existe.** Una rutina mensual a las 02:30 el día que el reloj se adelanta.
- **La hora que ocurre dos veces.** La noche en que el reloj se atrasa, una rutina diaria a las 02:30 no puede ejecutarse dos veces.
- **El negocio cambia de zona horaria.** Las próximas ejecuciones ya calculadas tienen que seguir a la zona nueva.
- **El worker estuvo caído dos horas.** Nadie quiere a las dos de la tarde el informe de las nueve.
- **La bolsa se vació entre que se programó y que llegó la hora.**
- **El agente se archiva** con rutinas vivas colgando de él.
- **Dos réplicas** llegan a la misma rutina a la misma hora.
- **La respuesta es enorme**: el agente devuelve veinte páginas.
- **La instrucción pide escribir** y la conexión está puesta en «preguntar antes de escribir», cuando todavía no se puede preguntar desde la consola. La ausencia se diseña (constitución §V): la ejecución lo dice en su respuesta, no se calla.
- **El cliente se borra** o el partner pierde el acceso a él.

## Requisitos *(obligatorio)*

### Requisito 1 — la rutina cuelga de un agente de un cliente

**Historia de usuario:** Como partner, quiero que cada rutina sea de un agente concreto de un cliente concreto, para que lo que gasta y lo que puede hacer estén acotados a ese cliente.

#### Criterios de aceptación

1. El sistema DEBE guardar cada rutina con su cliente y su agente, con la misma clave foránea compuesta que ya usan los trabajos, de modo que una rutina no pueda apuntar al agente de otro cliente.
2. WHEN el partner entra en Rutinas THEN el sistema DEBE pedirle primero un cliente, y a partir de ahí ofrecer solo los agentes de ese cliente.
3. IF el partner pide una rutina de un cliente que no es suyo THEN el sistema DEBE responder como si no existiera, sin decir que existe.
4. WHEN se archiva un agente THEN el sistema DEBE conservar sus rutinas y su historial, y NO DEBE borrarlos.

### Requisito 2 — el alta

**Historia de usuario:** Como partner, quiero escribir la instrucción como se la diría al agente por chat, para no tener que aprender otra forma de hablarle.

#### Criterios de aceptación

1. El sistema DEBE pedir nombre e instrucción, los dos obligatorios, con un tope de 60 caracteres el nombre y de 2.000 la instrucción.
2. IF falta el nombre o la instrucción THEN el sistema DEBE no guardar y señalar cuál falta.
3. WHEN el alta se abre desde la ficha de un agente THEN el sistema DEBE dejar ese agente puesto y no ofrecer cambiarlo.
4. El sistema DEBE decir en el alta que la rutina no añade herramientas y nombrar las que el agente ya tiene.
5. El sistema DEBE decir en el alta de qué bolsa va a salir el gasto.

### Requisito 3 — el cuándo

**Historia de usuario:** Como partner, quiero elegir entre unas pocas periodicidades claras, para no tener que escribir un cron.

#### Criterios de aceptación

1. El sistema DEBE ofrecer exactamente cuatro periodicidades: cada día, cada semana con sus días, cada mes con un día del 1 al 28, y una sola vez con su fecha.
2. El sistema DEBE guardar la hora como hora local más la zona del negocio, y calcular cada disparo en esa zona.
3. WHERE la periodicidad es semanal EL sistema DEBE exigir al menos un día.
4. IF la hora local de un disparo no existe ese día por el cambio de hora THEN el sistema DEBE ejecutar a la primera hora que sí exista ese día.
5. IF la hora local de un disparo ocurre dos veces ese día por el cambio de hora THEN el sistema DEBE ejecutar una sola vez.
6. WHEN el partner cambia la periodicidad o la hora THEN el sistema DEBE enseñarle las próximas ejecuciones ya calculadas, antes de guardar.
7. WHEN cambia la zona horaria del negocio THEN el sistema DEBE recalcular las próximas ejecuciones de sus rutinas con la zona nueva.
8. WHEN termina la única ejecución de una rutina de una sola vez THEN el sistema DEBE dejarla sin próxima y no volver a ejecutarla.

### Requisito 4 — la ejecución es un turno sin cliente final

**Historia de usuario:** Como partner, quiero que la rutina use al agente tal como es, para que lo que me conteste sea lo mismo que me contestaría por chat.

#### Criterios de aceptación

1. WHEN llega la hora de una rutina THEN el sistema DEBE correr un turno del agente con su versión publicada, su instrucción de operador y su conocimiento, sin conversación y sin cliente final.
2. El sistema DEBE construir la lista de herramientas del turno con la misma intersección de siempre: las del agente, acotadas por lo que deja la activación de cada conexión.
3. El sistema DEBE dejar fuera del turno toda herramienta que exija una conversación, porque en una rutina no la hay.
4. El sistema NO DEBE ofrecer en el turno ninguna herramienta con la que el modelo pueda elegir a un cliente final.
5. El sistema DEBE respetar el permiso de cada conexión tal como está: solo leer deja solo las de lectura, y leer y escribir deja escribir.
6. El sistema DEBE garantizar que una escritura consecuente se hace como mucho una vez por ejecución, aunque la ejecución se reintente.
7. El sistema DEBE guardar la respuesta como texto legible, junto con las herramientas que usó, lo que tardó y lo que costó.

### Requisito 5 — lo que no se pudo tocar se dice

**Historia de usuario:** Como partner, quiero que la rutina me diga lo que no pudo hacer, para no fiarme de un informe incompleto creyendo que está entero.

#### Criterios de aceptación

1. WHERE una conexión del agente está puesta en «preguntar antes de escribir» EL sistema DEBE, mientras no exista la pregunta desde la consola, dejar fuera del turno sus herramientas de escritura.
2. WHEN una herramienta queda fuera por lo anterior THEN el sistema DEBE escribirlo en la ejecución, en una frase que diga qué no se hizo y por qué, y NO DEBE callarlo.
3. El sistema DEBE marcar esa ejecución como parcial, no como hecha.

> El criterio 5.1 es provisional y tiene fecha de caducidad: se retira cuando exista la pregunta desde la consola, que va en su propia spec.

### Requisito 6 — ejecutar ahora

**Historia de usuario:** Como partner, quiero probar la instrucción antes de dejarla puesta, para no descubrir mañana que estaba mal escrita.

#### Criterios de aceptación

1. WHEN el partner pulsa «Ejecutar ahora» THEN el sistema DEBE correr la misma ejecución que correría a su hora, con las mismas herramientas y el mismo cobro.
2. El sistema DEBE dejar esa ejecución en el historial, distinguible de las que lanzó el calendario.
3. WHEN el partner pulsa «Probar ahora» desde el alta, sin haber guardado THEN el sistema DEBE ejecutar sin crear la rutina.
4. IF la bolsa del cliente está vacía THEN el sistema DEBE no ejecutar y decirlo.

### Requisito 7 — cuando falla

**Historia de usuario:** Como partner, quiero que un fallo pasajero no me deje sin el informe del día, y que uno que no es pasajero no me vacíe la bolsa.

#### Criterios de aceptación

1. El sistema DEBE tratar una ejecución y sus intentos como una sola cosa: **la ejecución es el conjunto de sus intentos**, y en el historial se ve una sola tarjeta con cuántos intentos llevó.
2. IF un intento falla THEN el sistema DEBE lanzar otro, hasta **tres intentos en total**, dentro de la hora siguiente a la hora de esa ejecución, y cada intento DEBE ser un trabajo nuevo en la cola.
3. El sistema NO DEBE lanzar un intento pasada esa hora, aunque le queden intentos por gastar.
4. IF los tres intentos fallan, o se acaba la hora antes de gastarlos THEN el sistema DEBE dar la ejecución por fallida, dejar el error escrito y esperar a la siguiente de su calendario.
5. IF tres **ejecuciones** seguidas de una rutina acaban fallidas THEN el sistema DEBE pausar la rutina con su motivo escrito y avisar al partner. El contador cuenta ejecuciones, nunca intentos.
6. IF la hora de una ejecución pasó hace más de una hora sin que llegara a empezar THEN el sistema DEBE darla por no ejecutada, dejar el motivo escrito y esperar a la siguiente, y NO DEBE ejecutarla tarde.
7. El sistema DEBE garantizar que dos réplicas que lleguen a la misma ejecución la corran una sola vez.

### Requisito 8 — cuando el agente no atiende

**Historia de usuario:** Como partner, quiero no tener que acordarme de parar las rutinas cuando paro un agente.

#### Criterios de aceptación

1. WHEN un agente deja de atender, por pausa, por despublicación o por archivo THEN el sistema DEBE dejar sus rutinas sin ejecutarse, con el motivo escrito y visible.
2. WHEN ese agente vuelve a atender THEN el sistema DEBE volver a ejecutar sus rutinas sin que nadie las toque, salvo las que una persona pausó a mano.
3. WHEN se crea una rutina para un agente que no atiende THEN el sistema DEBE crearla en pausa y decirlo en el momento.
4. IF la bolsa del cliente se vacía THEN el sistema DEBE dejar de ejecutar sus rutinas y volver a ejecutarlas cuando haya saldo, con el mismo criterio con el que ya se paran y se reanudan sus agentes.

### Requisito 9 — lo que gasta

**Historia de usuario:** Como partner, quiero poder decirle a mi cliente cuánto de su bolsa se va en rutinas, para que el cargo no le sorprenda.

#### Criterios de aceptación

1. El sistema DEBE cobrar cada ejecución de la bolsa del cliente del agente, con un origen propio que la distinga de un turno de conversación.
2. El sistema DEBE garantizar que la misma ejecución no se cobra dos veces.
3. El sistema DEBE enseñar, sobre la bolsa del cliente, lo gastado en conversaciones y lo gastado en rutinas por separado, con su importe y su parte del total.
4. El sistema NO DEBE sumar lo que gasta una rutina al tope del agente, que habla de lo que gasta atendiendo.
5. El sistema DEBE escribir los importes como ya los escribe la consola, «12,80 US$».
6. [NEEDS CLARIFICATION: ¿Rutinas es también una partida visible en la pantalla de Consumo del partner, junto a Conversaciones, Construcción y pruebas, Meta y Companion, o solo se ve dentro de Rutinas y en la bolsa del cliente? Lo decide el owner.]

### Requisito 10 — dónde aterriza la respuesta

**Historia de usuario:** Como partner, quiero enterarme de que hay respuesta sin tener que entrar a mirar.

#### Criterios de aceptación

1. El sistema DEBE guardar siempre la respuesta en el historial de la rutina, lo vea quien lo vea del equipo del partner.
2. WHEN una ejecución termina THEN el sistema DEBE dejar un aviso en la campana que lleve a esa ejecución.
3. WHERE la rutina tiene el correo encendido EL sistema DEBE mandar a quien la creó un correo con el enlace a la respuesta.
4. IF una ejecución queda parcial o fallida THEN el aviso DEBE decirlo, y no anunciarla como hecha.

### Requisito 11 — quién puede

**Historia de usuario:** Como dueño de la cuenta del partner, quiero decidir quién puede poner a un agente a gastar solo.

#### Criterios de aceptación

1. El sistema DEBE exigir un permiso propio para leer rutinas y otro para crearlas, pausarlas y ejecutarlas.
2. El sistema DEBE dar esos permisos a los mismos roles que hoy pueden leer y escribir agentes.
3. IF alguien sin el permiso de escritura intenta crear, pausar o ejecutar THEN el sistema DEBE rechazarlo.
4. El sistema NO DEBE enseñar las rutinas en la consola del cliente.

### Requisito 12 — topes y retención

**Historia de usuario:** Como partner, quiero un techo, para que un error de configuración no se lleve la bolsa de un cliente por la noche.

#### Criterios de aceptación

1. El sistema DEBE limitar a veinte las rutinas activas de un cliente, y decirlo cuando se llega al tope.
2. El sistema DEBE conservar el historial de ejecuciones durante la misma ventana que los mensajes y retirarlo después. La spec pide la ventana, no la técnica: cómo se retira lo elige el plan.
3. El sistema NO DEBE retirar lo medido del consumo, que es la base de facturar.

### Requisito 13 — queda dicho quién y desde dónde

**Historia de usuario:** Como responsable de la cuenta, quiero poder distinguir en la auditoría lo que hizo un agente atendiendo de lo que hizo solo.

#### Criterios de aceptación

1. WHEN una rutina escribe fuera THEN el sistema DEBE dejarlo en la auditoría con la rutina que lo originó y la persona que la creó.
2. El sistema DEBE registrar el alta, la pausa, la reanudación y el borrado de una rutina con quién lo hizo.
3. El sistema DEBE poder distinguir en la auditoría una acción de una rutina de la misma acción hecha en una conversación.

### Requisito 14 — la lista de un cliente

**Historia de usuario:** Como partner, quiero ver de un vistazo las rutinas de un cliente y en qué estado están, para saber cuál me está esperando sin abrirlas una a una.

#### Criterios de aceptación

1. WHEN el partner elige un cliente THEN el sistema DEBE enseñar las rutinas de todos sus agentes con, cada una: su nombre, su agente, cuándo se ejecuta, su próxima ejecución, su última ejecución y cómo acabó, lo que lleva gastado este mes y su estado.
2. El sistema DEBE dejar filtrar por agente y por estado, y enseñar en cada filtro cuántas rutinas caen dentro.
3. IF ninguna rutina cumple el filtro THEN el sistema DEBE decirlo, y NO DEBE enseñar una lista vacía sin explicación.
4. WHERE el cliente no tiene ninguna rutina EL sistema DEBE enseñar en su lugar qué es una rutina y cómo se crea la primera, sin botones apagados.
5. WHERE una rutina está pausada por el sistema EL sistema DEBE enseñar su motivo en la lista, sin tener que abrirla.
6. El sistema DEBE decir en la lista que una rutina no añade herramientas.

### Requisito 15 — cambiarla, pausarla y archivarla

**Historia de usuario:** Como partner, quiero corregir una rutina que escribí mal y retirar la que ya no sirve, sin perder lo que me contestó.

#### Criterios de aceptación

1. El sistema DEBE dejar cambiar el nombre, la instrucción, la periodicidad, la hora y el correo de una rutina, con las mismas validaciones del alta.
2. WHEN cambia la instrucción THEN el sistema DEBE conservar en cada ejecución ya hecha la instrucción con la que se ejecutó, y NO DEBE reescribir el historial con la nueva.
3. El sistema DEBE dejar al partner pausar y reanudar una rutina a mano, y esa pausa NO DEBE deshacerla el sistema cuando su agente vuelva a atender.
4. El sistema DEBE dejar archivar una rutina, que entonces deja de ejecutarse y conserva su historial para consultarlo.
5. WHEN se restaura una rutina archivada THEN el sistema DEBE dejarla en pausa, nunca ejecutándose, para que alguien confirme su hora antes de que vuelva a gastar.
6. El sistema NO DEBE borrar una rutina ni su historial.

### Entidades clave

- **Rutina**: lo que el partner configura una vez. Nombre, instrucción, periodicidad con sus días o su fecha, hora local, si manda correo, quién la creó y su estado. Pertenece al **cliente** (`tenant_id`), que es la columna por la que la alcanza la RLS, y apunta a su agente por la clave compuesta `(tenant_id, agent_id)`. No guarda nada de ningún cliente final, porque no hay.
- **Ejecución**: cada vez que la rutina corre. Cuándo se disparó, en qué estado acabó, la respuesta, las herramientas que usó, lo que tardó, lo que costó y, si falló, el error. Pertenece al mismo **cliente** por `tenant_id`, y a su rutina.

## Criterios de éxito *(obligatorio)*

- **CE-001**: el partner escribe el primer ejemplo del owner, lo deja puesto, y a la mañana siguiente la respuesta está en la consola sin que nadie haya tocado nada.
- **CE-002**: el segundo ejemplo del owner, el informe a quince días, se programa una vez, se ejecuta ese día y no vuelve a ejecutarse.
- **CE-003**: ante un cliente que pregunta por su factura, el partner puede decir cuánto de la bolsa se fue en conversaciones y cuánto en rutinas, y las dos cifras suman lo cobrado.
- **CE-004**: una rutina cuyo agente se pausa no gasta nada mientras está pausado, y vuelve sola sin intervención.
- **CE-005**: una rutina que no puede hacer parte de lo que se le pidió lo dice en su respuesta, y nunca aparece como hecha.
- **CE-006**: ninguna ejecución de un cliente ve, toca ni cobra datos de otro cliente.

## Fuera de alcance

- **Preguntar desde la consola por una escritura que necesita permiso** — es una pieza con su propio diseño (a quién se le pregunta, cómo se reanuda la ejecución) y va en su spec. Aquí solo se deja dicho lo que no se hizo.
- **Que la respuesta salga por WhatsApp o avise a un móvil** — abre un camino hacia clientes finales, y esta pieza no abre esa frontera.
- **Encadenar rutinas, condiciones o ramas** — eso es un workflow, y ese camino ya se intentó.
- **Las rutinas en la consola del cliente** — hoy el negocio ve panel, bandeja, reservas y consumo. Meterlas sería un módulo nuevo y una decisión aparte.
- **Periodicidades libres tipo cron** — decisión 4 del owner.
- **Editar la instrucción de una ejecución ya hecha** — el historial es lo que pasó, no se reescribe.

## Supuestos

- Una rutina hereda el permiso de cada conexión tal como está, sin degradarlo ni ampliarlo por ser una rutina *(decidido con Pedro el 2026-11-27)*.
- La ventana de gracia de una ejecución que se saltó es de una hora. Pasada, se da por no ejecutada.
- Rutinas se ve como una partida propia sobre la bolsa del cliente, dentro de Rutinas. Si además es una partida de la pantalla de Consumo del partner está abierto en el criterio 9.6, y es lo único que bloquea el paso a planificar.
- El correo de la primera ola es un aviso con enlace a la consola, no la respuesta entera: la plantilla genérica de hoy admite titular, una frase y un botón.
- El tope de veinte rutinas activas por cliente es un valor de partida, no un límite técnico.
- Una rutina archivada se consulta y se puede restaurar, y al restaurarse queda en pausa. Es el mismo trato que ya reciben los agentes, así que no abre una decisión nueva.
- Se reutiliza la cola de trabajos existente como ejecutor, y el grafo del agente como motor del turno. No se crea un ejecutor nuevo.
- El reloj del negocio sale de la zona horaria que ya tiene su ficha.
