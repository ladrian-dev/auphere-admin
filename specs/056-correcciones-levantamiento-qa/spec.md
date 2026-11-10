# Especificación: Correcciones del levantamiento QA de la consola del cliente

**Rama**: `056-correcciones-levantamiento-qa` · **Creada**: 2026-11-07 · **Estado**: Aprobada por el owner el 2026-11-07, con D3 cambiada por él (el partner hace lo mismo que el panel, sin solicitudes)

**Entrada**: el «Levantamiento funcional — Consola de partners Auphere» de QA (exploración de `console.staging.auphere.com` el 6 y 7 de noviembre, en modo solo lectura), revisado contra `develop` en el informe [Revisión del levantamiento QA](https://claude.ai/artifact/Kitdp2E22q2URvcB4NBmnc). Más dos cambios que pidió el owner el 2026-11-07: «el tab Agentes y Negocio no debe aparecer en la consola de customers» y «hoy se le puede activar la consola de customers solo desde el admin panel», que pasa a poder hacerse desde la consola de partners.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API de la consola, la consola, el panel de operador y el runtime del agente, que ya existen. No se abre ninguna superficie |
| **Garantías de aislamiento tocadas** | **1** (RLS): el partner pasa a escribir el acceso de sus clientes, y solo de los suyos. **C8 de ADR-041** (el partner nunca lee el cuerpo de un mensaje): sus rutas siguen sin cuerpos (Requisito 4). Queda abierto, **aceptado por el owner hasta una solución estable** (D3), que un partner que invite a una persona suya a la consola del cliente lea la Bandeja. **8, rozada**: el freno de citas lee lo que hicieron las herramientas en la misma conversación, nunca en otra |
| **Nota de KB que la justifica** | `[[ADR-041-consola-lite-del-cliente-final]]`, sección «Enmienda · 2026-11-07 (spec 056)»: L2 (quién da el acceso), L3 (Agentes y Negocio) y el riesgo de C8. La spec 047 (R50.1 y R50.2) lleva la enmienda tachada. El origen completo está en el informe enlazado arriba |
| **Qué se mide** | **Modelo**: el freno de citas comprueba con el modelo de clasificación las respuestas candidatas que hablan de una cita. Esa llamada va dentro del turno y entra en su cobro a la bolsa del cliente, igual que hoy `classify` y `respond`. Nada más gasta |

## Origen

Revisado el 2026-11-07 contra `develop` (`732576e7`), leyendo código y specs, sin navegador. QA vio staging en `9bab91ef` (spec 055). QA entró como **persona del cliente** de Jemma's Hair (rol `client`, spec 030), no como partner: por eso las rutas de partner le devolvían al Panel.

| # | Lo que dice QA o el owner | Veredicto | Lo que hace el código hoy | Requisito |
|---|---|---|---|---|
| 1 | El agente escribió «Cita confirmada» y no había cita (RSG-001) | **Fallo grave, mitigado y no cerrado** | Desde el 4 nov los fallos de los conectores ya no parecen éxitos y el agente recuerda lo que hicieron sus herramientas. Pero ese recuerdo solo dice «si salió bien, no lo niegues», la regla «no digas que has reservado» solo la llevan los agentes estructurados, el revisor de reservas viene apagado y no hay prueba de punta a punta | 1 |
| 2 | Agentes y Negocio no deben estar en la consola del cliente (owner) | **Cambio pedido** | Vienen por defecto a todo cliente de un partner con la consola nueva (spec 047, R50.1), aunque Auphere no los haya elegido. La app Auphere Customers los enseña por el mismo módulo | 2 |
| 3 | La consola del cliente solo se activa desde el panel (owner) | **Cambio pedido** | Solo la pestaña «Acceso» del panel de operador enciende, elige módulos e invita (spec 030, ADR-041 L2) | 3, 4 |
| 4 | Dos editores de horario y servicios (RSG-002) | **Fallo grave, y pierde datos** | Escriben en el mismo sitio con reglas distintas. Desde Reservas: un tercer turno se pierde, un servicio de 50 min no se puede guardar, «Gratis» pasa a «Sin precio» y el nombre se puede cambiar | 5 |
| 5 | «Corregir esta respuesta» con «Todo el negocio» | **Fallo grave** | Un dato se guarda para todo el negocio. Una regla de comportamiento solo llega al agente que respondió, aunque el diálogo dice «Lo sabrán todos tus agentes» | 9 |
| 6 | «Todas» no enseña las resueltas (RSG-004, DUD-002) | **A propósito, mal dicho** | La spec 030 (R7.3) lo pide. El filtro se llama «Todas» y el botón del estado vacío vuelve a la misma lista vacía | 6 |
| 7 | «El agente pidió ayuda: agent_unpublished» (RSG-009) | **Fallo** | El código sale tal cual en cuatro sitios. La tabla que lo traduce ya existe, pero solo la usa el constructor | 7 |
| 8 | El aviso «espera a una persona» sigue tras resolver (DUD-011) | **Hueco de diseño** | Nada cierra ese aviso | 8 |
| 9 | Error de Reservas con texto de Next.js (RSG-005) | **Fallo; causa sin confirmar** | La pantalla de error pinta el mensaje del error, que en producción es la frase técnica de Next.js | 10 |
| 10 | Validación (RSG-003) | **En parte** | Casi todo se rechaza al guardar, en español. Quedan: lista de espera sin avisos, tope de importe distinto en cada sitio, correo sin validar en la API, fechas especiales ya pasadas | 11 |
| 11 | Acciones destructivas (RSG-007) | **En parte** | Archivar en Reservas, Vaciar, Eliminar y Desconectar confirman. Archivar un servicio o una sede de la ficha y «Deshacer», no. Los diálogos de Reservas se cierran sin preguntar con datos escritos | 12 |
| 12 | Formatos (RSG-010, DUD-009) | **Fallo** | Cuatro formatos de dinero. El teléfono del contacto sale sin «+» | 13 |
| 13 | Acceso en inglés y página 404 (DUD-010, ERR-404) | **Fallo menor** | El cuerpo de /login sigue el idioma del navegador, pero su cabecera está fija en español. La 404 no tiene salida ni pasa por las traducciones | 14 |
| 14 | La sesión caduca sin aviso | **Hueco menor** | Caduca a los 7 días, a propósito y sin renovarse. Nadie avisa antes | 15 |
| 15 | Vaciar y Eliminar chat | **Sin spec** | Funcionan bien, pero entraron sin spec (commit `87b7c4cc`) | 16 |
| 16 | Juan y Roxi comparten calendario (DUD-006) | **Lo resuelve otra rama** | La regla que lo prohíbe (spec 043, R12.4, `calendar_in_use`) está escrita en la rama `reservas-fuente-unica-631d6d`, sin confirmar | Dependencia |

**Lo que no se toca porque está bien o es a propósito** (detalle en el informe): el aislamiento de la Bandeja entre clientes, Tomar el control y Reabrir, el resumen del agente escrito al pedir ayuda, los ajustes de Reservas que se guardan al cambiar, «Deshacer» de un nivel con 20 cambios a la vista, los huecos cada 30 minutos y la zona horaria del negocio.

## Decisiones

Las preguntas que haría `/speckit-clarify`, resueltas con una propuesta. El owner las aprueba o las cambia con la spec. **D2 y D3 son las que más cambian el resultado.**

| # | Pregunta | Decisión propuesta | Por qué |
|---|---|---|---|
| D1 | ¿Qué hace el agente si va a afirmar una cita que no existe? | **No se envía así.** Se repite el turno una vez, diciéndole que no hay reserva hecha y que reserve primero o diga la verdad. Si vuelve a afirmarla, la conversación pasa a una persona con el motivo «El agente dio por hecha una cita que no existe» | Reintentar arregla el caso normal sin escalar de más. Pasar a una persona es el único final seguro |
| D2 | ¿Qué pasa con Agentes y Negocio del cliente? | **Desaparecen de la consola del cliente y de la app**, para todos los clientes, también los que ya los tenían. Pausar agentes y números y editar la ficha pasan a ser solo del partner. El cliente conserva lo que edita desde Reservas › Ajustes (horario, equipo y servicios que se reservan) y «Corregir esta respuesta» | Lo pidió el owner. Enmienda la spec 047, R50.1, R50.2 y R50.4 en la parte del cliente |
| D3 | ¿Puede el partner abrir la Bandeja de su cliente a quien invite? | **Decisión del owner (2026-11-07): sí, como hoy el panel.** La pestaña Acceso del partner hace lo mismo que la del panel, Bandeja incluida, sin solicitudes ni aprobación de Auphere. Se buscará una solución estable más adelante | Se propuso que lo que abre la Bandeja pasara por Auphere, y el owner lo rechazó: «por ahora deja la funcionalidad como está». **Riesgo aceptado**: un partner puede invitar a una persona suya y leer la Bandeja del cliente, que es lo que C8 prohíbe. Sus rutas siguen sin cuerpos. Queda escrito en la enmienda de ADR-041 y en `docs/consola-lite.md` |
| D4 | ¿Dónde vive el acceso en la consola de partners y quién lo usa? | **Una pestaña «Acceso» en la ficha del cliente**, junto a Panel, Negocio y Agentes, con su propia dirección. Dentro, dos tarjetas: «Consola del cliente» y «Personas». La usan owner y admin; los demás roles no ven la pestaña. El panel de operador conserva su pestaña Acceso, con las mismas reglas | Es una página del cliente, como sus otras pestañas. Invitar a alguien a los datos de un negocio es una decisión de quien gestiona la cuenta, no de quien construye agentes |
| D5 | ¿Un editor o dos para horario y servicios? | **El mismo editor, con las mismas reglas, en la ficha (partner) y en Reservas › Ajustes (cliente).** Desde Reservas el cliente crea servicios con su nombre, pero no renombra uno existente, igual que hoy en Negocio | Dos editores con reglas distintas sobre el mismo dato pierden datos. Con D2, la ficha queda para el partner y Reservas para el cliente |
| D6 | ¿Qué hace el filtro «Todas» de la Bandeja? | **Mantener la regla de la spec 030 y llamarlo «Abiertas».** Si no hay abiertas pero sí resueltas, el estado vacío lo dice y lleva a Resueltas | La regla tiene sentido: lo resuelto no pide nada. Lo que confunde es el nombre |
| D7 | Una regla corregida con «Todo el negocio», ¿a quién llega? | **Una propuesta para cada agente activo del cliente**, que el partner revisa y aprueba de una vez | Es lo que el cliente eligió y lo que el diálogo le promete |
| D8 | ¿Los avisos «espera a una persona» se cierran solos? | **Sí**, cuando la conversación deja de esperar: alguien toma el control, se devuelve al agente o se resuelve | Un aviso de algo que ya no pasa es una pantalla que miente (§V) |
| D9 | ¿Qué formato de dinero es el bueno? | **El del idioma de la persona**, igual en todas las pantallas: en español, «10,00 US$». Los campos de importe aceptan coma o punto y enseñan el separador del idioma | Un solo formato. La spec 047 (R11.7) ya lo pedía |
| D10 | ¿Cuándo es «pasada» una fecha especial? | **Cuando su «Hasta» ya pasó.** Un cierre que empezó ayer y acaba mañana se puede guardar | Así se puede apuntar un cierre en curso, y no se apuntan cierres que ya no sirven |

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El agente nunca da por hecha una cita que no existe (Prioridad: P1)

Un cliente final pide cita por WhatsApp. El agente solo le dice que está confirmada si de verdad quedó creada en la agenda. Si no pudo crearla, lo dice o pasa la conversación a una persona.

**Por qué esta prioridad**: es el único fallo que engaña a un cliente final. Alguien se presenta a una cita que no existe.

**Prueba independiente**: con un agente sin herramienta de reservar, o con la de reservar fallando, se le pide una cita por el canal real. Nunca responde que está confirmada.

**Escenarios de aceptación**:

1. **Dado** un agente cuya herramienta de reservar falla, **cuando** el cliente pide una cita, **entonces** la respuesta no dice que la cita está confirmada.
2. **Dado** un agente sin herramienta de reservar, **cuando** el cliente pide una cita, **entonces** el agente dice que no puede reservarla él o pasa la conversación a una persona.
3. **Dado** que la reserva se creó bien, **cuando** el agente la confirma, **entonces** el mensaje sale sin cambios.

---

### Historia 2 — La consola del cliente enseña solo lo que gestiona el cliente (Prioridad: P1)

La persona de un negocio entra en su consola o en la app y ve Panel, Bandeja, Reservas y Consumo, según lo que tenga. No ve Agentes ni Negocio, ni puede llegar a ellos.

**Por qué esta prioridad**: lo pidió el owner. Hoy esas dos secciones salen a todos los clientes sin que nadie las haya elegido.

**Prueba independiente**: un cliente que hoy las tiene entra y no las ve. Abrir `/agentes` o `/negocio` lo lleva a su primer módulo.

**Escenarios de aceptación**:

1. **Dado** un cliente que hoy ve Agentes y Negocio, **cuando** entra tras el cambio, **entonces** su barra lateral no los tiene.
2. **Dado** un cliente, **cuando** abre `/agentes` o `/negocio` por la dirección, **entonces** acaba en su primer módulo, como cualquier ruta que no es suya.
3. **Dado** un cliente, **cuando** llama a la API de agentes o de la ficha de la consola del cliente, **entonces** recibe la misma respuesta que con un módulo que no tiene.

---

### Historia 3 — El partner abre la consola a su cliente sin pedírselo a Auphere (Prioridad: P1)

Desde la ficha de un cliente, el owner o admin del partner enciende su consola, elige los módulos, invita a sus personas y las revoca, igual que hoy Auphere desde el panel (D3).

**Por qué esta prioridad**: hoy cada cliente nuevo de un partner necesita que Auphere entre en el panel. No escala.

**Prueba independiente**: un owner de partner, sin el panel, deja a su cliente con Panel y Reservas encendidos y con una persona invitada que entra.

**Escenarios de aceptación**:

1. **Dado** un owner de partner, **cuando** abre la pestaña Acceso de su cliente y enciende Panel y Reservas, **entonces** queda guardado y auditado con su nombre.
2. **Dado** un cliente sin Bandeja, **cuando** el partner invita a una persona, **entonces** le llega la invitación y entra en Panel y Reservas.
3. **Dado** un cliente con WhatsApp conectado, **cuando** el partner enciende la Bandeja, **entonces** sus personas la ven al entrar, igual que si la hubiera encendido Auphere.
4. **Dado** un builder o un analyst, **cuando** abre la ficha del cliente, **entonces** no ve la pestaña Acceso.

---

### Historia 4 — Horario y servicios valen lo mismo desde cualquier pantalla (Prioridad: P2)

Lo que el partner guarda en la ficha y lo que el cliente guarda en Reservas › Ajustes siguen las mismas reglas. Nada se pierde al pasar de una a otra.

**Por qué esta prioridad**: hoy se pierden datos sin aviso, y el agente dice cosas falsas (un servicio gratis pasa a «lo confirma el equipo»).

**Prueba independiente**: un horario con tres turnos y un servicio «Gratis» de 50 minutos, guardados en la ficha, se abren y se guardan desde Reservas sin cambiar.

**Escenarios de aceptación**:

1. **Dado** un día con tres turnos en la ficha, **cuando** el cliente guarda el horario desde Reservas sin tocar ese día, **entonces** el día conserva sus tres turnos.
2. **Dado** un servicio «Gratis», **cuando** el cliente lo guarda desde Reservas, **entonces** sigue siendo «Gratis».
3. **Dado** un servicio de 50 minutos, **cuando** el cliente cambia su precio desde Reservas, **entonces** se guarda.

---

### Historia 5 — La Bandeja dice la verdad (Prioridad: P2)

El filtro se llama por lo que enseña, el motivo de un escalado se lee, los avisos se cierran cuando ya no hay nada que hacer y una corrección llega a quien el diálogo dice.

**Por qué esta prioridad**: son cuatro sitios donde la pantalla dice algo que no es cierto (§V).

**Prueba independiente**: con dos conversaciones resueltas y ninguna abierta, el estado vacío lleva a Resueltas. Un escalado por agente sin publicar dice «Agente sin publicar».

**Escenarios de aceptación**:

1. **Dado** un cliente con solo conversaciones resueltas, **cuando** abre la Bandeja, **entonces** ve «No tienes conversaciones abiertas», cuántas resueltas tiene y un botón a Resueltas.
2. **Dado** un escalado con motivo `agent_unpublished`, **cuando** se pinta, **entonces** dice «Agente sin publicar».
3. **Dado** un aviso «X espera a una persona», **cuando** alguien toma el control, **entonces** el aviso deja de estar pendiente.
4. **Dado** un cliente con dos agentes activos, **cuando** corrige una regla con «Todo el negocio», **entonces** se proponen dos cambios, uno por agente.

---

### Historia 6 — Pulido: errores, validación, confirmaciones, idioma y formatos (Prioridad: P3)

La consola del cliente no enseña texto técnico, valida igual en todas partes, pregunta antes de lo que no se deshace, no pierde lo escrito y usa un formato por cosa.

**Por qué esta prioridad**: cada punto es pequeño. Juntos son la diferencia entre una beta y un producto.

**Prueba independiente**: cada criterio de los Requisitos 10 a 15 es una prueba de componente o de página.

**Escenarios de aceptación**:

1. **Dado** un fallo al cargar Reservas, **cuando** se pinta el error, **entonces** dice en el idioma de la persona qué pasó y ofrece Reintentar, sin texto técnico.
2. **Dado** el diálogo «Nueva reserva» con un nombre escrito, **cuando** se pulsa cerrar, **entonces** pregunta antes de descartar.

---

### Casos límite

- **Un cliente que hoy usa Agentes o Negocio** (por ejemplo, pausa su número): tras el cambio, solo lo puede hacer su partner. Los avisos de pausa le siguen llegando, porque le informan de su servicio.
- **Un enlace guardado de la app a Negocio o a un agente**: abre el primer módulo del cliente, no una pantalla rota.
- **Datos ya guardados que no cumplen las reglas unificadas** (Requisito 5): se enseñan tal cual, marcados «Revísalo», y nunca se cambian sin que alguien guarde.
- **El partner apaga el acceso** con personas dentro: se cierran sus sesiones, como hoy desde el panel.
- **El partner y Auphere cambian el acceso del mismo cliente a la vez**: gana el último que guarda, como hoy entre dos operadores del panel, y los dos cambios quedan en la auditoría.
- **Una respuesta que menciona una cita pasada** («tu cita de ayer»): no es una cita afirmada. El freno solo mira las que la respuesta da por hechas ahora.
- **Un agente que reserva con un calendario conectado** (Google Calendar o Calendly) y no con Reservas: una reserva creada con éxito por esa herramienta cuenta como reserva hecha.
- **Ausencia diseñada (§V)**: quien no puede gestionar el acceso no ve la pestaña. Un cliente que no puede tener Bandeja (sin WhatsApp conectado) no la ve entre los módulos, como hoy en el panel.

## Requisitos *(obligatorio)*

### Requisito 1 — El freno de citas

**Historia de usuario:** Como negocio, quiero que mi agente nunca le diga a un cliente que tiene una cita que no existe, para que nadie se presente a una hora que no está reservada.

#### Criterios de aceptación

1. WHEN una respuesta del agente da por hecha una reserva (creada, confirmada, cambiada o mantenida) THEN el sistema DEBE comprobar, antes de enviarla, que en esa conversación hay una reserva creada o cambiada con éxito que la respalda.
2. IF no hay reserva que la respalde THEN el sistema NO DEBE enviar esa respuesta, y DEBE seguir D1: un reintento del turno y, si se repite, pasar la conversación a una persona con el motivo «El agente dio por hecha una cita que no existe».
3. El sistema DEBE contar como reserva hecha la que crea o cambia con éxito cualquier herramienta de reservar del agente: Reservas o un calendario conectado.
4. El freno DEBE valer para todos los agentes, estructurados y legados, y no depender de que el agente lleve una regla en su prompt.
5. El sistema DEBE dejar constancia de cada vez que el freno actúa, con la conversación y el agente, sin el texto del mensaje.
6. WHEN el freno comprueba una respuesta con el modelo THEN el coste DEBE entrar en el cobro de ese turno, como `classify` y `respond`.
7. DEBE existir una prueba de punta a punta, con el canal real en staging, que pida una cita a un agente con la herramienta de reservar fallando y compruebe que el cliente final no recibe una confirmación.

### Requisito 2 — Agentes y Negocio fuera de la consola del cliente

**Historia de usuario:** Como owner de Auphere, quiero que la persona del negocio no vea ni use Agentes ni Negocio, para que esas decisiones las tome quien gestiona sus agentes.

#### Criterios de aceptación

1. El sistema NO DEBE dar los módulos Agentes ni Negocio a ninguna persona de cliente, ni por defecto ni porque estén guardados.
2. El sistema DEBE retirar esos dos módulos del acceso de todos los clientes que los tienen guardados, sin tocar los demás módulos.
3. IF alguien intenta guardar Agentes o Negocio como módulo de un cliente, desde el panel o desde la consola de partners, THEN el sistema DEBE rechazarlo.
4. WHEN una persona de cliente abre `/agentes` o `/negocio` THEN la consola DEBE llevarla a su primer módulo, como con cualquier ruta que no es suya.
5. WHEN una persona de cliente llama a las rutas de agentes o de la ficha de su consola THEN la API DEBE responder lo mismo que a un módulo que no tiene.
6. La app Auphere Customers DEBE dejar de enseñar Agentes y Negocio, en sus pestañas, en Inicio y en Ajustes. Un enlace a esas pantallas DEBE abrir el primer módulo del cliente.
7. El sistema DEBE seguir enviando al cliente los avisos de pausa y reanudación de sus agentes y números.
8. Una corrección de dato con «Todo el negocio» DEBE seguir guardándose en la ficha, aunque el cliente ya no la vea.
9. Las personas del partner DEBEN poder seguir haciendo todo lo que hacían en Agentes y Negocio desde la consola de partners.

### Requisito 3 — El acceso del cliente desde la consola de partners

**Historia de usuario:** Como owner o admin de un partner, quiero encender la consola de mi cliente, elegir sus módulos e invitar a sus personas, para no depender de Auphere en cada alta.

#### Criterios de aceptación

1. La ficha de un cliente en la consola de partners DEBE tener una pestaña «Acceso», con su propia dirección, después de Panel, Negocio y Agentes.
2. WHERE la persona del partner es owner o admin EL sistema DEBE enseñar la pestaña. Para los demás roles NO DEBE existir, ni en la barra ni por la dirección.
3. La pestaña DEBE tener una tarjeta «Consola del cliente», con el interruptor de acceso y los módulos Panel, Bandeja, Reservas (con su modo) y Consumo, y las mismas reglas del panel:
   - encendida exige al menos un módulo;
   - la Bandeja exige un WhatsApp conectado al elegirla;
   - Reservas exige su modo la primera vez;
   - cambiar el modo con reservas futuras pide decidir qué pasa con ellas antes de guardar.
4. La pestaña DEBE tener una tarjeta «Personas» con la lista de personas del cliente y su estado (invitada, activa, caducada, revocada).
5. Cada fila de «Personas» DEBE tener una sola acción a la vista, la principal para su estado (Reenviar a una invitada o caducada). El resto DEBE ir en «⋯», y «Revocar» al final, en rojo y con confirmación.
6. WHEN el partner invita a una persona THEN el sistema DEBE enviarle la invitación de un solo uso de hoy (21 días) y DEBE enseñar el enlace una vez, como el panel.
7. WHEN el partner revoca a una persona o apaga el acceso THEN el sistema DEBE cerrar sus sesiones en la misma operación.
8. Cada cambio DEBE quedar en la auditoría del partner y del panel con el nombre de quien lo hizo.
9. El panel de operador DEBE conservar su pestaña Acceso, con las mismas reglas que la del partner y sin los módulos Agentes ni Negocio.
10. IF la persona del partner intenta gestionar el acceso de un cliente que no es suyo THEN el sistema DEBE responder el mismo 404 que con un cliente inexistente.

### Requisito 4 — Las rutas del partner siguen sin cuerpos (C8)

**Historia de usuario:** Como negocio, quiero que la agencia que me vende el agente no reciba por sus pantallas lo que me escriben mis clientes, aunque gestione mi acceso.

#### Criterios de aceptación

1. El partner NO DEBE recibir el cuerpo de ningún mensaje por ninguna ruta, nueva o de antes. El barrido de aislamiento de `/console/*` DEBE cubrir las rutas nuevas sin excepción nueva.
2. Las rutas nuevas del acceso NO DEBEN devolver nada de la Bandeja del cliente: ni conversaciones, ni contactos, ni el texto de los avisos.
3. La enmienda de ADR-041 y `docs/consola-lite.md` DEBEN decir el riesgo que el owner aceptó en D3: una persona invitada por el partner lee la Bandeja del cliente.

### Requisito 5 — Un solo juego de reglas para horario y servicios

**Historia de usuario:** Como negocio, quiero que mi horario y mis servicios digan lo mismo los edite quien los edite, para que el agente no diga cosas falsas.

#### Criterios de aceptación

1. La ficha del partner y Reservas › Ajustes del cliente DEBEN aceptar y rechazar exactamente los mismos valores del horario del negocio: número de turnos por día, paso de las horas, horas posibles y turnos que cruzan la medianoche. Reservas edita solo el horario de todo el negocio. El horario propio de una sede se enseña allí sin poder editarse, y guardar desde Reservas NO DEBE cambiarlo.
2. Las dos DEBEN aceptar y rechazar exactamente los mismos valores de servicio: duraciones, tipo de precio (Sin precio, Gratis, Importe), importe máximo y categoría.
3. IF el cliente guarda desde Reservas un horario o un servicio THEN el sistema NO DEBE cambiar ninguna parte que el cliente no tocó.
4. Desde Reservas el cliente DEBE poder crear un servicio con su nombre, y NO DEBE poder renombrar uno existente.
5. IF un dato guardado no cumple las reglas unificadas THEN las dos pantallas DEBEN enseñarlo tal cual, marcado «Revísalo», y el sistema NO DEBE cambiarlo hasta que alguien lo guarde.
6. Un error al guardar DEBE decir qué valor falla y por qué. NO DEBE decir «No se pudo hablar con el servidor» cuando el servidor respondió.

### Requisito 6 — «Abiertas» en la Bandeja

#### Criterios de aceptación

1. El filtro por defecto de la Bandeja DEBE llamarse «Abiertas» y enseñar lo mismo que hoy enseña «Todas».
2. WHEN no hay conversaciones abiertas y sí resueltas THEN la Bandeja DEBE decir que no hay abiertas, cuántas resueltas hay y ofrecer un botón que abre Resueltas.
3. WHEN no hay ninguna conversación THEN la Bandeja DEBE enseñar el estado vacío de hoy, sin botón.

### Requisito 7 — Motivos de escalado legibles

#### Criterios de aceptación

1. Todo motivo de escalado que la Bandeja pinta (actividad, fila, hilo y caja de respuesta) DEBE pasar por la misma tabla de textos que usa el constructor.
2. IF un motivo no está en la tabla THEN la Bandeja DEBE enseñar un texto genérico («El agente pidió ayuda») y NO DEBE enseñar el código.
3. El motivo `agent_unpublished` DEBE decir «Agente sin publicar», como fija el contrato de eventos de la spec 047.

### Requisito 8 — Los avisos de escalado se cierran solos

#### Criterios de aceptación

1. WHEN una conversación deja de esperar a una persona (alguien toma el control, se devuelve al agente o se resuelve) THEN el sistema DEBE marcar como atendido su aviso «espera a una persona».
2. Un aviso atendido NO DEBE contar como pendiente en la campana ni en la app.

### Requisito 9 — Corregir con «Todo el negocio»

#### Criterios de aceptación

1. WHEN una persona del cliente corrige una regla de comportamiento con «Todo el negocio» THEN el sistema DEBE proponer el cambio a cada agente activo del cliente, no solo al que respondió.
2. El partner DEBE poder revisar y aprobar esas propuestas de una vez, y DEBE ver que vienen de la misma corrección.
3. Con «Solo este agente», el sistema DEBE seguir proponiendo el cambio solo al agente que respondió.
4. El texto de cada alcance DEBE describir lo que de verdad pasa.

### Requisito 10 — Errores sin texto técnico

#### Criterios de aceptación

1. WHEN una pantalla de la consola del cliente falla al cargar THEN DEBE decir, en el idioma de la persona, que no se pudo cargar y ofrecer Reintentar. NO DEBE enseñar el mensaje técnico del error.
2. El plan DEBE encontrar en los registros de staging la causa del fallo de Reservas del 6 de noviembre (cambiar de periodo y pulsar «Hoy») y corregirla. WHEN se repite esa secuencia diez veces seguidas THEN la agenda DEBE cargarse las diez.

### Requisito 11 — Validación igual en todas partes

#### Criterios de aceptación

1. «Apuntar en la lista de espera» DEBE validar como «Nueva reserva»: avisos al salir del campo y botón desactivado mientras falte el cliente, el servicio o haya un teléfono inválido.
2. El importe máximo de un servicio DEBE ser el mismo en la consola y en la API, y superar el tope DEBE dar un mensaje que lo diga.
3. La API DEBE rechazar un correo de persona del equipo con formato inválido.
4. IF el «Hasta» de una fecha especial ya pasó THEN el sistema DEBE rechazarla, en la consola y en la API (D10).
5. Los mensajes de validación DEBEN salir en el idioma de la consola, nunca del navegador.

### Requisito 12 — Confirmar lo que no se deshace y no perder lo escrito

#### Criterios de aceptación

1. Archivar un servicio o una sede desde la ficha DEBE pedir confirmación, como archivar en Reservas.
2. «Deshacer» un cambio de la ficha DEBE pedir confirmación, diciendo qué cambio se deshace. Con el Requisito 2 desaparece la única pantalla que lo enseña hoy (Negocio del cliente): la confirmación va en el componente de historial de la ficha, que es el que la enseñe cuando se monte.
3. WHEN se cierra un diálogo de Reservas con datos escritos THEN DEBE preguntar antes de descartarlos.

### Requisito 13 — Un formato de dinero y de teléfono

#### Criterios de aceptación

1. Todos los importes de la consola del cliente y de la ficha DEBEN enseñarse con el formato del idioma de la persona (D9).
2. Los campos de importe DEBEN aceptar coma o punto como separador decimal y DEBEN enseñar el del idioma.
3. El teléfono de un contacto DEBE enseñarse con «+» y su prefijo de país.

### Requisito 14 — Idioma del acceso y página 404

#### Criterios de aceptación

1. Las páginas de acceso (entrar, recuperar, crear cuenta) DEBEN pintar la cabecera y el cuerpo en el mismo idioma.
2. WHEN una persona con sesión abre una ruta que no existe THEN DEBE ver la 404 dentro de la consola, con su menú y un enlace a su primer módulo.
3. WHEN una persona sin sesión abre una ruta que no existe THEN la 404 DEBE ofrecer «Entrar».
4. El texto de la 404 DEBE pasar por las traducciones y seguir sin revelar si lo pedido existe.

### Requisito 15 — Aviso antes de que caduque la sesión

#### Criterios de aceptación

1. WHEN a la sesión le quedan menos de 24 horas THEN la consola DEBE avisar una vez, sin bloquear, con un botón «Volver a entrar».
2. La sesión DEBE seguir caducando a los 7 días sin renovarse.

### Requisito 16 — Vaciar y Eliminar chat (spec retroactiva)

Lo que ya hace el código desde el commit `87b7c4cc`, escrito como requisito para que tenga prueba.

#### Criterios de aceptación

1. «Vaciar chat» y «Eliminar chat» DEBEN pedir confirmación con su propio texto.
2. «Vaciar chat» DEBE hacer que el agente deje de ver los mensajes anteriores, sin borrarlos.
3. «Eliminar chat» DEBE resolver la conversación sin borrar sus mensajes. WHEN el contacto vuelve a escribir THEN DEBE aparecer como conversación nueva.
4. Las dos DEBEN quedar en la auditoría con quién las hizo.

### Requisito 17 — Documentación

#### Criterios de aceptación

1. El mismo cambio que implemente cada requisito DEBE actualizar su documento: `docs/consola-lite.md` (Requisitos 2, 3, 4, 6 a 9, 16), `docs/console.md` (3, 4), `docs/admin.md` (3, 4), `docs/ficha-del-negocio.md` y `docs/reservas.md` (5, 11, 12), `docs/agentes.md` (1, 9) y `docs/app-movil.md` (2).
2. La KB DEBE recoger la enmienda de ADR-041 (L2 y, según D3, C8) y la de la spec 047 (R50) antes de `/speckit-plan`.

### Entidades clave

- **Acceso del cliente**: si sus personas pueden entrar y qué módulos ven. Pertenece al cliente (tenant) y la RLS lo alcanza por su `tenant_id`. Lo escriben Auphere y, desde esta spec, su partner.
- **Persona del cliente**: alguien invitado a la consola de un cliente, con su estado y su invitación. Pertenece al cliente.
- **Constancia del freno de citas** (nueva): cada vez que el freno actúa, con la conversación, el agente y el resultado (reintento o paso a una persona), sin el texto del mensaje. Pertenece al cliente.

## Criterios de éxito *(obligatorio)*

- **CE-001**: en la prueba de punta a punta, cero respuestas que confirmen una cita inexistente en 20 intentos con la herramienta de reservar fallando.
- **CE-002**: ninguna persona de cliente ve Agentes ni Negocio, en la consola ni en la app, el día del despliegue.
- **CE-003**: un owner de partner deja a un cliente nuevo con la consola encendida y una persona invitada en menos de 3 minutos, sin escribir a Auphere.
- **CE-004**: ninguna ruta nueva devuelve a un partner el cuerpo de un mensaje (barrido de aislamiento en verde).
- **CE-005**: un horario de tres turnos y un servicio «Gratis» de 50 minutos sobreviven a diez guardados alternos entre la ficha y Reservas sin cambiar.
- **CE-006**: QA repite el levantamiento sobre la consola del cliente y no encuentra ninguno de los fallos del informe.

## Fuera de alcance

- Impedir que un partner lea la Bandeja de su cliente invitando a una persona suya (D3): el owner lo deja para una solución estable más adelante.
- La regla que impide que dos personas usen el mismo calendario: la trae la spec 043 (R12.4) en la rama `reservas-fuente-unica-631d6d`. **Es una dependencia**: esa rama debe estar fusionada antes de cerrar esta spec.
- Un levantamiento de la consola de partners, del panel y de la app: es otra ronda de QA.
- Ctrl K en pantallas estrechas: en un teléfono no hay teclado con Ctrl.
- Un control para cambiar el paso de los huecos (15, 30 o 60 minutos): nadie lo ha pedido.
- «Deshacer» de más de un nivel y paginar «Últimos cambios»: la spec 047 los fija así.
- «Pausar» en un agente en Borrador: desaparece con la sección Agentes del cliente (Requisito 2).
- Regenerar el resumen del agente: la spec 030 prohíbe gastar modelo en ello.

## Supuestos

- La app Auphere Customers ya decide sus pestañas por los módulos del cliente, así que el Requisito 2 no necesita versión nueva de la app salvo para los enlaces directos. Si la necesita, va en la siguiente versión por las tiendas.
- La invitación de un solo uso, su caducidad y el cierre de sesiones al revocar son los del panel de hoy, y se reutilizan.
- Los datos de prueba de Jemma's Hair (Juan y Roxi con el mismo correo) no son una regla del producto.
