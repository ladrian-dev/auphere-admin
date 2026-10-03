# Especificación: el equipo confirma o rechaza los pagos desde WhatsApp

**Rama**: `025-revision-de-pagos` · **Creada**: 2026-10-01 · **Estado**: Borrador

**Entrada**: descripción del owner: ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `1` — el agente escribe por primera vez a un número que no es el del cliente que conversa: los revisores del negocio. Sale siempre del número del propio negocio y solo a números que el partner puso en la lista |
| **Garantías de aislamiento tocadas** | Una nueva. Una pulsación de un revisor solo resuelve pagos del negocio dueño de ese revisor, aunque el mismo teléfono sea revisor de otro negocio. Quién es revisor lo decide la configuración del agente del tenant, nunca el remitente |
| **Nota de KB que la justifica** | `[[clients/flor-y-encanto]]` (2026-10-01) y `[[clients/flor-y-encanto-prompt]]` |
| **Qué se mide** | Los avisos a revisores salen del número del negocio y cuentan como mensajes de canal del cliente, como cualquier otro mensaje del agente. La pulsación de un revisor no llama al modelo |

## Origen

El 2026-10-01 el owner definió cómo vende Flor y Encanto por WhatsApp: el
cliente paga por el enlace de la tienda o por transferencia bancaria, y
manda el comprobante por el chat. El owner pidió que, cuando haya una venta
o llegue un comprobante, el agente escriba a dos números del equipo
(+56991280655 y +56989829063) con el pedido y dos botones, **Confirmar
pago** y **Rechazar pago**.

Medido en el código ese día:

1. Existe un flujo para «consultar al dueño», pero no sirve para esto.
   Escribe desde un número de Auphere y no desde el del negocio. Llega a un
   solo teléfono, solo con texto, sin botones ni imagen, y no manda el
   resumen del caso. La respuesta se empareja por texto libre.
2. El número del negocio ya sabe mandar botones e imágenes, y la plataforma
   ya entiende la pulsación de un botón. Pero cada envío del agente va atado
   a la conversación del cliente que escribe: el agente no puede escribir a
   otro número.
3. WhatsApp solo deja mandar un mensaje libre con botones a un revisor si
   ese revisor escribió al número del negocio en las últimas 24 horas.
   Fuera de esa ventana hace falta una plantilla de mensaje aprobada por
   Meta, con botones de respuesta rápida, en la cuenta del negocio. La
   consola ya crea y sigue plantillas en Canales.
4. La lista «A quién responde» (spec 024) decide a quién contesta el agente.
   Un revisor tiene que poder pulsar los botones aunque no esté en esa
   lista, y su pulsación no debe arrancar una venta con el agente.

Hasta que esto exista, el agente pasa la conversación a una persona al
recibir el comprobante, y el equipo lo revisa en la app del teléfono.

## Clarifications

### Session 2026-10-01

- Q: ¿Cómo se entera el agente de que un pedido se pagó por el enlace de la tienda? → A: **Cuando el cliente se lo dice** (owner, opción A). El agente comprueba el pedido en la tienda y avisa a los revisores. Que la tienda avise sola queda fuera de esta spec.
- Q: ¿A quién avisa el agente cuando pasa una conversación a una persona? → A: **A los mismos revisores de pagos** (owner, 2026-10-01: «les debe avisar a +56991280655 y +56989829063»), con la plantilla `alert_escalation_v1` desde el número del negocio, además del teléfono del dueño si existe.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Un comprobante llega al equipo con botones (Prioridad: P1)

Un cliente final paga por transferencia y manda el comprobante por
WhatsApp. El agente le responde que lo están verificando. A la vez, cada
revisor del negocio recibe en su WhatsApp, desde el número del negocio, el
resumen del pedido y la imagen del comprobante, con dos botones:
**Confirmar pago** y **Rechazar pago**.

**Por qué esta prioridad**: es el paso que hoy obliga a un humano a leer
cada conversación para encontrar los comprobantes. Sin él no hay nada que
confirmar.

**Prueba independiente**: con dos revisores configurados, mandar un
comprobante desde un número de cliente y comprobar que los dos revisores
reciben el aviso con la imagen y los dos botones.

**Escenarios de aceptación**:

1. **Dado** un negocio con dos revisores y un cliente que ya eligió producto,
   modalidad y fecha, **cuando** el cliente manda la imagen de una
   transferencia, **entonces** cada revisor recibe un aviso con producto,
   modalidad (envío o retiro), comuna o lugar de retiro, fecha y rango u
   hora, total, forma de pago, nombre y número del cliente, la imagen del
   comprobante y los dos botones.
2. **Dado** ese mismo caso, **cuando** el aviso sale, **entonces** el
   cliente recibe una respuesta que dice que el pago se está verificando y
   no ve ni a los revisores ni sus números.
3. **Dado** un revisor que no escribió al número del negocio en las últimas
   24 horas, **cuando** sale el aviso, **entonces** le llega igual, con la
   plantilla aprobada del negocio, y el comprobante en el mismo mensaje o
   justo después.
4. **Dado** un comprobante en PDF o como texto pegado, **cuando** sale el
   aviso, **entonces** el revisor recibe el documento o el texto en lugar de
   la imagen.

---

### Historia 2 — Un revisor pulsa y el cliente se entera (Prioridad: P1)

Un revisor pulsa **Confirmar pago**. El pago queda confirmado una sola vez.
El otro revisor recibe que ya lo confirmó su compañero, con nombre. El
agente escribe al cliente que el pago está verificado y que el pedido se
prepara para la fecha y el rango elegidos. Si el revisor pulsa **Rechazar
pago**, el agente le dice al cliente con tacto que no pudieron verificar la
transferencia y pasa la conversación a una persona del equipo.

**Por qué esta prioridad**: sin la vuelta al cliente, el botón no ahorra
trabajo; el equipo tendría que escribirle a mano igual.

**Prueba independiente**: con un aviso pendiente, pulsar Confirmar desde un
revisor y comprobar la respuesta al cliente y el mensaje al otro revisor.
Repetir con Rechazar.

**Escenarios de aceptación**:

1. **Dado** un aviso pendiente, **cuando** un revisor pulsa Confirmar pago,
   **entonces** el cliente recibe en menos de un minuto que su pago está
   verificado, con la fecha y el rango u hora de su pedido.
2. **Dado** un aviso pendiente, **cuando** un revisor pulsa Rechazar pago,
   **entonces** el cliente recibe que no se pudo verificar el pago, sin
   culparlo, y la conversación queda en manos de una persona.
3. **Dado** que un revisor ya resolvió el pago, **cuando** el otro pulsa
   cualquiera de los dos botones, **entonces** no cambia nada y ese revisor
   recibe quién lo resolvió y cómo.
4. **Dado** cualquier resolución, **cuando** el partner revisa la
   auditoría, **entonces** ve quién confirmó o rechazó, cuándo y de qué
   conversación.
5. **Dado** un revisor que no está en la lista «A quién responde», **cuando**
   pulsa un botón, **entonces** la pulsación cuenta y el agente no le
   contesta como si fuera un cliente.

---

### Historia 3 — El partner elige quién revisa los pagos (Prioridad: P2)

En Ajustes del agente hay una sección **«Revisión de pagos»** donde el
partner pone los números del equipo que revisan pagos, con un nombre por
número, igual que en «A quién responde». Se guarda en el borrador y se
aplica al publicar. La sección dice si la plantilla de aviso está aprobada
por Meta y, si no lo está, que los revisores sin conversación abierta en
las últimas 24 horas no recibirán el aviso.

**Por qué esta prioridad**: el primer negocio se puede configurar a mano;
el segundo no debería necesitar a Auphere.

**Prueba independiente**: poner dos números, publicar y mandar un
comprobante.

**Escenarios de aceptación**:

1. **Dado** Ajustes del agente, **cuando** el partner añade dos revisores y
   publica, **entonces** el siguiente comprobante les llega a los dos.
2. **Dado** un número mal escrito, **cuando** el partner guarda,
   **entonces** la consola señala ese número y no guarda.
3. **Dado** un negocio sin plantilla de aviso aprobada, **cuando** el
   partner abre la sección, **entonces** la consola lo dice y le lleva a
   crearla desde Canales con el texto ya preparado.
4. **Dado** un negocio sin revisores, **cuando** llega un comprobante,
   **entonces** el agente hace lo de hoy: responde al cliente y pasa la
   conversación a una persona.

---

### Historia 4 — La pantalla dice qué pagos esperan revisión (Prioridad: P3)

En Conversaciones, la conversación con un pago por revisar lo dice («pago
por revisar»), y la resuelta dice cómo terminó y quién la resolvió.

**Por qué esta prioridad**: los revisores trabajan desde WhatsApp; la
consola es para el partner que supervisa.

**Prueba independiente**: con un aviso pendiente y otro resuelto, abrir
Conversaciones.

**Escenarios de aceptación**:

1. **Dado** un pago pendiente, **cuando** el partner abre Conversaciones,
   **entonces** esa conversación dice «pago por revisar» y desde cuándo.
2. **Dado** un pago resuelto, **cuando** el partner abre Conversaciones,
   **entonces** dice si se confirmó o se rechazó y quién lo hizo.

---

### Casos límite

- **Los dos revisores pulsan casi a la vez**: gana el primero que llega; el
  segundo recibe quién lo resolvió y cómo.
- **El cliente manda dos comprobantes del mismo pedido**: el segundo se suma
  al aviso pendiente como un comprobante más, no abre otro.
- **El cliente escribe mientras el pago está pendiente**: el agente le
  responde que lo están verificando, sin volver a avisar a los revisores.
- **El cliente manda el comprobante sin haber elegido producto**: el aviso
  sale igual con lo que se sabe y lo dice («pedido sin completar en el
  chat»).
- **El comprobante no es un comprobante** (una foto cualquiera): el agente
  decide si lo es; si duda, pregunta al cliente antes de avisar.
- **Un revisor tiene la ventana cerrada y no hay plantilla aprobada**: ese
  revisor no recibe el aviso. El resto sí. Si ninguno lo recibe, el agente
  pasa la conversación a una persona como hoy y la consola lo dice.
- **Un pago lleva 24 horas sin resolver**: sigue pendiente; la consola lo
  enseña. No hay recordatorios automáticos en esta spec.
- **La resolución llega cuando la ventana del cliente ya se cerró**: el
  agente no puede escribirle un mensaje libre; la conversación queda
  marcada para que el equipo le escriba desde la app.
- **El mismo teléfono es revisor de dos negocios**: cada botón lleva su
  propio pago; pulsar resuelve solo el de ese negocio.
- **Un revisor es también un número de la lista «A quién responde»** (hoy
  pasa con +56989829063): sus mensajes de texto siguen siendo una
  conversación de prueba con el agente; solo sus pulsaciones de botones de
  revisión van a la revisión.
- **Pago por el enlace de la tienda**: ver Requisito 6.

## Requisitos *(obligatorio)*

### Requisito 1 — El agente abre una revisión al recibir un comprobante

**Historia de usuario:** Como negocio que cobra por transferencia, quiero que
cada comprobante llegue a mi equipo con el pedido y dos botones, para no
tener que buscarlo en las conversaciones.

#### Criterios de aceptación

1. WHEN el agente reconoce un comprobante de transferencia de un cliente
   THEN el sistema DEBE abrir una revisión de pago ligada a esa
   conversación con el resumen del pedido que el agente conoce y el o los
   comprobantes.
2. WHEN se abre una revisión THEN el sistema DEBE avisar a cada revisor
   del negocio desde el número del propio negocio, con el resumen, el
   comprobante y los botones Confirmar pago y Rechazar pago.
3. IF la ventana de 24 horas de un revisor está abierta THEN el aviso DEBE
   ir como mensaje con botones e imagen; IF está cerrada THEN DEBE ir con
   la plantilla aprobada del negocio, y el comprobante en el mismo mensaje
   o justo después.
4. IF una revisión del mismo cliente sigue pendiente THEN un comprobante
   nuevo DEBE sumarse a ella y NO DEBE abrir otra.
5. El agente DEBE responder al cliente que el pago se está verificando, y
   NO DEBE confirmar el pago ni el pedido por su cuenta.
6. El cliente NO DEBE ver los números ni los nombres de los revisores.

### Requisito 2 — Una pulsación resuelve el pago una sola vez

1. WHEN un revisor pulsa un botón de una revisión pendiente THEN el sistema
   DEBE marcarla confirmada o rechazada, con quién y cuándo, una sola vez.
2. WHEN una revisión ya está resuelta THEN cualquier pulsación posterior NO
   DEBE cambiarla, y el sistema DEBE decirle a ese revisor quién la
   resolvió y cómo.
3. WHEN se resuelve THEN el sistema DEBE avisar al resto de revisores de
   quién la resolvió y cómo.
4. La pulsación DEBE emparejarse por un identificador que viaja en el
   botón, nunca por el texto del mensaje.
5. Una pulsación DEBE resolver solo revisiones del negocio dueño de ese
   revisor.
6. La pulsación de un revisor NO DEBE llegar al agente como mensaje de
   cliente, esté o no ese número en la lista «A quién responde».

### Requisito 3 — El cliente se entera del resultado

1. WHEN una revisión se confirma THEN el agente DEBE escribir al cliente
   que el pago está verificado y que el pedido se prepara para la fecha y
   el rango u hora elegidos.
2. WHEN una revisión se rechaza THEN el agente DEBE escribir al cliente,
   sin culparlo, que no se pudo verificar la transferencia, y DEBE pasar la
   conversación a una persona.
3. IF la ventana de 24 horas del cliente está cerrada THEN el sistema NO
   DEBE fingir que le escribió: la conversación DEBE quedar marcada para que
   el equipo le escriba.

### Requisito 4 — Los revisores se eligen en Ajustes del agente

1. El sistema DEBE ofrecer en Ajustes del agente una sección «Revisión de
   pagos» con una lista de números con nombre, con las mismas reglas de
   formato que «A quién responde».
2. El cambio DEBE ir al borrador y aplicarse al publicar, como el resto de
   Ajustes del agente, y DEBE viajar con las versiones.
3. La sección DEBE decir si la plantilla de aviso del negocio está aprobada
   y, si no, llevar a crearla desde Canales con el texto preparado.
4. IF la lista está vacía THEN el agente DEBE comportarse como hoy: pasar la
   conversación a una persona al recibir un comprobante.
5. Quien solo mira DEBE ver la sección sin poder editarla.

### Requisito 5 — La pantalla dice qué pagos esperan

1. Conversaciones DEBE marcar las conversaciones con un pago por revisar,
   desde cuándo, y las resueltas con su resultado y quién la resolvió.
2. La auditoría DEBE registrar cada aviso enviado o no entregado y cada
   resolución.
3. El Companion DEBE poder leer los pagos pendientes de un cliente con la
   misma lectura que la pantalla.

### Requisito 6 — Ventas pagadas por el enlace de la tienda

1. WHEN el cliente dice que pagó por el enlace THEN el agente DEBE buscar
   su pedido en la tienda y, si lo encuentra, abrir la revisión con el
   estado real del pedido. El sistema NO DEBE esperar ningún aviso de la
   tienda.
2. WHEN se conoce una venta pagada por el enlace THEN el sistema DEBE
   avisar a los revisores con el resumen y el estado del pedido en la
   tienda, sin botones, porque la pasarela ya verificó el pago.
3. IF el pedido figura sin pagar o fallido THEN el aviso DEBE llevar los
   botones, como una transferencia.

### Requisito 7 — Lo que no cambia

1. La lista «A quién responde» sigue decidiendo a quién contesta el agente.
2. El flujo de «consultar al dueño» y su número de Auphere siguen como hoy.
3. El agente sigue sin verificar transferencias contra el banco.

### Entidades clave

- **Revisor de pagos**: número y nombre del equipo del negocio que puede
  confirmar o rechazar pagos. Parte de la configuración del agente
  (versión). Pertenece al tenant.
- **Revisión de pago**: una por pedido pendiente de pago en una
  conversación. Resumen del pedido, comprobantes, estado (pendiente,
  confirmada, rechazada), quién la resolvió y cuándo. Pertenece al tenant.
- **Aviso a un revisor**: un envío de una revisión a un revisor. Cómo salió
  (mensaje con botones o plantilla), si se entregó y, si no, por qué.
- **Plantilla de aviso de pago**: plantilla de utilidad en la cuenta de
  WhatsApp del negocio con los dos botones de respuesta rápida.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un comprobante enviado por un cliente llega a los dos
  revisores de Flor y Encanto con el resumen, la imagen y los dos botones
  en menos de un minuto.
- **CE-002**: tras una pulsación, el cliente recibe el resultado en menos de
  un minuto, y el otro revisor recibe quién lo resolvió.
- **CE-003**: con dos pulsaciones casi simultáneas, el pago queda resuelto
  una sola vez y la auditoría registra una sola resolución.
- **CE-004**: un revisor con la ventana de 24 horas cerrada recibe el aviso
  igual cuando la plantilla está aprobada.
- **CE-005**: un partner configura dos revisores desde la consola, sin
  ayuda de Auphere, en menos de tres minutos.
- **CE-006**: ninguna respuesta al cliente contiene el número o el nombre de
  un revisor.

## Fuera de alcance

- Verificar la transferencia contra el banco.
- Crear o cambiar el estado del pedido en WooCommerce al confirmar.
- Recordatorios a los revisores si nadie pulsa.
- Pedir al revisor el motivo de un rechazo.
- Que la tienda avise sola a la plataforma cuando se paga un pedido
  (opción B de la aclaración): sin el mensaje del cliente no hay aviso.
- Instalar Mercado Pago en la tienda: hoy la tienda cobra en línea con
  Flow, y eso lo decide el negocio en su web.

## Supuestos

- Los avisos salen del número del negocio, no de un número de Auphere: el
  equipo reconoce el remitente y no hace falta otra cuenta.
- El agente decide si una imagen es un comprobante con el mismo criterio
  con que hoy lee imágenes; si duda, pregunta al cliente.
- La plantilla de aviso la crea el partner desde Canales con un texto que
  la consola propone; Meta la revisa como cualquier plantilla de utilidad.
- En Flor y Encanto el número es de coexistencia: la app del teléfono verá
  también los avisos que salen a los revisores. Se acepta.
