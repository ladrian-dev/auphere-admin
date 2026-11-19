# Especificación: Reservas a tiempo y conversaciones con principio y fin

**Rama**: `064-reservas-y-ciclo-de-conversacion` · **Creada**: 2026-11-18 · **Estado**: Aclarada con Luis el 2026-11-18, lista para planificar

**Entrada**: descripción del usuario: "Reservas y Bandeja: correcciones pedidas por los partners (2026-11-18). Cuatro historias. (1) Antelación mínima del agente configurable: hoy el agente no ofrece ni reserva nada antes de ahora + 60 min y ninguna pantalla deja cambiarlo. (2) Teléfono obligatorio y validado al crear una reserva a mano desde la app y desde la consola. La llegada sin reserva queda exenta. (3) «Atendida»: el cierre automático a la hora de fin ya existe. Falta que la consola relea sola el estado y que el negocio pueda marcar «No vino» (y deshacerlo) después del cierre automático. (4) Ciclo de vida de la conversación, opcional y de menor prioridad: resolver marca un corte en el contexto del agente, y hay un cierre por inactividad configurable por cliente. «Limpio» conserva lo mínimo. Fuera de alcance: histórico de citas por cliente y avisos de retoque tras la cita."

> La aclaración del 2026-11-18 recortó esa entrada en dos puntos: la antelación
> por defecto no cambia, y la app móvil queda fuera. Ver Clarifications.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API de la consola, las herramientas `reservas.*` del agente y el runtime del turno, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **8 (cliente final dentro del tenant), rozada por los requisitos 3 y 4.** El teléfono obligatorio hace que toda reserva hecha a mano en la consola quede enlazada a un contacto del negocio, que luego la ve con `reservas.list_mine` y recibe sus avisos: un número mal escrito enlaza la cita a otra persona (requisito 3.6). El corte del contexto solo quita mensajes del propio contacto, nunca añade los de otro (requisito 4.7). **1 (RLS), rozada por los requisitos 1 y 5:** los dos ajustes son del cliente y se leen y escriben bajo su `tenant_id`. Ninguna otra: no se mueven datos entre negocios. |
| **Nota de KB que la justifica** | `[[research/2026-11-18-reservas-y-ciclo-de-conversacion]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada nuevo.** No hay llamadas nuevas al modelo. El corte del contexto quita mensajes de cada turno, así que gasta lo mismo o menos, y se sigue midiendo en la bolsa del cliente. Releer la agenda sola son lecturas de la API, que no se miden. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 043, clarificación «¿Antelación para reservar?» y **R2** (ajustes del negocio) | El agente reserva con al menos 60 min de antelación. Es un ajuste, pero ninguna pantalla lo enseña ni lo cambia. | El negocio lo ve y lo cambia en los Ajustes de la consola. El valor por defecto sigue en 60 minutos (requisito 1). |
| Spec 043, **R6** (herramientas del agente) | `reservas.find_slots` devuelve las horas que el agente puede dar y nada más. | También dice cuándo hay horas libres más cercanas que el agente no puede dar (requisito 1.5). |
| Spec 043, clarificación «¿Cliente final sin teléfono?» y **R5.2** (crear una reserva) | La reserva lleva nombre y, si hay, teléfono. | Una reserva hecha a mano desde la consola lleva nombre y teléfono. La llegada sin reserva sigue sin pedirlo, y la app móvil sigue como está hasta que se ponga al día (requisito 3). |
| Spec 043, **R5.4** y clarificación «¿`done` se guarda o se calcula?» | «No vino» y «Deshacer» solo valen el mismo día y mientras la reserva sigue abierta. Lo que el sistema cierra como «Atendida» ya no se toca. | En Servicios, el negocio puede corregir una «Atendida» a «No vino», y al revés, durante los 7 días siguientes (requisito 2). |
| Spec 043, **R8** (pantallas de Reservas en la consola) | No dice cuándo se relee. Hoy la pantalla lee al entrar y tras cada acción. | Relee sola mientras está abierta (requisito 2.6). |
| Spec 030, **R12.2** (el contacto escribe en una conversación resuelta) | Se reabre y responde el agente, que lee el hilo anterior. | Se reabre y responde el agente, que empieza sin lo anterior (requisito 4). |
| Spec 030, **R12** (resolver, reabrir) | Solo una persona resuelve una conversación. | Además, el cliente puede hacer que se resuelvan solas tras un tiempo sin mensajes (requisito 5). |

La spec 044 (la app con Reservas) no se enmienda: la app móvil queda fuera.

## Por qué

El 2026-11-18 Luis trajo cuatro recomendaciones de partners: tres «importante corregir» y una «ideal». Se revisó cada una contra el código y contra los registros del planificador. `main` y `develop` son iguales en Reservas, así que lo que sigue vale para producción y para staging.

1. **«Permitir reservas en el próximo horario disponible. Hoy es una hora después.»** Es cierto, y es una decisión de la 043: el agente no ofrece ni reserva nada que empiece antes de ahora más 60 minutos. Solo afecta al agente: desde la consola y la app, el negocio reserva cualquier hora futura. El valor ya es un ajuste del cliente, pero ninguna pantalla lo enseña ni lo cambia. Además, el agente no sabe que se quitaron horas por la antelación y contesta «no hay disponibilidad antes de…», aunque la agenda del negocio enseñe esas horas libres.
2. **«"Atendida" se marca automático, a la hora de fin exacta.»** Ya ocurre. Un proceso pasa cada minuto y cierra como «Atendida» toda cita de Servicios cuya hora de fin pasó. En staging, entre el 9 y el 16 de noviembre, cerró cada cita en menos de un minuto desde su fin. Lo que falla es otra cosa:
   - **La consola no relee sola.** Quien tiene la agenda abierta sigue viendo «Confirmada» hasta recargar o hacer una acción.
   - **No se puede corregir.** «No vino» solo se ofrece mientras la cita sigue abierta. Si nadie lo marcó antes de la hora de fin, quien no vino cuenta como atendido para siempre.
3. **«Número obligatorio en la reserva desde la app.»** Hoy el teléfono es opcional en la app, en la consola y en la API. Sin teléfono no sale la confirmación ni el recordatorio, y la reserva no queda enlazada a ningún contacto.
4. **«Ideal: el ciclo de vida del mensaje, con valor por configuración.»** Resolver una conversación existe y es manual. No hay cierre por inactividad. Y el contexto no se limpia: en cada turno el agente lee los últimos 20 mensajes del hilo, tengan la antigüedad que tengan y esté o no resuelta. Si alguien vuelve a escribir a los 7 días, el agente sigue leyendo la conversación anterior. Hoy solo «Vaciar el chat» y «Eliminar» lo cortan, los dos a mano.

## Clarifications

### Session 2026-11-18

Todas las respondió Luis. Las tres primeras, al pedir la spec. Las demás, en
la aclaración.

- Q: ¿Qué es «el ciclo de vida del mensaje»? → A: Que la conversación tenga un inicio y un fin: que se pueda marcar como resuelta y que, si la persona vuelve a escribir días después, el contexto sea nuevo y limpio. No es algo requerido: es lo «ideal» de la lista.
- Q: ¿«Limpio» es olvidarlo todo? → A: No: conserva lo mínimo.
- Q: ¿Entran el histórico de citas por cliente y los avisos de retoque? → A: No. El histórico «lo veremos luego», y los retoques son una función nueva. Lo que más importa de «Atendida» es poder marcar si el cliente vino o no.
- Q: ¿Qué antelación debe tener cada negocio al desplegar esta spec? → A: Se queda en 60 minutos. Solo se añade el control en Ajustes: el negocio que quiera la próxima hora libre elige «sin antelación». Nadie cambia de antelación sin tocarlo.
- Q: Cuando una conversación se marca como resuelta y el contacto vuelve a escribir, ¿el agente empieza siempre sin los mensajes anteriores? → A: Sí, siempre, la resuelva una persona o el cierre por inactividad. Si una persona la reabre a mano, el agente recupera el contexto.
- Q: ¿Entra la app móvil? → A: No. Solo la web ahora: la app queda para su sesión aparte. El teléfono obligatorio se exige en el formulario de la consola, y el servidor sigue aceptando lo que la app envía hoy.
- Q: ¿Se dan por buenas las demás decisiones? → A: Sí, todas:
  - la antelación se elige entre sin antelación, 15 min, 30 min, 1 h, 2 h, 4 h y 24 h;
  - el teléfono es obligatorio en la consola, y la llegada sin reserva queda exenta;
  - «No vino» se puede corregir hasta 7 días después de la cita, y solo en Servicios;
  - «lo mínimo» que conserva el agente es el nombre del contacto y que ya es un contacto del negocio;
  - el cierre por inactividad viene apagado, con plazos de 24 horas, 3 días, 7 días y 30 días.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El negocio decide con cuánta antelación da citas el agente (Prioridad: P1)

El dueño de una barbería quiere que su agente dé la próxima hora libre. Abre Reservas → Ajustes en la consola, ve «Antelación mínima del agente: 1 hora» y la cambia a «sin antelación». A las 13:09 una clienta escribe al WhatsApp: quiere un corte cuanto antes. La agenda tiene libres las 13:30 y las 14:00, y el agente le ofrece las 13:30.

Otro negocio no toca nada y sigue con su hora de antelación. Cuando le piden una cita para dentro de media hora y hay hueco, el agente ya no dice que no hay disponibilidad: dice que para esa hora tiene que confirmarlo el negocio, y le pasa la conversación a una persona si la clienta quiere.

**Por qué esta prioridad**: hoy el agente niega horas que el negocio ve libres, y nadie puede cambiarlo desde ninguna pantalla.

**Prueba independiente**: con «sin antelación», a las 13:09 y las 13:30 libres, el agente ofrece las 13:30. Con 1 hora, no la ofrece y dice que el negocio puede darla.

**Escenarios de aceptación**:

1. **Dado** un negocio que eligió «sin antelación», **cuando** el agente busca huecos a las 13:09 y las 13:30 están libres, **entonces** ofrece las 13:30.
2. **Dado** un negocio que nunca abrió Ajustes, **cuando** se despliega el cambio, **entonces** sigue con 60 minutos de antelación.
3. **Dado** un negocio con antelación, **cuando** piden una hora libre dentro de ella, **entonces** el agente dice que esa hora la da el negocio y ofrece pasar la conversación, y no dice que no hay disponibilidad.
4. **Dado** los Ajustes de Reservas, **cuando** el negocio cambia la antelación, **entonces** el agente la aplica en la siguiente búsqueda.
5. **Dado** un negocio con antelación, **cuando** una persona del negocio reserva desde la consola o la app, **entonces** puede elegir cualquier hora futura, como hoy.

---

### Historia 2 — Marcar si el cliente vino o no (Prioridad: P1)

Un cliente tenía cita a las 16:00 y no apareció. Nadie lo marcó a tiempo, y a las 16:30 el sistema cerró la cita como «Atendida». Al día siguiente la dueña abre la cita en la consola y marca «No vino». La cita deja de contar como atendida y cuenta como no-show. Si se equivoca de cita, la devuelve a «Atendida». Mientras tanto, quien tiene la agenda abierta en el mostrador ve cómo las citas pasan a «Atendida» a su hora, sin recargar la página.

**Por qué esta prioridad**: es lo que Luis señaló como más importante. Sin la corrección, las cifras de atendidos y de no-show no son de fiar.

**Prueba independiente**: una cita cerrada sola como «Atendida» se marca «No vino» al día siguiente y cambia la cifra del mes. Con la agenda abierta y sin tocarla, una cita que termina se ve «Atendida».

**Escenarios de aceptación**:

1. **Dado** una cita que el sistema cerró como «Atendida», **cuando** el negocio la abre dentro de los 7 días siguientes, **entonces** puede marcar «No vino».
2. **Dado** una cita marcada «No vino» después de su hora de fin, **cuando** el negocio pulsa «Deshacer» dentro de esos 7 días, **entonces** vuelve a «Atendida».
3. **Dado** una corrección, **cuando** se abre el historial de la cita, **entonces** dice quién la hizo y cuándo.
4. **Dado** una cita de hace 8 días, **cuando** se abre, **entonces** no ofrece la corrección.
5. **Dado** la agenda abierta en la consola, **cuando** una cita termina y nadie toca la pantalla, **entonces** se ve «Atendida» en menos de 2 minutos.
6. **Dado** una cita corregida a «No vino», **cuando** se mira el resumen del mes, **entonces** cuenta como no-show y no como atendida.

---

### Historia 3 — Toda reserva hecha a mano en la consola lleva teléfono (Prioridad: P2)

Alguien llama al negocio para pedir cita. La persona que atiende abre «Nueva reserva» en la consola, elige servicio y hora, y escribe el nombre y el teléfono. Sin teléfono no puede guardar, y la pantalla dice por qué: sin él no hay confirmación ni recordatorio. Si el número está mal escrito, lo dice antes de guardar. Cuando entra alguien por la puerta sin reserva, la llegada sin reserva se apunta como siempre, sin pedir teléfono.

**Por qué esta prioridad**: sin teléfono, la reserva no recibe ningún aviso. Va después de las dos primeras porque el negocio ya puede escribir el teléfono hoy.

**Prueba independiente**: en la consola, «Guardar» no se activa sin un teléfono válido. La llegada sin reserva se guarda sin él.

**Escenarios de aceptación**:

1. **Dado** «Nueva reserva» en la consola, **cuando** falta el teléfono, **entonces** no se puede guardar y la pantalla dice que hace falta para avisar al cliente.
2. **Dado** un teléfono sin prefijo de país o con letras, **cuando** se intenta guardar, **entonces** la pantalla dice que no es válido y no guarda.
3. **Dado** una llegada sin reserva en Aforo, **cuando** se apunta, **entonces** no pide teléfono.
4. **Dado** una reserva antigua sin teléfono, **cuando** el negocio la mueve o la cancela, **entonces** puede hacerlo sin añadirlo.
5. **Dado** la app móvil de hoy, **cuando** guarda una reserva sin teléfono, **entonces** se guarda como hasta ahora.

---

### Historia 4 — Una conversación resuelta empieza de cero (Prioridad: P3)

Una clienta pregunta un lunes por los precios de un tratamiento, el agente le contesta y la dueña marca la conversación como resuelta. El lunes siguiente la clienta escribe «hola, quería pedir hora». El agente la saluda por su nombre y atiende lo que pide ahora, sin arrastrar la conversación de la semana anterior. En la Bandeja, la dueña sigue viendo el hilo entero, con la marca de cuándo se resolvió y cuándo se reabrió.

Otro negocio no quiere resolver a mano. En los ajustes de la Bandeja elige «Cerrar las conversaciones tras 7 días sin mensajes». A partir de ahí, las conversaciones que lleva el agente se resuelven solas a los 7 días de silencio, y la siguiente empieza limpia.

**Por qué esta prioridad**: es la recomendación «ideal», no un fallo.

**Prueba independiente**: se resuelve una conversación, el contacto escribe de nuevo y la respuesta del agente no usa nada de lo anterior. Con el cierre a 24 horas, una conversación sin mensajes aparece resuelta pasado ese plazo.

**Escenarios de aceptación**:

1. **Dado** una conversación resuelta, **cuando** el contacto vuelve a escribir, **entonces** el agente responde sin los mensajes anteriores a la resolución y se dirige al contacto por su nombre.
2. **Dado** esa misma conversación, **cuando** una persona la abre en la Bandeja, **entonces** ve el hilo entero, con lo anterior y lo nuevo.
3. **Dado** una conversación que una persona resolvió por error, **cuando** la reabre a mano, **entonces** el agente vuelve a tener el contexto de antes.
4. **Dado** un cliente con el cierre a 7 días, **cuando** una conversación que lleva el agente pasa 7 días sin mensajes, **entonces** queda resuelta, y el hilo dice que se cerró por inactividad.
5. **Dado** una conversación que espera a una persona o que lleva una persona, **cuando** pasa el plazo, **entonces** no se cierra sola.
6. **Dado** un cliente que no tocó el ajuste, **cuando** pasa el tiempo, **entonces** ninguna conversación se cierra sola.
7. **Dado** una petición de confirmación de cita enviada ayer y aún sin respuesta, **cuando** la conversación se cierra por inactividad y el contacto contesta «sí, voy», **entonces** el agente sabe a qué contesta.

---

### Casos límite

- **La rejilla sigue redondeando.** Sin antelación, a las 13:09 y con pasos de 30 minutos, la próxima hora es 13:30, no 13:10. Esta spec no cambia el paso.
- **Una hora que ya empezó.** Nunca se ofrece, con o sin antelación (043, R4.1).
- **«Antelación» ya nombra otra cosa en Ajustes.** «Antelación mínima para avisar» es la de la lista de espera. El control nuevo se llama distinto y dice a quién afecta: al agente (requisito 1.3).
- **El agente mueve una cita.** La antelación vale igual que al reservar.
- **Corregir una «Atendida» no escribe al cliente.** Es una anotación del negocio. No sale ningún mensaje.
- **Una reserva de Aforo cerrada como «Vino».** No se corrige a «No vino»: solo se cierra así si alguien marcó antes «Llegó», o si nació como llegada sin reserva. La persona estuvo allí.
- **Dos personas corrigen la misma cita a la vez.** La segunda recibe el aviso de que la cita cambió, como en cualquier otra acción (043, R5.8).
- **La pestaña de la consola está oculta.** No relee mientras nadie la mira. Al volver a ella, relee en el momento.
- **Hay un diálogo abierto con algo escrito.** Releer la agenda no lo cierra ni borra lo escrito.
- **La consola no puede releer** (sin red, API caída). Deja lo que tenía y dice que puede estar desactualizado. No lo pinta como al día.
- **La app móvil de hoy.** Sigue funcionando sin cambios: guarda reservas con o sin teléfono, y abre una reserva ya cerrada aunque la API ofrezca sobre ella una acción que la app no conoce (requisitos 2.12 y 3.5).
- **La lista de espera** sigue aceptando una entrada sin teléfono, como hoy. Ver Fuera de alcance.
- **Un teléfono válido pero de otra persona.** El sistema no puede saberlo. Por eso valida el formato, y la reserva guardada enseña su teléfono.
- **«Vaciar el chat» y «Eliminar»** siguen como están: quitan los mensajes también de la Bandeja. Resolver no quita nada de la Bandeja.
- **Un aviso del negocio reabre la conversación** (un recordatorio de cita, uno de cobranza). Ese aviso es el primer mensaje de la conversación nueva, y el agente lo tiene en cuenta cuando el contacto contesta.
- **La derivación a otro agente** ya se reinicia al resolver (047, R53). El cierre por inactividad es una resolución más y hace lo mismo.
- **Qué ve un cliente sin Reservas o sin Bandeja.** Nada nuevo: ni el control de la antelación ni el ajuste del cierre. No hay controles apagados.

## Requisitos *(obligatorio)*

### Requisito 1 — La antelación del agente la decide el negocio

**Historia de usuario:** Como negocio, quiero decidir con cuánta antelación mínima puede dar citas el agente, para que ofrezca la próxima hora libre o respete el margen que yo necesite.

#### Criterios de aceptación

1. El sistema DEBE enseñar en los Ajustes de Reservas de la consola la antelación mínima con la que el agente da citas, y DEBE dejar cambiarla a quien ya puede cambiar los ajustes de Reservas.
2. Los valores que se pueden elegir DEBEN ser: sin antelación, 15 min, 30 min, 1 h, 2 h, 4 h y 24 h. IF llega otro valor THEN el sistema DEBE rechazarlo diciendo el campo.
3. El control DEBE decir que afecta solo al agente, y NO DEBE confundirse con la antelación de la lista de espera, que conserva su nombre.
4. WHEN el agente busca huecos, reserva o mueve una cita THEN el sistema DEBE aplicar la antelación vigente en ese momento. Las reservas que hace una persona del negocio NO DEBEN quedar limitadas por ella.
5. WHEN el agente busca huecos y hay horas libres que solo quedan fuera por la antelación THEN la herramienta DEBE decírselo, distinguiéndolo de «no hay horas libres».
6. IF el cliente pide una hora que solo queda fuera por la antelación THEN el agente DEBE decir que esa hora la confirma el negocio y ofrecer pasar la conversación a una persona, y NO DEBE decir que no hay disponibilidad.
7. Un cliente que activa Reservas DEBE seguir empezando con 60 minutos de antelación (decisión de Luis, 2026-11-18).
8. WHEN se despliegue este cambio THEN ningún cliente DEBE cambiar de antelación sin que alguien la cambie en Ajustes.

### Requisito 2 — «Atendida» se ve sola y se puede corregir

**Historia de usuario:** Como negocio, quiero ver cuándo una cita pasa a «Atendida» y poder marcar que el cliente no vino aunque ya se haya cerrado, para que mis cifras digan la verdad.

#### Criterios de aceptación

1. WHEN una reserva de Servicios está «Atendida» y han pasado como mucho 7 días desde su hora de fin THEN el sistema DEBE ofrecer «No vino» en la consola.
2. WHEN el negocio marca «No vino» sobre una reserva ya cerrada THEN el sistema DEBE dejarla como no-show, y NO DEBE enviar ningún mensaje al cliente final.
3. WHEN el negocio deshace un «No vino» de una reserva cuya hora de fin ya pasó, dentro de esos 7 días, THEN el sistema DEBE dejarla «Atendida», y NO DEBE enseñarla como «Confirmada» en ningún momento.
4. Cada corrección DEBE quedar en el historial de la reserva con la persona que la hizo.
5. IF han pasado más de 7 días desde la hora de fin, o la reserva es de Aforo, THEN el sistema NO DEBE ofrecer la corrección, y DEBE rechazarla si llega.
6. WHILE la pantalla de Reservas está abierta y visible en la consola, el sistema DEBE releer el estado de las reservas sin que la persona recargue, de modo que un cambio hecho por el sistema o por otra persona se vea en menos de 2 minutos.
7. WHEN la pantalla vuelve a estar visible después de haber estado oculta THEN DEBE releer en ese momento.
8. Releer NO DEBE cerrar un diálogo abierto, borrar lo que la persona esté escribiendo ni mover la vista que tiene delante.
9. IF la relectura falla THEN la pantalla DEBE conservar lo que tenía y decir que puede estar desactualizado.
10. El resumen del mes DEBE contar una reserva corregida según su estado final.
11. El cierre automático a la hora de fin NO DEBE cambiar: Servicios, las abiertas cuya hora de fin pasó; Aforo, las que llegaron y cuya estancia terminó (043, R7).
12. La app móvil de hoy DEBE seguir abriendo y manejando cualquier reserva, también una cerrada sobre la que la API ofrece ahora la corrección.

### Requisito 3 — Toda reserva hecha a mano en la consola lleva teléfono

**Historia de usuario:** Como negocio, quiero que no se pueda guardar una reserva sin el teléfono del cliente, para que siempre haya a quién confirmar y recordar la cita.

#### Criterios de aceptación

1. WHEN una persona crea una reserva desde la consola THEN la consola DEBE exigir nombre y teléfono, en Servicios y en Aforo.
2. IF falta el teléfono, o no es un número internacional válido con su prefijo de país, THEN la consola NO DEBE guardar la reserva, y DEBE marcar el error en el campo con su motivo.
3. El formulario DEBE decir por qué se pide el teléfono: sin él no hay confirmación ni recordatorio.
4. La llegada sin reserva NO DEBE pedir teléfono. Las reservas que ya existen sin teléfono DEBEN poder seguir moviéndose, cancelándose y cerrándose sin añadirlo.
5. El sistema DEBE seguir aceptando las reservas que envía la app móvil de hoy, con o sin teléfono, hasta que la app se ponga al día (decisión de Luis, 2026-11-18).
6. Una prueba de aislamiento DEBE fijar que una reserva hecha a mano solo se enlaza al contacto del mismo negocio cuyo número coincide entero, y que ningún otro contacto la ve ni recibe sus avisos (garantía 8).

### Requisito 4 — Una conversación resuelta empieza de cero

**Historia de usuario:** Como negocio, quiero que una conversación resuelta sea un asunto cerrado, para que el agente atienda lo que el cliente pide ahora y no lo que habló hace días.

#### Criterios de aceptación

1. WHEN el contacto escribe en una conversación resuelta THEN el agente DEBE responder sin los mensajes anteriores a la resolución, y sin el recuerdo de las herramientas que usó en ellos.
2. Después del corte, el agente DEBE seguir sabiendo el nombre del contacto y que ya es un contacto del negocio. Lo que vive fuera del chat, como sus citas en Reservas, DEBE seguir consultándose con las herramientas de siempre.
3. La Bandeja DEBE seguir enseñando el hilo entero, con lo anterior a la resolución y las marcas de resuelta y reabierta. Resolver NO DEBE ocultar ni borrar ningún mensaje.
4. WHEN una persona reabre a mano una conversación resuelta THEN el agente DEBE recuperar el contexto anterior, como si no se hubiera resuelto.
5. WHEN un aviso que la plataforma envía por su cuenta (recordatorio, petición de confirmación, oferta de la lista de espera, cobranza) reabre una conversación resuelta THEN ese aviso DEBE formar parte del contexto de la conversación nueva.
6. IF la plataforma envió uno de esos avisos, el contacto aún no lo contestó y lo que pide sigue vigente THEN el aviso DEBE seguir en el contexto del agente aunque la conversación se resuelva después. Sigue vigente mientras la cita a la que se refiere no ha pasado, mientras la oferta no ha caducado o, en un aviso de cobranza, durante los 7 días siguientes a su envío.
7. Una prueba de aislamiento DEBE fijar que el contexto del agente, antes y después de un corte, solo lleva mensajes del contacto del turno (garantía 8).
8. Este requisito DEBE valer para toda conversación que se resuelva después del despliegue, la resuelva una persona o el cierre por inactividad (decisión de Luis, 2026-11-18). Las resueltas antes NO DEBEN cambiar hasta que se vuelvan a resolver.

### Requisito 5 — Cierre por inactividad, si el negocio lo quiere

**Historia de usuario:** Como negocio, quiero que las conversaciones sin actividad se den por terminadas solas, para no tener que resolverlas una a una.

#### Criterios de aceptación

1. El sistema DEBE ofrecer en los ajustes de la Bandeja del cliente, en la consola, «Cerrar las conversaciones sin mensajes», con estos valores: nunca, 24 horas, 3 días, 7 días y 30 días. Por defecto DEBE ser «nunca».
2. WHERE el cliente eligió un plazo, WHEN una conversación que responde el agente pasa ese plazo sin mensajes en ningún sentido THEN el sistema DEBE resolverla, y el hilo DEBE decir que se cerró por inactividad.
3. El sistema NO DEBE cerrar sola una conversación que espera a una persona ni una que lleva una persona.
4. Una conversación cerrada por inactividad DEBE comportarse como cualquier resuelta: sale de la lista por defecto, se reabre si el contacto escribe y empieza de cero (requisito 4).
5. El cierre por inactividad NO DEBE avisar a nadie ni contar como algo pendiente.
6. WHEN el cliente cambia el plazo THEN el plazo nuevo DEBE valer para las conversaciones abiertas, contando desde su último mensaje.
7. WHERE el cliente no tiene Bandeja, el sistema NO DEBE enseñar el ajuste.
8. El ajuste DEBE leerse y escribirse solo dentro del cliente al que pertenece, y una prueba de aislamiento DEBE fijarlo (garantía 1).

### Entidades clave

No hay entidades nuevas. Se tocan estas:

- **Ajustes de Reservas del cliente**: la antelación mínima del agente, que ya existe. Pertenece al tenant del cliente, y la RLS la alcanza por `tenant_id`.
- **Reserva**: su estado y su historial, con las correcciones. Pertenece al tenant del cliente.
- **Conversación**: desde qué momento cuenta para el agente, que deja de ser lo mismo que desde qué momento se ve en la Bandeja. Pertenece al tenant del cliente y a un solo contacto.
- **Ajuste de cierre por inactividad**: un valor por cliente. Pertenece al tenant del cliente, y la RLS lo alcanza por `tenant_id`.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Con un negocio que eligió «sin antelación», a las 13:09 y con las 13:30 libres, el agente ofrece las 13:30. Hoy ofrece como pronto las 14:30, y nadie puede cambiarlo.
- **CE-002**: Con un negocio con antelación y una hora libre dentro de ella, el agente no dice «no hay disponibilidad» en **ninguna** de 5 pruebas seguidas: dice que la da el negocio.
- **CE-003**: Un negocio cambia la antelación en **menos de 1 minuto** y sin ayuda de Auphere. Hoy no puede.
- **CE-004**: Una cita que nadie marcó se corrige a «No vino» al día siguiente en **2 pasos** desde la agenda, y la cifra de no-show del mes cambia. Hoy no se puede.
- **CE-005**: Con la agenda abierta y sin tocarla, una cita que termina se ve «Atendida» en **menos de 2 minutos**. Hoy no cambia hasta recargar.
- **CE-006**: El **100 %** de las reservas hechas a mano en la consola después del despliegue, salvo las llegadas sin reserva, tiene un teléfono válido.
- **CE-007**: Un contacto con una conversación resuelta escribe 7 días después: en **5 de 5** pruebas, la respuesta del agente no usa nada de la conversación anterior y lo saluda por su nombre.
- **CE-008**: Con el cierre a 24 horas, una conversación sin mensajes aparece resuelta **antes de las 25 horas**. Con el ajuste en «nunca», ninguna se cierra sola.
- **CE-009**: La app móvil de hoy crea, abre y cancela reservas después del despliegue igual que antes.

## Fuera de alcance

- **La app móvil.** Luis la dejó para su sesión aparte (2026-11-18). Hasta entonces, en la app el teléfono sigue opcional y con el prefijo `+56`, y no se ve ni se cambia la antelación del agente. La corrección de «Atendida» sí le llega sin tocar su código, porque la app pinta las acciones que la API permite. La 044 (R8.6) pedirá el ajuste de la antelación cuando la app se ponga al día. **La recomendación de los partners nombraba «la app»: mientras tanto, se cumple solo en la consola.**
- **Cambiar la antelación por defecto.** Sigue en 60 minutos. Quien quiera la próxima hora libre la elige en Ajustes.
- **El histórico de citas por cliente.** Luis lo dejó para después (2026-11-18).
- **Los avisos de retoque tras la cita.** Son una función nueva, con su plantilla de Meta y su consentimiento. Va en su propia spec.
- **Cambiar cuándo sale el recordatorio.** Sigue 24 horas antes, y una reserva hecha con menos de 24 horas sigue sin recordatorio (043). El teléfono es necesario para avisar, pero no cambia esas reglas.
- **Las plantillas de Meta.** Fuera de la ventana de 24 horas, un aviso sigue necesitando su plantilla aprobada (043, R15).
- **Exigir teléfono en la lista de espera.** No se pidió. Una entrada sin teléfono sigue sin poder recibir ofertas, como hoy.
- **Cerrar sola en Aforo la reserva confirmada que nunca llegó.** La 043 lo dejó manual y nadie lo pidió.
- **Cambiar el paso de la rejilla de huecos.** La API ya lo acepta, pero no forma parte de la recomendación.
- **Un resumen de la conversación anterior para el agente.** «Lo mínimo» es el nombre y sus citas. Resumir lo hablado sería otra función, con su gasto de modelo.
- **Partir una conversación en varias filas.** Sigue habiendo un solo hilo por contacto y número (030, D11). Lo que cambia es dónde empieza a leer el agente.

## Supuestos

- En producción ningún cliente tuvo actividad de reservas en los 7 días anteriores al 2026-11-18, así que el cierre automático solo está comprobado con citas reales en staging. El planificador de producción está en marcha.
- La app móvil de hoy tolera que la API ofrezca una acción nueva sobre una reserva cerrada: la enseña o la ignora, pero no falla. El plan lo comprueba antes de tocar la API (requisito 2.12).
- El agente no necesita la conversación anterior para atender bien: las citas, que son lo que más importa recordar, viven en Reservas.
- Los avisos que la plataforma envía por su cuenta quedan guardados como mensajes de la conversación, de modo que se puede saber cuáles siguen sin respuesta. Comprobado para los de Reservas.
