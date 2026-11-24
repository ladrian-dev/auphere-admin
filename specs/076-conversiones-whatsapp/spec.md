# Especificación: Conversiones de anuncios de WhatsApp

**Rama**: `076-conversiones-whatsapp` · **Creada**: 2026-11-24 · **Estado**: En `develop` y en staging desde el 2026-11-24 (PR 56), nada en `main`. En staging solo la ofrece «Meta Review Demo». Faltan las tareas de Luis en Meta y en staging (T026 a medias, T044–T046). Quedan decisiones por revisar (ver Clarifications)

**Entrada**: descripción del usuario: «076 — Medir conversiones de anuncios de WhatsApp (ver propuesta https://claude.ai/artifact/483WL7vTJyKGzgj3jTsDBQ)». Antes, al decidir pedir el permiso a Meta: «si vamos a solicitar el permiso la idea es que lo usemos correctamente».

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API de la consola, el webhook de WhatsApp, el runtime del turno y el worker, que ya existen. No se abre ninguna superficie de agente. Sí se abre un **flujo de datos nuevo hacia Meta**: los resultados de clientes finales en el chat (una reserva, un pedido) salen a la API de conversiones de cada negocio. Van con el clic del anuncio o, si no lo hay, con el teléfono del cliente cifrado. El plan hace la lectura de RGPD de ese flujo. |
| **Garantías de aislamiento tocadas** | **1 (RLS)**: el origen de anuncio, el ajuste de medición, el conjunto de datos de Meta y la cola de eventos son del negocio y se leen y escriben bajo su `tenant_id`. El conjunto de datos al que va un evento sale de las credenciales del negocio, nunca de quien llama (requisito 6.5). **8 (cliente final dentro del tenant)**: el clic de un anuncio es de una persona; nunca puede atribuir la reserva de otro contacto ni mostrarse en su conversación (requisitos 1.6 y 6.6). **6 (logs)**, rozada: cada envío a Meta queda en el log con su `tenant_id`. |
| **Nota de KB que la justifica** | `[[research/2026-11-24-conversiones-whatsapp]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada nuevo.** Meta no cobra la API de conversiones y no hay llamadas nuevas al modelo. El origen del anuncio añade una línea al contexto del turno del agente, y ese gasto ya se mide en la bolsa del cliente. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 050, **requisito 7.2** y la parte de `referral` de la tarea **T042** | Guardar en la conversación el anuncio del que viene la persona y dárselo al agente como contexto. | Pasa a esta spec (requisito 1), que además guarda cada clic en el contacto para poder medir. T042 se queda con `button` y `contacts`. |
| Spec 050, **requisito 10.4** y «Fuera de alcance» | El envío a revisión de Meta no incluye `whatsapp_business_manage_events`; la API de conversiones queda fuera porque no hay caso de uso de anuncios. | Hay caso de uso: esta spec. El permiso se pide cuando el flujo funcione en staging (requisito 7). La API de mensajes de marketing sigue fuera. |

## Por qué

El 2026-11-24 el soporte de Meta recomendó pedir acceso avanzado a `whatsapp_business_manage_events`. Los tokens del inicio de sesión con la app WhatsApp Business lo incluyen, y la app solo tiene acceso estándar. El permiso sirve para una sola cosa: enviar a Meta los resultados que consigue un negocio en sus chats (una compra, un pedido, un cliente potencial), para que Meta los atribuya a sus anuncios y optimice las campañas.

Hoy Auphere no envía ninguno, y además pierde el dato que lo haría posible. Cuando alguien escribe desde un anuncio de clic a WhatsApp, Meta manda en el primer mensaje un identificador de ese clic. El adaptador lo lee, pero se descarta antes de guardarse. Así:

- **El negocio no sabe de qué anuncio viene cada cliente.** El agente tampoco.
- **Las campañas se miden por conversaciones iniciadas**, no por las reservas que el agente consigue en ellas.
- **Pedir el permiso sin usarlo es causa de rechazo.** La página de revisión de Meta dice que se pida «únicamente» si se usa. La descripción que quedó guardada en el borrador de revisión afirma un uso que no existe.

Meta aprueba este permiso automáticamente a las apps con acceso avanzado a `whatsapp_business_messaging`, que tenemos. La condición es tener un uso real que enseñar.

## Clarifications

### Session 2026-11-24

- Q: ¿Se construye la medición de conversiones? → A: Sí. Luis aprobó abrir la spec tras leer la propuesta.
- Q: Meta no tiene un evento de cita. ¿Qué se envía cuando el agente crea una reserva? → A: Una compra (`Purchase`) con el precio y la moneda, en cuanto el agente la crea. Si la reserva no tiene precio, se envía como cliente potencial (`LeadSubmitted`), sin importe.
- Q: ¿Se envían solo los resultados de conversaciones que vinieron de un anuncio? → A: No: todos los del chat. Los que no tienen clic de anuncio identifican al cliente con su teléfono cifrado, como pide Meta, y Meta intenta atribuirlos a anuncios de los últimos 7 días.
- Q: ¿Se envía algo de quien tiene una baja de marketing activa en ese número? → A: No, nada, ni con clic ni sin él (requisito 5.9).

**Correcciones al planificar (2026-11-24).** El plan leyó el código y cambió dos cosas de la spec:

- **La consola de partners no tiene Bandeja con la conversación.** La Bandeja con el hilo y la ficha del contacto es solo la de la consola lite, que usa el negocio. El partner ve listados sin contenido. Por eso el requisito 2 se queda en la consola lite, y el partner ve los anuncios en el informe (requisito 3).
- **Una persona con baja de marketing.** La spec decía que su baja no cambiaba nada. Con la decisión de enviar todos los resultados del chat, eso mandaría a Meta el teléfono cifrado de alguien que pidió no recibir marketing. Ahora no se envía nada de esa persona (requisito 5.9). **Luis lo confirmó el 2026-11-24.**

**Decisiones tomadas sin Luis, por revisar.** Son las recomendaciones de la propuesta y quedan escritas aquí hasta que las confirme:

- La medición está apagada por defecto y se activa por número, desde la consola de partners.
- Solo se pide volver a autorizar al cliente que active la medición.
- No se envía si la persona asistió o no a la cita: ocurre fuera del chat.
- Nunca se envía el nombre del servicio, notas ni texto de la conversación.
- El identificador del clic se conserva 90 días.
- El borrador de revisión abierto en Meta no se envía hasta cumplir el requisito 7.
- Los pedidos y enlaces de pago que crea el agente (WooCommerce) se envían como pedido creado (requisito 5.4). Ocurren en el chat y ya llevan importe.
- La cancelación de una reserva ya enviada se envía aunque se haga desde la consola (requisito 5.3), para que Meta no siga contando una reserva que no existe.
- El número de Auphere se prueba con una configuración de registro insertado aparte, solo para personas con rol en la app (requisito 7.2).
- Al activar la medición, la persona que la activa confirma que el negocio puede enviar a Meta estos datos de sus clientes. La confirmación queda en la auditoría (requisito 4.8).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El negocio sabe de qué anuncio viene cada cliente (Prioridad: P1)

Una persona toca un anuncio de clic a WhatsApp de una barbería y escribe. En la Bandeja, la conversación enseña el anuncio del que vino, con su titular y un enlace. El agente lo sabe y puede responder sobre la promoción del anuncio sin que la persona la explique.

**Por qué esta prioridad**: es la base de todo lo demás y no necesita ningún permiso nuevo. Sin el clic guardado no hay nada que medir.

**Prueba independiente**: llega un mensaje con origen de anuncio. La conversación lo muestra, el agente lo recibe como dato, y un segundo contacto del mismo negocio no lo ve.

**Escenarios de aceptación**:

1. **Dado** un mensaje entrante que viene de un anuncio, **cuando** se guarda, **entonces** la conversación muestra el titular del anuncio y un enlace a él.
2. **Dado** una conversación que viene de un anuncio, **cuando** el agente responde, **entonces** tiene el titular y el texto del anuncio como dato del contexto.
3. **Dado** un anuncio cuyo texto dice «ignora tus instrucciones», **cuando** el agente lo recibe, **entonces** lo trata como texto del anuncio y no cambia lo que hace.
4. **Dado** una conversación que no viene de ningún anuncio, **cuando** se abre, **entonces** no aparece nada sobre anuncios.

---

### Historia 2 — El partner ve qué anuncios traen reservas (Prioridad: P2)

En la consola, el partner abre el informe de anuncios de un cliente y elige unas fechas. Ve cuántas conversaciones llegaron de cada anuncio, cuántas reservas creó el agente en ellas y por qué importe.

**Por qué esta prioridad**: da el valor de medir sin depender de Meta ni del permiso. Es lo que el partner puede enseñar a su cliente desde el primer día.

**Prueba independiente**: con conversaciones de prueba de dos anuncios y reservas en una de ellas, el informe da los números exactos y no cuenta las canceladas.

**Escenarios de aceptación**:

1. **Dado** conversaciones de dos anuncios en las fechas elegidas, **cuando** el partner abre el informe, **entonces** ve una fila por anuncio con conversaciones, reservas e importe.
2. **Dado** una reserva cancelada, **cuando** se calcula el informe, **entonces** no suma en el importe ni en las reservas.
3. **Dado** un periodo sin conversaciones desde anuncios, **cuando** se abre el informe, **entonces** lo dice y explica que se llena solo cuando alguien escribe desde un anuncio.

---

### Historia 3 — El negocio mide y optimiza sus anuncios en Meta (Prioridad: P2)

El partner activa «Medir resultados de anuncios» en el número de un cliente. Si hace falta, el cliente vuelve a autorizar la conexión con Meta. Desde ese momento, cada reserva que el agente crea en el chat llega a Meta. Si la conversación vino de un anuncio, llega como resultado de ese anuncio; si no, Meta intenta atribuirla por el teléfono cifrado. El negocio lo ve en Events Manager, y Meta puede optimizar sus campañas por reservas.

**Por qué esta prioridad**: es el uso del permiso y lo que de verdad mejora las campañas. Depende de la historia 1 y del permiso de Meta.

**Prueba independiente**: en staging, con el número de Auphere, un clic de anuncio de prueba y una reserva del agente producen un evento visible en los eventos de prueba de Meta en menos de una hora, una sola vez.

**Escenarios de aceptación**:

1. **Dado** un número sin la autorización nueva, **cuando** el partner activa la medición, **entonces** la consola pide volver a conectar y no la activa hasta que se conecta.
2. **Dado** un número con la medición activa, **cuando** el agente crea una reserva en una conversación que vino de un anuncio, **entonces** Meta recibe un único evento de compra con el importe, la moneda y el clic del anuncio.
3. **Dado** un número con la medición activa, **cuando** el agente crea una reserva en una conversación que no vino de ningún anuncio, **entonces** Meta recibe un único evento de compra que identifica al cliente solo con su teléfono cifrado.
4. **Dado** esa reserva, **cuando** se cancela, **entonces** Meta recibe el evento de cancelación.
5. **Dado** una reserva creada desde la consola, **cuando** se guarda, **entonces** no se envía nada a Meta.
6. **Dado** un número con la medición apagada, **cuando** el agente crea una reserva, **entonces** no se envía nada a Meta.

---

### Historia 4 — Auphere pide el permiso con un uso real (Prioridad: P3)

Con la historia 3 funcionando en staging, el equipo graba el vídeo que pide Meta y envía la solicitud de acceso avanzado con una descripción que cuenta solo lo que la app hace.

**Por qué esta prioridad**: sin el permiso la historia 3 no llega a ningún cliente, pero no se puede pedir antes de tener la historia 3.

**Prueba independiente**: la solicitud enviada lleva el vídeo del flujo real, y Meta la aprueba.

**Escenarios de aceptación**:

1. **Dado** el flujo funcionando en staging, **cuando** se envía la solicitud, **entonces** el vídeo muestra el clic del anuncio, la conversación, la reserva y el evento en Meta.
2. **Dado** que Meta concede el acceso avanzado, **cuando** un cliente conecta un número, **entonces** el registro insertado le pide el permiso nuevo.

---

### Casos límite

- **Varios clics de anuncio del mismo contacto**: cuenta el más reciente anterior al resultado. Cada clic queda guardado con su fecha.
- **Un origen sin identificador de clic** (una publicación orgánica): se guarda y se muestra. Sus resultados salen a Meta como los de cualquier conversación sin clic, con el teléfono cifrado.
- **Un contacto sin teléfono** (alguien que escribe con nombre de usuario de WhatsApp): sin clic ni teléfono no hay con qué identificarlo ante Meta, y su resultado no se envía.
- **Una reserva creada más de 7 días después del clic**: el evento se envía igual, porque lleva el clic. Meta decide si la atribuye.
- **El negocio desactiva la medición con eventos en cola**: los que no salieron se descartan, no se envían más tarde.
- **Meta rechaza un evento**: se reintenta si el error es pasajero. Si no lo es, el error se ve en el estado del número y el evento no se reintenta para siempre.
- **El evento lleva más de 7 días en cola**: no se envía. Meta rechaza el lote entero si un evento es más viejo.
- **La reserva no tiene precio**: se envía como cliente potencial (`LeadSubmitted`), sin importe. Cuenta en el informe como reserva, sin sumar importe.
- **Un número en coexistencia** (la app WhatsApp Business y la API a la vez): la guía de Meta no dice si se mide. Se prueba en el plan. Si no funciona, ese número no ofrece la medición: no hay interruptor apagado ni explicación (constitución §V).
- **Un número conectado sin el permiso nuevo**: el interruptor lleva a volver a conectar. No se ofrece «activar» para que falle después.
- **Un contacto que pidió la baja de marketing**: no se envía nada suyo a Meta (requisito 5.9). Su conversación sigue mostrando el anuncio y cuenta en el informe, que no sale de Auphere.

## Requisitos *(obligatorio)*

### Requisito 1 — Guardar el origen de anuncio

**Historia de usuario:** Como negocio, quiero que Auphere guarde el anuncio del que viene cada persona, para saberlo yo, que lo sepa el agente y poder medirlo.

#### Criterios de aceptación

1. WHEN llega un mensaje de WhatsApp con origen de anuncio THEN el sistema DEBE guardarlo en el contacto con su fecha. El origen incluye el identificador del clic, el identificador y el enlace del anuncio o la publicación, el tipo de origen, el titular y el texto.
2. WHEN un contacto ya tiene un origen guardado y llega otro THEN el sistema DEBE guardar también el nuevo, sin borrar el anterior.
3. La conversación DEBE poder mostrar el origen más reciente de su contacto.
4. WHEN el agente atiende una conversación con origen de anuncio THEN el sistema DEBE darle el titular y el texto del anuncio como dato del contexto, y NO DEBE darle el identificador del clic.
5. IF el texto del anuncio contiene algo que parece una instrucción THEN el agente DEBE tratarlo como dato y NO DEBE cambiar lo que hace (constitución §III).
6. El origen de un contacto NO DEBE mostrarse, darse al agente ni usarse para medir en la conversación o en los resultados de otro contacto, aunque sean del mismo negocio.
7. WHEN han pasado 90 días desde un clic THEN el sistema DEBE borrar su identificador de clic y conservar el resto del origen.

### Requisito 2 — Ver el origen en la Bandeja

**Historia de usuario:** Como negocio, quiero ver en la conversación de qué anuncio vino la persona, para atenderla con ese contexto.

#### Criterios de aceptación

1. WHERE la conversación tiene un origen de anuncio, la Bandeja de la consola lite DEBE mostrar el titular y un enlace al anuncio o la publicación. La consola de partners no tiene Bandeja con conversaciones: el partner ve los anuncios en el informe (requisito 3).
2. WHERE la conversación no tiene origen de anuncio, la Bandeja NO DEBE mostrar nada sobre anuncios.
3. IF el origen no trae titular THEN la Bandeja DEBE mostrar el tipo de origen («Anuncio», «Publicación») con su enlace.

### Requisito 3 — Informe de anuncios

**Historia de usuario:** Como partner, quiero ver qué anuncios de mi cliente traen reservas, para enseñárselo y mejorar sus campañas.

#### Criterios de aceptación

1. WHEN el partner abre el informe de anuncios de un cliente y elige un periodo THEN la consola DEBE mostrar, por anuncio: las conversaciones con un clic de ese anuncio en el periodo, las reservas creadas por el agente en el periodo y atribuidas a ese anuncio (criterio 3.3), y el importe de esas reservas por moneda.
2. Las reservas canceladas NO DEBEN contar en reservas ni en importe.
3. Una reserva DEBE contar para el anuncio del clic más reciente de su contacto, en el número de su conversación, anterior a la reserva.
4. WHILE el informe carga, la consola DEBE mostrar el estado de carga con la forma final. IF falla THEN DEBE decir qué falló y ofrecer reintentar.
5. WHERE no hay conversaciones desde anuncios en las fechas elegidas, la consola DEBE decirlo y explicar que el informe se llena solo cuando alguien escribe desde un anuncio.
6. El informe DEBE mostrar solo datos del propio cliente.

### Requisito 4 — Activar la medición en Meta por número

**Historia de usuario:** Como partner, quiero activar la medición en el número de mi cliente, para que sus resultados lleguen a sus anuncios de Meta.

#### Criterios de aceptación

1. La medición DEBE estar apagada en todos los números hasta que un partner la active.
2. WHEN el partner activa la medición en un número THEN el sistema DEBE asegurar que existe el conjunto de datos de Meta de esa cuenta de WhatsApp y guardarlo con las credenciales del número.
3. IF la autorización del número no incluye el permiso de eventos THEN la consola DEBE pedir volver a conectar el número, y NO DEBE activar la medición hasta que la autorización lo incluya.
4. WHEN el partner desactiva la medición THEN el sistema DEBE dejar de enviar desde ese momento y descartar lo que esté en cola.
5. WHEN se activa o se desactiva THEN la auditoría DEBE nombrar a la persona que lo hizo y cuándo.
6. WHERE la medición está activa, la página del número DEBE mostrar su estado: conjunto de datos vinculado, eventos enviados en los últimos 7 días y, si lo hay, el último error con qué hacer.
7. IF el número no admite la medición THEN la página del número NO DEBE mostrar el interruptor ni explicar su ausencia (constitución §V).
8. WHEN el partner activa la medición THEN la consola DEBE decir qué se envía a Meta (el tipo de resultado, el importe y el clic del anuncio o el teléfono cifrado) y pedir que confirme que el negocio puede enviarlo. La auditoría DEBE guardar esa confirmación.

### Requisito 5 — Qué resultados se envían

**Historia de usuario:** Como negocio, quiero que Meta reciba solo los resultados que consigue el agente en el chat, para que mis campañas se optimicen por lo que de verdad importa.

#### Criterios de aceptación

1. WHEN el agente crea una reserva en una conversación de un número con la medición activa THEN el sistema DEBE enviar a Meta un evento de compra (`Purchase`) con el importe y la moneda de la reserva.
2. IF la reserva no tiene precio THEN el sistema DEBE enviar un evento de cliente potencial (`LeadSubmitted`) sin importe, y NO DEBE enviar una compra.
3. WHEN se cancela una reserva cuyo evento ya se envió THEN el sistema DEBE enviar un evento de cancelación (`OrderCanceled`), la cancele quien la cancele. Es la única excepción al criterio 5.5: corrige un resultado del chat que Meta ya contó.
4. WHEN el agente crea un pedido o un enlace de pago en una conversación de un número con la medición activa THEN el sistema DEBE enviar un evento de pedido creado (`OrderCreated`) con su importe y moneda.
5. Las reservas y los pedidos creados fuera del chat NO DEBEN enviarse: los de la consola, la app, la llegada sin reserva y los de la web.
6. La asistencia, la ausencia y el pago fuera del chat NO DEBEN enviarse.
7. Los resultados del chat DEBEN enviarse vengan o no de un anuncio. WHERE el contacto tiene un clic de anuncio en el mismo número anterior al resultado, el evento DEBE llevar el más reciente. WHERE no lo tiene, el evento DEBE identificar al contacto con su teléfono cifrado, como pide Meta.
8. IF el contacto no tiene clic de anuncio ni teléfono THEN el sistema NO DEBE enviar el resultado.
9. IF el contacto pidió la baja de marketing THEN el sistema NO DEBE enviar a Meta ningún resultado suyo, tenga clic o no.

### Requisito 6 — Cómo se envían

**Historia de usuario:** Como responsable de la plataforma, quiero que el envío a Meta sea fiable, mínimo y aislado, para no perder resultados, no duplicarlos y no mandar a Meta más de lo necesario.

#### Criterios de aceptación

1. WHEN ocurre un resultado que se envía THEN el sistema DEBE enviarlo a Meta en menos de una hora.
2. Un mismo resultado DEBE llegar a Meta una sola vez, aunque el envío se reintente.
3. IF Meta devuelve un error pasajero THEN el sistema DEBE reintentar. IF el error no es pasajero, o el evento cumple 7 días sin salir, THEN el sistema DEBE dejar de intentarlo y mostrar el error en el estado del número.
4. Cada evento DEBE llevar solo el tipo de resultado, la hora, el importe, la moneda, la identificación de la cuenta y del número de WhatsApp, y una de estas dos cosas: el identificador del clic o el teléfono del contacto cifrado como pide Meta. NO DEBE llevar el nombre del servicio, notas, el nombre de la persona, el teléfono sin cifrar ni texto de la conversación.
5. El conjunto de datos al que va un evento DEBE salir de las credenciales del negocio dueño del resultado. NO DEBE venir de quien llama ni de otro negocio.
6. El identificador de clic o el teléfono que lleva un evento DEBEN ser del mismo contacto que el resultado.
7. Cada envío DEBE quedar en el log con el negocio, el número, el tipo de evento y el resultado. NO DEBEN quedar el identificador del clic ni el teléfono, cifrado o no.

### Requisito 7 — El permiso en Meta

**Historia de usuario:** Como responsable de la integración, quiero pedir el permiso de eventos con un uso real, para que Meta lo apruebe y los clientes puedan concederlo.

#### Criterios de aceptación

1. Antes de pedir el acceso avanzado, el flujo de la historia 3 DEBE funcionar en staging con el número de Auphere: un clic de anuncio de prueba, una reserva del agente y el evento visible en los eventos de prueba de Meta.
2. Para el criterio 7.1 y el vídeo, el número de Auphere DEBE autorizarse con una configuración de registro insertado de pruebas que pida el permiso. Solo la usan personas con rol en la app, que con acceso estándar sí pueden concederlo. Esa configuración NO DEBE ofrecerse a ningún cliente.
3. La solicitud DEBE llevar una descripción que cuente solo el uso de esta spec y un vídeo con el inicio de sesión, la autorización con el permiso, la conversación desde el anuncio, la reserva y el evento en Meta.
4. WHILE la app no tenga acceso avanzado al permiso, las configuraciones del registro insertado que usan los clientes NO DEBEN pedirlo.
5. WHEN Meta concede el acceso avanzado THEN el registro insertado DEBE pedir el permiso en las altas nuevas y en las reconexiones.
6. Antes de activar la medición en un cliente que no sea Auphere, la app DEBE tener el nivel de acceso completo a la API de marketing que pide Meta.

### Entidades clave

- **Origen de anuncio**: un clic de anuncio o de publicación de un contacto. Guarda el identificador del clic (borrado a los 90 días), el anuncio, el enlace, el tipo, el titular, el texto y la fecha. Es del negocio (`tenant_id`, RLS) y de un contacto.
- **Medición del número**: si el número envía resultados a Meta, quién la activó y cuándo, y el conjunto de datos de Meta vinculado. Es del negocio (`tenant_id`, RLS) y de un número.
- **Evento de conversión**: un resultado que hay que enviar. Guarda de qué reserva o pedido sale, el tipo, la hora, el importe, la moneda, el clic que lo atribuye, el estado del envío (pendiente, enviado, fallido, descartado), los intentos y el último error. Es del negocio (`tenant_id`, RLS).

## Criterios de éxito *(obligatorio)*

- **CE-001**: el 100 % de las conversaciones de prueba que llegan desde un anuncio muestran su anuncio en la Bandeja de la consola lite.
- **CE-002**: una reserva hecha por el agente en una conversación desde un anuncio aparece en los eventos de Meta en menos de una hora.
- **CE-003**: cero eventos enviados al conjunto de datos de otro negocio, y cero clics atribuidos a otro contacto, en la batería de aislamiento.
- **CE-004**: cero resultados duplicados en Meta en una batería con reintentos forzados.
- **CE-005**: el importe del informe de anuncios coincide al céntimo con las reservas no canceladas del agente del periodo atribuidas a anuncios.
- **CE-006**: un partner activa la medición de un número en menos de 3 minutos, reconexión incluida.
- **CE-007**: Meta aprueba el acceso avanzado al primer envío.

## Fuera de alcance

- **La API de mensajes de marketing**: tiene plazo propio (13 de abril de 2027 para las cuentas nuevas) y va en una spec aparte.
- **Instagram y Messenger**: la misma API los acepta, pero sus permisos no se han estudiado.
- **Pedidos del catálogo** (el mensaje `order` de WhatsApp): hoy se convierten en texto y no se guardan. Guardarlos es trabajo aparte.
- **Clientes potenciales sin reserva**: no hay una definición de lead en el producto.
- **Mostrar en Auphere el gasto o el coste por reserva de Meta**: pediría `ads_read` y leer las cuentas publicitarias.
- **La app móvil**: la Bandeja de la app se pone al día en su sesión.
- **Reservas de Quédate**: la API del agente de Quédate no tiene reservas.
- **Mensajes de bienvenida de los anuncios**: son otra función de Meta.

## Supuestos

- Hay partners cuyos clientes hacen anuncios de clic a WhatsApp. No tenemos el dato de cuántos.
- Meta aprueba el permiso automáticamente con el acceso avanzado a `whatsapp_business_messaging`, como dice su página de revisión.
- El token del registro insertado de cada cliente sirve para enviar sus eventos, como recomienda Meta, si incluye el permiso.
- Los tokens emitidos hasta hoy no incluyen el permiso, porque las configuraciones del registro insertado no lo piden. Se confirma con `debug_token` en el plan.
- Con el acceso actual, el envío funciona en staging con el número de Auphere porque somos usuarios con rol en la app. La primera llamada lo confirma.
- Meta no cobra la API de conversiones.
- La vía del teléfono cifrado solo atribuye anuncios vistos en los últimos 7 días, y solo en «un subconjunto de países» que Meta no enumera. Donde no esté disponible, Meta acepta el evento y no lo atribuye.
- Noventa días bastan para atribuir una reserva a su clic. Si Meta documenta otra ventana, el plan la ajusta.
