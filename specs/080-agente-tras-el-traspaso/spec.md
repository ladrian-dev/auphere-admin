# Especificación: El agente tras el traspaso y la disponibilidad

**Rama**: `080-agente-tras-el-traspaso` · **Creada**: 2026-11-26 · **Estado**: Decidida con Luis el 2026-11-26, lista para planificar

**Entrada**: descripción del usuario: «Spec 080 "El agente tras el traspaso y la disponibilidad". R1: el freno de reservas da por buena una reserva viva del cliente de la conversación, creada o cambiada en el ciclo actual, también las hechas por una persona en la consola, con prueba de aislamiento (garantía 8). R3: las intenciones `fallback` y `escalate` conservan las herramientas de reservas que el agente tenga, catálogo incluido, para que un "gracias" o una queja a mitad de reserva no dejen al agente sin poder comprobar ni seguir. R4: `reservas.find_slots` acepta no dar fecha y devuelve los primeros horarios libres desde ahora, cruzando días, y la descripción deja de prometer `first_fit` en modo servicios. R5: la cancelación hecha por el agente se registra como del agente, no del cliente. R2 (recortable): los mensajes del equipo, marcados como del equipo en el historial del modelo. Fuera: el clasificador con las reglas del partner, la ventana de agrupación de mensajes y los cambios de interfaz.»

> La aclaración del 2026-11-26 deja R2 fuera (ver Clarifications y Fuera de alcance).
> Los requisitos de abajo van numerados del 1 al 4.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: el runtime del turno y las herramientas `reservas.*` del agente, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **8 (cliente final dentro del tenant), tocada por el requisito 1.** El freno pasa a mirar también las reservas del cliente final de la conversación, y no solo las de la conversación. Ese cliente lo resuelve el servidor a partir de la conversación y nunca llega como argumento. Una reserva de otra persona del mismo negocio sigue sin existir para el freno. **2 (lista blanca exhaustiva), rozada por el requisito 2.** Más intenciones reciben herramientas de reservas, siempre dentro de la lista blanca del agente: lo que el agente no tiene no aparece en ningún turno. Ninguna otra: no se mueven datos entre negocios. |
| **Nota de KB que la justifica** | `[[research/2026-11-26-beta-jemma-p0-p1]]` en `/Users/lmatos/Work/Auphere/nexus/`, sección 080 |
| **Qué se mide** | **Nada nuevo.** No hay llamadas nuevas al modelo. Los turnos de saludo y de paso a persona de un agente con Reservas llevan más definiciones de herramientas, es decir, más tokens de entrada, casi todos en caché. Se cobran en la bolsa del cliente igual que hoy. Buscar sin fecha sustituye varias llamadas a la herramienta por una. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 056, **R1.1** (el freno de citas) | La respuesta que da por hecha una cita tiene que estar respaldada por una reserva de esa conversación. | También la respalda una reserva viva del cliente final de esa conversación creada o cambiada en el ciclo actual, la haga quien la haga (requisito 1). |
| Spec 047, clarificación «¿Se toca el enrutado del turno por intenciones…?» (`spec.md:179`) | Fuera; queda como seguimiento. | Se resuelve para Reservas: saludo y paso a persona conservan sus herramientas (requisito 2). El enrutado del resto no cambia. |
| Spec 043, **R6** (herramientas del agente) | `reservas.find_slots` busca un día concreto. | Si no se da día, devuelve los primeros horarios libres desde ahora, cruzando días (requisito 3). |
| Spec 043, **R6.2–R6.3**, en lo que deja en el historial de la reserva | Crear y mover quedan a nombre del agente; cancelar queda a nombre del cliente. | Cancelar también queda a nombre del agente, y sigue constando que lo decidió el cliente (requisito 4). |

## Por qué

En la beta de Jemma's Hair (partner Autprod), Neliana vio dos cosas que parecen fallos del modelo y que se explican por cómo está montado el turno. Se revisaron contra los registros de producción y el panel de operador.

1. **«El agente alucinó tras el traspaso a persona».** Conversación de uñas acrílicas, 23 de noviembre:
   - **18:21 UTC.** Una persona del salón creó la reserva desde la agenda: sábado 28 a las 15:00, con Daybeth. El sistema mandó al cliente su confirmación.
   - **18:22.** La persona escribió «¡Su cita ha sido agendada…!» y devolvió la conversación al agente.
   - **Después.** El cliente contestó «Excelente muchas gracias».

   Con ese «gracias» pasaron tres cosas:
   - **El turno se quedó sin agenda.** Se clasificó como saludo o agradecimiento (`fallback`), y esa intención no lleva ninguna herramienta de Reservas.
   - **El freno no vio la reserva.** Solo acepta reservas atadas a esa conversación, y la consola no ata a ninguna conversación las reservas que se crean a mano.
   - **El freno reintentó y el agente escaló.** Reintentó con la nota «no hay ninguna reserva hecha en esta conversación». El agente no tenía herramientas para comprobarlo y pasó la conversación a una persona: «Esto necesita que lo revise una persona del equipo». El cliente tuvo que escribir «Otra vez».

   El texto exacto del primer borrador no se guarda, así que lo que decía es una inferencia. Los hechos registrados son tres: la clasificación, el freno con reintento y el paso a persona.

   Antes, a las 18:06, el cliente escribió «Roxana no me gusta como me atiende»:
   - El clasificador decide con significados genéricos («se queja»), sin las reglas del partner («Pedir otra profesional no cuenta»).
   - Con la etiqueta `escalate` el agente solo tiene la herramienta de pasar a persona, así que no podía seguir la reserva con Daybeth.

2. **«Ofreció el martes 24 antes que el hueco del lunes 23».** `reservas.find_slots` busca un solo día por llamada, y el modelo tiene que elegir cuál.
   - **Con Luna**, cuando el cliente no dio día, buscó directamente mañana. Pasó en dos de dos casos: a las 13:24 y a las 16:24, hora de Caracas. La herramienta devolvió justo lo que se le pidió, que solo era el martes.
   - **Con Sol**, el 18 de noviembre, recorrió los días uno a uno desde hoy: seis llamadas en un turno.
   - **Las instrucciones de Jemma** piden «lo antes posible: los tres primeros espacios», y la herramienta no puede darlo en una llamada.
   - **Su descripción** sugiere usar `first_fit`, que en modo servicios nunca se rellena.

3. Para el informe del piloto (spec 083) hace falta contar lo que hizo el agente en la agenda. Crear y mover quedan a su nombre, pero **cancelar queda a nombre del cliente**.

## Clarifications

### Session 2026-11-26

Luis dio por buenas todas las decisiones al recibir el plan validado («Me queda claro, empieza a trabajar en los P0 y P1»).

- Q: ¿Qué reservas respaldan una respuesta, además de las de la conversación? → A: Las vivas del cliente final de la conversación, creadas o cambiadas desde que empezó el ciclo actual, las haga quien las haga. Una cita de ese cliente de antes del ciclo no respalda «quedó reservada»: se sigue respaldando con `reservas.list_mine`, como hoy.
- Q: ¿Qué herramientas conservan el saludo y el paso a persona? → A: Las mismas de Reservas y de catálogo que tiene un turno de reservar, siempre dentro de la lista blanca del agente. El paso a persona se sigue ofreciendo.
- Q: ¿Cuántos horarios devuelve la búsqueda sin fecha? → A: Los primeros libres en orden cronológico, hasta un tope fijo que decide el plan. Cada uno con su fecha y su día de la semana, dentro de la ventana de reserva y respetando la antelación del agente.
- Q: ¿Entra marcar en el historial los mensajes del equipo (R2)? → A: No. Con los requisitos 1 y 2, el caso observado queda resuelto. No hay pruebas de que marcar esos mensajes cambie el resultado. Si vuelve a verse, se abre aparte.
- Q: ¿Quién decide una cancelación hecha por el agente? → A: El cliente, como hoy, a efectos de política. Lo que cambia es quién la ejecutó: el agente.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1: Tras una reserva hecha por el equipo, un «gracias» se contesta con normalidad (Prioridad: P1)

Una persona del negocio toma la conversación, reserva la cita desde la agenda y la devuelve al agente. El cliente da las gracias. El agente le responde con normalidad, recordándole la cita si procede, sin dudar de ella ni pasarlo otra vez a una persona.

**Por qué esta prioridad**: es lo que vio el cliente piloto. Rompe la confianza en el agente justo cuando el negocio ya había resuelto el caso.

**Prueba independiente**: se reproduce la conversación de acrílicos con una reserva creada desde la consola para ese cliente. El turno del «gracias» no pasa a una persona y el freno no actúa.

**Escenarios de aceptación**:

1. **Dado** que una persona creó desde la agenda una reserva para el cliente de la conversación y la devolvió al agente, **cuando** el cliente escribe «Excelente, muchas gracias», **entonces** el agente responde sin pasar la conversación a una persona y sin negar la cita.
2. **Dado** lo mismo, **cuando** el borrador del agente menciona la cita del sábado, **entonces** el freno lo da por respaldado y la respuesta sale al primer intento.
3. **Dado** que la reserva de la agenda es de **otra** persona del mismo negocio, **cuando** el agente da por hecha una cita, **entonces** el freno actúa como hoy: reintenta y, si se repite, pasa a una persona.
4. **Dado** que la reserva se canceló antes del «gracias», **cuando** el agente la da por hecha, **entonces** el freno actúa como hoy.

---

### Historia 2: Un saludo o una queja a mitad de reserva no dejan al agente sin agenda (Prioridad: P1)

En mitad de una reserva el cliente dice algo que se clasifica como saludo, agradecimiento o queja. El agente sigue pudiendo consultar el catálogo, la disponibilidad y las citas del cliente, y sigue pudiendo reservar. Decide con las reglas de su negocio si sigue o pasa la conversación a una persona.

**Por qué esta prioridad**: sin herramientas, la única salida del agente es pasar a persona, aunque el negocio haya dicho que «pedir otra profesional no cuenta».

**Prueba independiente**: un turno clasificado como `fallback` y otro como `escalate`, en un agente con Reservas, reciben las herramientas de Reservas de su lista blanca. En un agente sin Reservas no aparece ninguna.

**Escenarios de aceptación**:

1. **Dado** un agente con Reservas, **cuando** el turno se clasifica como saludo o agradecimiento, **entonces** el modelo tiene las herramientas de catálogo, disponibilidad, citas del cliente, reservar, mover y cancelar que tenga el agente.
2. **Dado** un agente con Reservas, **cuando** el turno se clasifica como paso a persona, **entonces** el modelo tiene esas mismas herramientas además de la de pasar a persona.
3. **Dado** un agente sin Reservas, **cuando** llega cualquiera de esos turnos, **entonces** no aparece ninguna herramienta de Reservas.

---

### Historia 3: «Lo antes posible» devuelve de verdad lo primero libre (Prioridad: P1)

El cliente pide una cita sin decir día, o pide «lo antes posible». El agente busca sin fecha y ofrece los primeros horarios libres desde ahora, que serán de hoy si queda alguno. No tiene que adivinar el día ni consultar los días de uno en uno.

**Por qué esta prioridad**: es el segundo fallo que vio el cliente piloto y pasa con cualquier modelo pequeño, también con Haiku, que será el modelo por defecto de los agentes nuevos.

**Prueba independiente**: se pide disponibilidad sin fecha cuando a un profesional le quedan horas hoy y también mañana. Los primeros horarios devueltos son los de hoy, en orden.

**Escenarios de aceptación**:

1. **Dado** que hoy quedan horas libres a partir de las 16:00 y son las 13:24, **cuando** el agente busca sin fecha, **entonces** el primer horario devuelto es el de hoy a las 16:00, con su fecha y su día de la semana.
2. **Dado** que hoy no queda nada, **cuando** busca sin fecha, **entonces** los primeros horarios son los del siguiente día con hueco, saltando los días cerrados.
3. **Dado** que no hay nada libre en toda la ventana de reserva, **cuando** busca sin fecha, **entonces** la herramienta lo dice, sin horarios y con el motivo.
4. **Dado** que se pide un día concreto, **cuando** busca con fecha, **entonces** el resultado es el de hoy, sin cambios.

---

### Historia 4: Lo que cancela el agente cuenta como del agente (Prioridad: P2)

Cuando el cliente pide cancelar y el agente lo hace, el historial de la reserva dice que la canceló el agente a petición del cliente.

**Por qué esta prioridad**: el informe del piloto (spec 083) cuenta lo que hizo el agente en la agenda. Sin esto, sus cancelaciones se cuentan como del cliente.

**Prueba independiente**: el agente cancela una reserva, y el historial nombra al agente como quien la ejecutó y al cliente como quien la decidió.

**Escenarios de aceptación**:

1. **Dado** que el cliente pide cancelar su cita, **cuando** el agente la cancela, **entonces** el historial registra al agente como autor de la cancelación y la cancelación sigue figurando como decidida por el cliente.
2. **Dado** cancelaciones de antes de este cambio, **cuando** se leen, **entonces** siguen como estaban: no se reescriben.

---

### Casos límite

- **Reserva hecha a mano con otro teléfono.** La consola enlaza la reserva al cliente por los dígitos del teléfono. Si la persona escribe el número en otro formato (local en vez de internacional), la reserva queda en otro contacto y el freno no la ve. El comportamiento sería el de hoy, nunca peor. Corregir cómo se escribe el teléfono en la consola queda fuera (ver Supuestos).
- **Reserva cambiada en este ciclo pero creada antes.** Cuenta: mover también es «cambiar con éxito» (spec 056, R1.3).
- **Agente de recepción que deriva a otro agente.** Cada agente recibe las herramientas de su propia lista blanca. La de recepción no gana herramientas de Reservas que no tenga.
- **Playground y pruebas del agente.** La agenda es la simulada, y el freno ya la lee como hasta ahora (`simulated_booking_stands`). La búsqueda sin fecha funciona igual sobre la agenda simulada.
- **Modo capacidad (Aforo).** Buscar sin fecha devuelve también las primeras horas con plazas para ese número de personas. Ahí `first_fit` sigue existiendo.
- **Antelación mínima.** Sin fecha, las horas anteriores a «ahora + antelación» no se ofrecen. Se informan como se informa hoy al buscar el día de hoy.
- **Una conversación siempre tiene cliente final** (`customer_id` no admite nulos). El caso «sin cliente» es un turno sin conversación, que ya hoy no respalda. Una reserva sin cliente, hecha sin teléfono, no es de nadie.

## Requisitos *(obligatorio)*

### Requisito 1: El freno ve las reservas del cliente hechas en este ciclo

**Historia de usuario:** Como negocio, quiero que mi agente no dude de una cita que acabo de reservar a mano para ese cliente, para que no lo pase otra vez a una persona cuando ya está resuelto.

#### Criterios de aceptación

1. WHEN el freno comprueba si una respuesta que da por hecha una cita está respaldada THEN el sistema DEBE contar como respaldo, además de lo que ya cuenta hoy, una reserva viva del cliente final de esa conversación que se haya creado o cambiado con éxito desde que empezó el ciclo actual de la conversación, sea quien sea el que la creó o la cambió (agente, persona del negocio o cliente).
2. El sistema DEBE tomar el cliente final de la conversación tal como lo resolvió el servidor, y NO DEBE aceptar ningún dato del modelo ni del mensaje para decidir de quién son las reservas que mira.
3. IF la reserva es de otro cliente final del mismo negocio THEN el sistema NO DEBE contarla como respaldo, ni pidiéndola por su identificador.
4. IF la reserva está cancelada, o se creó y no se ha cambiado desde antes del ciclo actual, THEN el sistema NO DEBE contarla por este criterio. Lo que ya cuenta hoy sigue contando igual.
5. WHERE el turno no tiene conversación, el sistema DEBE comprobar solo lo que comprueba hoy. Una reserva sin cliente final (hecha sin teléfono) NO DEBE respaldar ninguna conversación.
6. El reintento, el paso a persona, el registro del freno y su coste NO DEBEN cambiar.

### Requisito 2: Saludo y paso a persona conservan las herramientas de Reservas

**Historia de usuario:** Como negocio, quiero que mi agente pueda comprobar y seguir una reserva aunque el cliente dé las gracias o se queje, para que decida con mis reglas y no por falta de herramientas.

#### Criterios de aceptación

1. WHERE el agente tiene herramientas de Reservas en su lista blanca, WHEN un turno se clasifica como saludo, agradecimiento o charla (`fallback`) THEN el sistema DEBE ofrecer al modelo las mismas herramientas de Reservas y de catálogo que en un turno clasificado como reservar.
2. WHERE el agente tiene herramientas de Reservas, WHEN un turno se clasifica como paso a persona (`escalate`) THEN el sistema DEBE ofrecer esas mismas herramientas además de las que ya ofrece en ese turno.
3. El sistema NO DEBE ofrecer en ningún turno una herramienta que no esté en la lista blanca del agente.
4. El sistema DEBE seguir ofreciendo pasar a una persona en esos turnos cuando el agente la tenga.
5. La clasificación del turno NO DEBE cambiar.

### Requisito 3: Buscar disponibilidad sin fecha

**Historia de usuario:** Como cliente final, quiero que cuando pido «lo antes posible» me ofrezcan lo primero que de verdad está libre, para no reservar mañana algo que había hoy.

#### Criterios de aceptación

1. WHEN el agente busca disponibilidad sin indicar fecha THEN la herramienta DEBE devolver los primeros horarios libres a partir de ahora, en orden cronológico. Empieza por hoy en la zona horaria del negocio, sigue por los días siguientes y se detiene al llegar al tope de horarios o al final de la ventana de reserva.
2. Cada horario devuelto DEBE llevar su fecha y su día de la semana.
3. La búsqueda sin fecha DEBE aplicar los mismos filtros (servicio, profesional, número de personas), la misma antelación mínima del agente, el mismo horario del negocio y de cada profesional y la misma ventana de reserva que la búsqueda con fecha.
4. IF no hay ningún horario libre en toda la ventana THEN la herramienta DEBE devolverlo vacío y con el motivo, y NO DEBE inventar horarios.
5. WHEN el agente busca con fecha THEN la herramienta DEBE comportarse como hoy.
6. La descripción de la herramienta DEBE indicar al modelo que busque sin fecha cuando el cliente no da día o pide lo antes posible.
7. La descripción NO DEBE pedirle que use `first_fit` en el modo en que no se rellena.

### Requisito 4: La cancelación del agente queda a su nombre

**Historia de usuario:** Como partner, quiero que el historial de la agenda distinga lo que hizo el agente de lo que hizo el cliente, para contarlo en el informe del piloto.

#### Criterios de aceptación

1. WHEN el agente cancela una reserva a petición del cliente THEN el sistema DEBE registrar al agente como autor de la cancelación, y DEBE seguir registrando que la cancelación la decidió el cliente.
2. El sistema NO DEBE reescribir las cancelaciones anteriores a este cambio.

### Entidades clave

- **Reserva**: cita del negocio. Pertenece a un tenant, y la RLS la alcanza por `tenant_id`. Puede tener cliente final, conversación o ninguno de los dos. Aquí se lee, no se crea ninguna entidad nueva.
- **Historial de la reserva**: cada creación, cambio o cancelación, con quién la ejecutó. Pertenece al tenant de la reserva.
- **Ciclo de la conversación**: desde que se abrió, o se reabrió tras resolverse, hasta ahora (spec 064). No es una entidad: es el punto desde el que el agente lee el hilo.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Se reproduce el caso de acrílicos: reserva hecha a mano para el cliente, devolución al agente y «gracias». El agente responde sin pasar a una persona en el 100 % de las ejecuciones de la prueba.
- **CE-002**: Una reserva de otra persona del mismo negocio no respalda nunca una respuesta: 0 casos en la prueba de aislamiento.
- **CE-003**: Se pide cita sin día cuando quedan horas hoy. El primer horario que el agente ofrece es de hoy en el 100 % de los casos de prueba, con el modelo de la beta (Luna) y con el modelo por defecto de los agentes nuevos (Haiku 5.5).
- **CE-004**: Un «lo antes posible» se resuelve con una búsqueda, no con una por día.
- **CE-005**: Ningún turno ofrece una herramienta fuera de la lista blanca del agente: 0 casos en las pruebas de saludo y paso a persona.
- **CE-006**: Las cancelaciones del agente posteriores al cambio cuentan como del agente en el historial: el 100 %.

## Fuera de alcance

- **Marcar en el historial del modelo los mensajes del equipo (R2 de la entrada).** Con los requisitos 1 y 2 el caso observado queda resuelto, y no hay pruebas de que cambie el resultado.
- **Que el clasificador lea las reglas del partner.** Con el requisito 2, la etiqueta ya no quita herramientas a un agente con Reservas, y quien decide si pasar a persona es el modelo con las reglas del negocio.
- **La ventana para agrupar mensajes seguidos.** Es un ajuste del entorno y Luis lo decide aparte.
- **El enrutado por intención del resto de herramientas** (colas, conectores). Solo se ve el caso de Reservas.
- **Que `info` reciba la herramienta de disponibilidad.** No se ha observado ningún fallo por esto. Si aparece, se abre aparte.
- **Cómo escribe la consola el teléfono de una reserva hecha a mano.** Ver Supuestos.
- **Cambios de interfaz.** No hay ninguno.

## Supuestos

- La consola enlaza la reserva hecha a mano con el cliente final por los dígitos del teléfono. En el caso de acrílicos funcionó: la confirmación llegó al mismo hilo. Si se escribe en otro formato, el freno no la ve. Corregir ese formato es trabajo de la consola, no de esta spec.
- El ciclo actual es el que ya define la spec 064: desde la apertura, o desde el corte de la última reapertura.
- El tope de horarios de la búsqueda sin fecha lo fija el plan. Debe cubrir lo que piden las instrucciones habituales, como «los tres primeros», sin inflar la respuesta.
- La ventana de reserva («desde hoy hasta N días») y la antelación del agente ya son ajustes del cliente. No se tocan.
