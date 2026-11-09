# Especificación: La agenda desde el agente

**Rama**: `057-agenda-desde-el-agente` · **Creada**: 2026-11-09 · **Estado**: Aprobada para implementar, completa (Luis, 2026-11-09)

**Entrada**: descripción del usuario: "«Gestiona citas» como interruptor por agente, en el alta y en la edición, tratado como un conector. Si se enciende, el agente lleva las 9 herramientas de Reservas desde su primera versión y, si Reservas está apagado para el cliente, se enciende en ese mismo paso. Incluye corregir el aviso desactualizado «No tenemos herramienta para»."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` API de la consola. No abre ninguna superficie nueva. |
| **Garantías de aislamiento tocadas** | **1** (RLS: encender Reservas y cambiar la lista del agente se hacen en el cliente de la ruta, nunca en uno que llegue en el cuerpo) y **2** (lista blanca por agente: un agente lleva la agenda solo si su interruptor está encendido; encender Reservas para el cliente no se la da a quien no da citas). |
| **Nota de KB que la justifica** | `[[research/2026-11-09-agenda-desde-el-agente]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Modelo**: la propuesta de texto del requisito 3 es una llamada del constructor y cuenta como construcción, igual que «Generar borrador». Encender el interruptor no gasta nada más. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 047, decisión **D67** | La agenda es del módulo Reservas y no se conecta desde el agente. Con el módulo apagado, el constructor no la ve. | El módulo sigue mandando (sin Reservas encendido no hay `reservas.*`), pero **el agente puede encenderlo**: «Gestiona citas» en el alta y en Conectores. |
| Spec 047, **17.1** | «Nuevo agente» pide el nombre y «¿Qué tiene que hacer?». | Pide además «Gestiona citas» (requisito 1). |
| Spec 047, **67.6** | No se ofrece encender todas las herramientas de un conector de golpe. | Excepción: la agenda se enciende entera (las 9), y luego se puede apagar una a una. |
| Spec 043, **11.5** | Al encender Reservas, el borrador de **cada** agente activo gana `reservas.*`. | Solo el de los agentes que dan citas (requisito 5). |
| Spec 043, decisión de la sesión del 2026-11-05 sin Luis | «Si el cliente no puede reservar, su agente no se publica ni se enciende Reservas.» | Para el alta y la edición: se enciende, se publica con aviso y el agente pasa las citas a una persona hasta que esté listo (requisito 4). El paso automático del despliegue (043, 11.4) no cambia. |

## Por qué

El 2026-11-08 se creó en staging el agente «Recepción de Spa Jemma» con Reservas apagado para el cliente. El constructor no ve la agenda con el módulo apagado (D67), así que la versión 1 salió con dos herramientas, sin agenda, y con la alternativa «toma los datos y pasa al equipo para que confirme». Una clienta escribió por WhatsApp «quiero agendar una cita para mañana a las 10» y el agente contestó «la cita quedará confirmada solo cuando el equipo revise la disponibilidad», y escaló. Reservas se encendió 45 minutos después desde Acceso: eso preparó un borrador con las 9 herramientas, sin publicarlo y sin que nada lo dijera, y la conversación siguió con la versión sin agenda. Cuando por fin se publicó con agenda, la consola seguía diciendo «No tenemos herramienta para: reservar citas», porque ese aviso es lo que el constructor guardó al crear el agente y nunca se recalcula.

Tres fallos, uno por historia: **el orden importa y nadie lo dice**, **encender Reservas no llega al agente**, y **el aviso miente**.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Crear un agente que da citas, listo desde la primera versión (Prioridad: P1)

Un partner crea el agente de recepción de un cliente nuevo. En «Nuevo agente», además del nombre y de qué tiene que hacer, ve «Gestiona citas», ya encendido porque la descripción habla de citas. Reservas está apagado para ese cliente: la pantalla le dice que generarlo encenderá Reservas y le propone cómo se reserva (por servicio y profesional, para una peluquería). Genera el borrador, lo prueba reservando en el probador y lo publica. La primera clienta que escribe por WhatsApp reserva sin que nadie haga nada más.

**Por qué esta prioridad**: es el fallo de Spa Jemma y el camino de todo cliente nuevo que da citas.

**Prueba independiente**: un cliente sin Reservas, un agente creado con «Gestiona citas» encendido: su versión 1 lleva las 9 herramientas, Reservas queda encendido y el probador reserva.

**Escenarios de aceptación**:

1. **Dado** un cliente con Reservas apagado, **cuando** el partner genera un agente con «Gestiona citas» encendido, **entonces** Reservas se enciende para el cliente antes de escribir el borrador, y la versión 1 lleva las 9 herramientas y procedimientos para reservar, mover y cancelar.
2. **Dado** el mismo cliente, **cuando** el partner apaga «Gestiona citas» antes de generar, **entonces** Reservas no se enciende y el agente no lleva la agenda.
3. **Dado** un cliente con Reservas ya encendido, **cuando** el partner genera con «Gestiona citas», **entonces** no se le pregunta cómo se reserva y el agente lleva la agenda.
4. **Dado** que encender Reservas falla, **cuando** el partner genera, **entonces** la pantalla lo dice y no se crea ningún agente a medias.

---

### Historia 2 — El aviso «No tenemos herramienta para» dice la verdad (Prioridad: P1)

El partner abre un agente que ya tiene la agenda. La pantalla no le dice que le falta lo que tiene. Si de verdad le falta, el aviso, además de «Quitar la promesa», le ofrece «Gestionar citas».

**Por qué esta prioridad**: un aviso falso hace que el partner desconfíe de todo lo demás y busque un fallo donde no lo hay, como pasó con Spa Jemma.

**Prueba independiente**: un agente que el constructor creó sin agenda y que la ganó después: el aviso no la nombra, y la revisión de publicar dice lo mismo que el aviso.

**Escenarios de aceptación**:

1. **Dado** un agente cuyo constructor anotó «reservar citas» como lo que faltaba, **cuando** ya lleva `reservas.create`, **entonces** el aviso no lo nombra, ni en el borrador ni en la versión publicada.
2. **Dado** un agente sin agenda cuyo texto promete citas, **cuando** se abre, **entonces** el aviso nombra la promesa y ofrece «Gestionar citas» y «Quitar la promesa».

---

### Historia 3 — Encender o apagar la agenda en un agente ya creado (Prioridad: P2)

En la pestaña Conectores del agente, «Agenda (Reservas)» aparece como una fila más, la primera. El partner la activa: el borrador gana las 9 herramientas y el constructor le propone cómo cambiar los procedimientos de citas. El partner revisa la propuesta, la acepta y publica. Si más adelante la desactiva, el borrador pierde la agenda, Reservas sigue encendido para el cliente y las citas ya dadas siguen ahí.

**Por qué esta prioridad**: es el camino de los agentes que ya existen y del que cambia de idea; sin él, el alta resuelve el caso nuevo pero no el de siempre.

**Prueba independiente**: un agente sin agenda; al activarla, su borrador lleva las 9 y una propuesta de texto pendiente; al aceptarla y publicar, reserva.

**Escenarios de aceptación**:

1. **Dado** un agente sin agenda y Reservas encendido, **cuando** el partner activa «Agenda (Reservas)», **entonces** su borrador gana las 9 herramientas y aparece la propuesta de texto.
2. **Dado** Reservas apagado, **cuando** el partner la activa, **entonces** una confirmación dice que se encenderá Reservas para todo el cliente y, al aceptar, se enciende.
3. **Dado** un agente con agenda, **cuando** el partner la desactiva, **entonces** el borrador pierde las 9, Reservas sigue encendido y se le propone quitar las promesas de citas.
4. **Dado** un agente con agenda, **cuando** el partner abre «Qué puede hacer» de la agenda, **entonces** ve las 9 y puede apagar una sola (la lista de espera, por ejemplo), salvo las que usa un procedimiento.

---

### Historia 4 — Reservas aún no está listo (Prioridad: P2)

El partner crea el agente antes de que el cliente haya dado de alta a sus profesionales. Puede publicar: la revisión le avisa de lo que falta y de dónde completarlo. Mientras falte, si alguien pide una cita, el agente toma el servicio y el día y la hora que prefiere y pasa la conversación a una persona, diciendo que el equipo se la confirmará. Cuando el cliente completa Reservas, el agente empieza a reservar en el siguiente mensaje, sin publicar de nuevo.

**Por qué esta prioridad**: decisión de Luis del 2026-11-09. Bloquear la publicación deja al cliente sin agente para todo lo demás. Y decir «no hay huecos» cuando lo que falta es configurar es mentir.

**Prueba independiente**: un cliente con Reservas encendido y sin profesionales; el agente publicado pasa la petición de cita a una persona; al añadir un profesional, reserva.

**Escenarios de aceptación**:

1. **Dado** Reservas sin profesionales, **cuando** el partner publica un agente con agenda, **entonces** se publica y la revisión avisa (sin bloquear) de qué falta, con un enlace a dónde completarlo.
2. **Dado** ese agente publicado, **cuando** una clienta pide una cita, **entonces** el agente pide el servicio, el día y la hora, pasa a una persona y no dice que no hay huecos.
3. **Dado** que el cliente añade un profesional, **cuando** la clienta vuelve a escribir, **entonces** el agente busca huecos y reserva.

---

### Historia 5 — Encender Reservas desde Acceso solo toca a quien da citas (Prioridad: P3)

El owner del partner enciende Reservas para un cliente que ya tiene tres agentes: recepción, cobros y soporte. Solo el de recepción, que promete citas, gana la agenda en un borrador. La lista de agentes y la ficha de ese agente dicen, a la vista, «Tiene la agenda preparada: publica para que reserve». Cobros y soporte no cambian.

**Por qué esta prioridad**: hoy los tres ganarían la agenda, en borradores que nadie ve. Con el interruptor por agente, encender el módulo deja de ser la vía principal.

**Prueba independiente**: tres agentes, uno que promete citas; al encender Reservas, solo ese tiene borrador nuevo, y su aviso se ve en la lista.

**Escenarios de aceptación**:

1. **Dado** un agente que promete citas y otro que no, **cuando** se enciende Reservas en Acceso, **entonces** solo el primero gana la agenda en su borrador, sin publicarse.
2. **Dado** ese borrador, **cuando** el partner abre la lista de agentes, **entonces** ve el aviso de publicar en la fila de ese agente.
3. **Dado** un agente que reserva en Calendly, **cuando** se enciende Reservas, **entonces** gana la agenda igual (da citas).

---

### Casos límite

- **Dos agentes creados a la vez** que encienden Reservas: el módulo se enciende una vez, y los dos llevan la agenda.
- **Reservas ya encendido en modo aforo** y un agente que pide la agenda: no se cambia el modo desde el agente; el agente usa el modo del cliente.
- **Una plantilla** con herramientas de Reservas: el interruptor viene encendido; si el partner lo apaga, el agente sale sin ellas.
- **El tope de herramientas** (60 por agente): si añadir la agenda lo pasa, se rechaza con el número y se dice qué quitar. No se añade a medias.
- **Un agente de instrucciones libres** (los de antes de la 047, como Ana de Jemma's Hair): el interruptor cambia sus herramientas igual; no hay propuesta de texto (no tiene procedimientos), y el aviso de promesas sigue avisando.
- **Un agente que reserva en Calendly o Google**: activar la agenda sustituye esas herramientas por las de Reservas, como manda la 043 (R11).
- **Apagar Reservas en Acceso** con agentes que tienen la agenda: sigue como hoy (se publica al momento una versión sin ella). Su fila de agenda dice «Reservas está apagado» y activarla lo vuelve a encender.
- **Una persona del partner sin permiso de editar agentes** (analista o facturación): ve el interruptor sin poder cambiarlo, como el resto de la pestaña.
- **Lo que no está disponible** (constitución §V): si Reservas no se ofrece a ese cliente, la fila «Agenda (Reservas)» y el interruptor del alta no aparecen; no hay botón apagado.

## Requisitos *(obligatorio)*

### Requisito 1 — «Gestiona citas» en «Nuevo agente»

**Historia de usuario:** Como partner, quiero decir al crear un agente si da citas, para que salga con la agenda desde su primera versión, sin tener que ir a Acceso ni volver a publicarlo.

#### Criterios de aceptación

1. WHERE Reservas se ofrece al cliente, «Nuevo agente» DEBE mostrar el interruptor «Gestiona citas» en las tres formas de empezar (describir, plantilla y en blanco), con una línea de lo que hace: dar, mover y cancelar citas en la agenda de Reservas.
2. WHEN la descripción pide citas, reservas o turnos, o la plantilla elegida lleva herramientas de Reservas, y nadie ha tocado el interruptor THEN el sistema DEBE encenderlo y decir por qué. La persona DEBE poder apagarlo.
3. WHILE el interruptor está encendido y Reservas está apagado para el cliente, la pantalla DEBE decir que generar encenderá Reservas para ese cliente y DEBE pedir cómo se reserva (por servicio y profesional, o por aforo), con la opción que corresponde al sector del cliente ya elegida.
4. WHEN se genera con el interruptor encendido y Reservas apagado THEN el sistema DEBE encender Reservas para el cliente con ese modo **antes** de escribir el borrador, de modo que el constructor vea la agenda.
5. IF encender Reservas falla THEN el sistema DEBE decirlo con su motivo y NO DEBE crear el agente ni el borrador.
6. WHEN se genera con el interruptor encendido THEN la versión 1 DEBE llevar las 9 herramientas de Reservas y procedimientos para reservar, mover y cancelar, y NO DEBE llevar la alternativa de pasar la cita al equipo para que la confirme.
7. WHEN se genera con el interruptor apagado THEN el agente NO DEBE llevar ninguna herramienta de Reservas, aunque Reservas esté encendido para el cliente.
8. Encender Reservas desde el alta NO DEBE dar acceso a las personas del cliente ni cambiar sus otros módulos, y DEBE tener sobre los demás agentes del cliente el mismo efecto que encenderlo desde Acceso (requisito 5).

### Requisito 2 — «Agenda (Reservas)» en la pestaña Conectores

**Historia de usuario:** Como partner, quiero encender o apagar la agenda de un agente ya creado como enciendo un conector, para cambiar lo que hace sin rehacerlo.

#### Criterios de aceptación

1. WHERE Reservas se ofrece al cliente, la pestaña Conectores del agente DEBE enseñar «Agenda (Reservas)» como la primera fila, con su estado en ese agente (activa o no) y, si Reservas está apagado para el cliente, diciéndolo.
2. WHEN alguien la activa THEN el borrador del agente DEBE ganar las 9 herramientas de Reservas de una vez, por la misma ruta y con la misma validación que cualquier otro cambio de herramientas, y la pantalla DEBE decir que rige al publicar.
3. WHEN alguien la activa y Reservas está apagado para el cliente THEN el sistema DEBE pedir confirmación diciendo que Reservas se encenderá para todo el cliente y cómo se reservará (requisito 1.3), y solo al confirmar DEBE encenderlo y añadir la agenda.
4. «Qué puede hacer» de la agenda DEBE listar las 9 herramientas, separando las que consultan de las que cambian algo, y DEBE dejar apagar una sola, salvo las que usa un procedimiento del agente, como pide la 047 (67.1 a 67.3).
5. WHEN alguien la desactiva THEN el borrador DEBE perder las 9 herramientas, y el sistema NO DEBE apagar Reservas para el cliente ni tocar sus reservas. La pantalla DEBE decir que las citas ya dadas siguen en Reservas.
6. IF añadir la agenda pasa del máximo de herramientas de un agente THEN el sistema DEBE rechazarlo diciendo el máximo y NO DEBE añadir solo una parte.
7. WHERE el agente es de instrucciones libres, activar y desactivar DEBEN cambiar sus herramientas igual, sin propuesta de texto (requisito 3).

### Requisito 3 — El texto sigue a la agenda: propuesta del constructor

**Historia de usuario:** Como partner, quiero que al cambiar la agenda de un agente el constructor me proponga cómo queda su texto de citas, para no publicar un agente que tiene la agenda y sigue diciendo «paso tu cita al equipo».

#### Criterios de aceptación

1. WHEN se activa la agenda en un agente estructurado ya creado THEN el constructor DEBE proponer reescrito, con las herramientas que el agente tiene ahora, todo lo que habla de citas: procedimientos, reglas, disparadores de escalado, habilidades con su alternativa y lo que solo sabe el agente. Y DEBE quitar todo lo que pasa la cita al equipo para que la confirme o dice que la agenda no está activa. (Spa Jemma, 2026-11-09: con las 9 herramientas ya publicadas, el agente seguía sin reservar porque un procedimiento decía «no ofrezcas huecos ni confirmes la reserva», un disparador de escalado decía «cuando solicitan crear, cambiar o cancelar una cita, porque la agenda no está activa», dos reglas decían que el equipo confirma, y dos habilidades —que la consola no deja editar— tenían por alternativa pasar al equipo.)
2. WHEN se desactiva THEN el constructor DEBE proponer quitar los procedimientos y las promesas de citas y dejar la alternativa de pasar a una persona.
3. La propuesta DEBE verse por bloque, con lo de antes y lo de después, y la persona DEBE poder aceptarla, editarla o descartarla. «Editar» la aplica al borrador y abre el primer bloque cambiado para ajustarlo antes de publicar. NO DEBE aplicarse sola.
4. La propuesta DEBE usar solo herramientas del agente y datos de la ficha del cliente, como pide la 047 (requisito 65).
5. IF la propuesta falla o tarda más que «Generar borrador» THEN el cambio de herramientas DEBE quedar hecho igual, la pantalla DEBE decir que el texto no se pudo proponer y ofrecer reintentarlo, y el aviso de promesas (requisito 6) DEBE seguir diciendo lo que no cuadra.
6. La llamada del constructor DEBE contar como construcción en el medidor, igual que «Generar borrador».
7. IF la ficha del negocio dice que el equipo confirma las citas (por ejemplo, en su política de cancelación) THEN la propuesta DEBE señalarlo con un enlace a Negocio, sin cambiar la ficha: la ficha es de todos los agentes del cliente.
8. WHILE un agente lleva la agenda y su texto dice que no la tiene, que el equipo confirma las citas o que se pasa la cita a una persona, la revisión de publicar DEBE avisar de la contradicción, con el puntero a cada texto. Es el caso inverso de «promete sin herramienta»: tiene la herramienta y su texto la prohíbe.

### Requisito 4 — Reservas aún no está listo: se publica con aviso y el agente pasa las citas

**Historia de usuario:** Como partner, quiero publicar el agente aunque al cliente le falte configurar Reservas, para que atienda todo lo demás, sin que diga a nadie que no hay huecos.

#### Criterios de aceptación

1. WHEN se publica un agente con agenda y al cliente le falta algo para poder tomar una cita (horario, profesionales, servicios reservables o capacidad) THEN la publicación NO DEBE bloquearse por ello, y la revisión DEBE avisar de qué falta, con un enlace a dónde completarlo.
2. WHILE al cliente le falta algo para poder tomar una cita, cuando alguien pide una cita, el agente DEBE pedir el servicio, el día y la hora que prefiere, pasar la conversación a una persona y decir que el equipo se la confirmará. NO DEBE decir que no hay huecos, ni dar una cita por hecha.
3. WHEN al cliente ya no le falta nada THEN el agente DEBE buscar huecos y reservar desde el mensaje siguiente, sin publicar de nuevo.
4. WHILE falte algo, la ficha del agente y su fila de agenda en Conectores DEBEN decir «La agenda aún no está lista» y qué falta.
5. Un servicio concreto sin profesional que lo haga DEBE seguir como manda la 043 (requisito 14): este requisito trata lo que le falta a Reservas entero, no a un servicio.

### Requisito 5 — Encender Reservas solo toca a los agentes que dan citas

**Historia de usuario:** Como partner, quiero que encender Reservas para un cliente prepare la agenda solo a los agentes que dan citas, y que lo vea, para publicarlos sin buscar qué cambió.

#### Criterios de aceptación

1. WHEN se enciende Reservas para un cliente (desde Acceso o desde un agente) THEN solo los agentes activos que dan citas DEBEN ganar la agenda en su borrador, sin publicarse: los que reservan en un conector y los que prometen citas en su texto. Los demás NO DEBEN cambiar.
2. El agente desde el que se encendió NO DEBE recibir además un borrador de este requisito: su cambio es el del requisito 1 o 2.
3. WHILE un agente tiene la agenda preparada en un borrador sin publicar, la lista de agentes y su ficha DEBEN decirlo a la vista, con la acción de revisar y publicar, y DEBEN llevar a la propuesta de texto del requisito 3.
4. IF alguien descarta ese borrador THEN NO DEBE volver mientras siga la misma versión activa, como manda la 043 (11.5).

### Requisito 6 — El aviso «No tenemos herramienta para» se recalcula

**Historia de usuario:** Como partner, quiero que el aviso de lo que le falta a un agente diga lo que le falta ahora, para fiarme de él.

#### Criterios de aceptación

1. El aviso DEBE calcularse con lo que la versión tiene en el momento de leerla: WHEN lo que el constructor anotó como falta ya lo hace una herramienta del agente, o el módulo que faltaba ya está encendido, THEN NO DEBE aparecer, ni en el borrador ni en la versión publicada.
2. El aviso y la revisión de publicar DEBEN decir lo mismo sobre las promesas sin herramienta.
3. WHEN el aviso nombra reservar, mover o cancelar citas y Reservas se ofrece al cliente THEN DEBE ofrecer «Gestionar citas», que hace lo del requisito 2, además de «Quitar la promesa».
4. Los agentes que ya existen con una nota desactualizada DEBEN verse bien sin migración a mano.

### Requisito 7 — Quién puede, y queda dicho

**Historia de usuario:** Como owner del partner, quiero que quien edita agentes pueda encender Reservas al crearlos, y que apagarlo siga siendo cosa mía, para no frenar el trabajo sin perder el control.

#### Criterios de aceptación

1. Encender Reservas desde el alta o desde Conectores DEBE requerir el permiso de editar agentes (owner, admin y builder) del partner dueño del cliente.
2. IF el cliente de la ruta no es del partner de la persona THEN el sistema DEBE responder como si no existiera y NO DEBE encender nada.
3. El cliente sobre el que se enciende Reservas DEBE salir de la ruta y de la sesión. NO DEBE aceptarse un cliente en el cuerpo de la petición.
4. Apagar Reservas para el cliente NO DEBE poder hacerse desde un agente: solo desde Acceso, con el permiso que ya tiene (owner y admin).
5. Cada encendido DEBE quedar en la auditoría del cliente con la persona, el agente desde el que se hizo y el modo elegido.
6. La lista de herramientas de un agente DEBE llevar las de Reservas solo si su agenda está activa (garantía 2). Encender Reservas para el cliente NO DEBE dárselas a un agente que no da citas.

### Entidades clave

- **La agenda de un agente**: si un agente lleva las herramientas de Reservas. No es una fila nueva: es lo que dice la lista de herramientas de su versión, del cliente del agente y alcanzada por la RLS de ese cliente (`tenant_id`).
- **Reservas del cliente**: el módulo y su modo (por servicio o por aforo), del cliente, por `tenant_id`. Ya existe; este cambio solo añade otra forma de encenderlo.
- **La propuesta de texto**: los bloques reescritos que el constructor propone a un borrador del agente, pendientes de aceptar. Del cliente del agente, por `tenant_id`.
- **La nota del constructor**: lo que el constructor dejó fuera al escribir el agente. Ya existe; deja de mostrarse tal cual y se contrasta con lo que el agente tiene.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un agente creado con «Gestiona citas» toma una cita real en su primera conversación tras publicarse, sin ningún paso después de crearlo (cero borradores intermedios y cero visitas a Acceso).
- **CE-002**: crear un agente que da citas para un cliente nuevo pasa de tres pantallas y dos publicaciones (Acceso, agente, volver a publicar) a una pantalla y una publicación.
- **CE-003**: cero avisos «No tenemos herramienta para» sobre algo que el agente sí puede hacer, en un barrido de todos los agentes de staging.
- **CE-004**: mientras Reservas no está listo, ninguna respuesta dice que no hay huecos por falta de configuración, y toda petición de cita pasa a una persona.
- **CE-005**: encender Reservas desde Acceso no cambia ningún agente que no dé citas.

## Fuera de alcance

- **La cola sin cita** (`queue.*`, 5 herramientas) como interruptor — es otro módulo; va en otra spec si se pide.
- **Apagar Reservas desde un agente** — decisión de Luis: apagar sigue en Acceso.
- **Elegir herramientas sueltas en el alta** — el alta tiene un interruptor; las sueltas se eligen en Conectores.
- **Cambiar el modo de Reservas desde un agente** cuando ya está encendido — es del cliente, no del agente; sigue en Acceso.
- **El paso automático del despliegue** (043, 11.4) — no cambia: sigue sin tocar al agente cuyo cliente no puede reservar.
- **La app móvil y la consola lite** — no crean agentes.

## Supuestos

- Reservas da 9 herramientas: ver qué se puede reservar, buscar huecos, reservar, consultar las reservas de quien escribe, mover, cancelar, confirmar la asistencia, apuntar en la lista de espera y responder a un hueco ofrecido.
- «Dar citas», para el requisito 5, es lo que ya calcula la plataforma: reservar en un conector, o prometer citas en el texto con las mismas palabras que detecta el aviso de promesas.
- El modo propuesto sale del sector del cliente, que ya está identificado en su ficha (047, requisito 57). Sin sector, se propone por servicio y profesional.
- Spa Jemma no necesita nada a mano: su versión activa ya lleva la agenda, y su aviso desactualizado desaparece con el requisito 6.
