# Especificación: clientes de solo envío, códigos por WhatsApp y membresía que corta

**Rama**: `077-otp-con-membresia` · **Creada**: 2026-11-24 · **Estado**: Implementada (2026-11-24), pendiente de staging

**Entrada**: Luis, 2026-11-24: «Tengo un cliente que se llama Tecfin que necesito configurarlo y darlo de alta en Auphere, pero este cliente no va a tener un agente activo sino que utilizará un endpoint que le vamos a proveer con unos tokens de acceso para que utilicen Auphere solo para enviar mensajes OTP. El cliente New Air tiene una configuración similar. Adicionalmente este cliente debe tener asociada una membresía de 40 dólares mensuales y si la membresía no está activa no se deben enviar los mensajes». Después: «Asegúrate que este feature no vaya a romper nada y que todo se pueda administrar desde la UI sin romper lo que existe ni quede como puesto obligado sino que sea parte del flujo». Y: «actualmente se le puede cobrar de la bolsa del partner o directamente, así que debe mantenerse esa opción».

Diseño aprobado del flujo: artifact «Alta de Tecfin» (https://claude.ai/artifact/DXef1YXCUCPyrAsN7jMtY6).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API, el panel de operador, la consola, el webhook de Stripe y el worker, que ya existen. Se abre una **página pública sin datos** («Pago recibido»), a la que vuelve quien paga en Stripe: no lee ni escribe nada. |
| **Garantías de aislamiento tocadas** | **1 (RLS)**: la membresía de un cliente es suya y se lee y escribe bajo su `tenant_id`; un aviso de Stripe solo cambia la membresía cuya suscripción nombra; el cargo a la bolsa se escribe bajo el `partner_id` del partner del cliente; una clave de envío solo actúa sobre su cliente, también tras rotarla (`tests/isolation/test_77…`). **6 (logs)**: ningún log lleva un código de un solo uso ni un dato de tarjeta. Y la constitución §IV: emitir, rotar y revocar claves, activar, cancelar y cambiar una membresía y marcar un cliente como de solo envío nombran al operador. |
| **Nota de KB que la justifica** | `[[clients/tecfin]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada nuevo.** No hay llamadas a modelos. Los mensajes de Meta los paga el cliente en su propia cuenta de WhatsApp Business. El cargo mensual a la bolsa del partner se anota en el libro como gasto del partner, con su propia clave, y se concilia con lo demás. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| `apps/api/src/nexus_api/billing/__init__.py` y `docs/billing.md` | La única resta del sistema es `debit_wallet` en el camino del turno. | Hay una segunda, el **cargo fijo mensual** a la bolsa del partner, siempre desde el worker y nunca por un aviso externo (la regla de spec 005 R3.4 sigue igual). |
| Plantillas de «Autenticación» (panel y consola) | Se crean con texto libre, como cualquier otra. Meta las rechaza. | Se crean con el formato de Meta: texto fijo, botón de copiar código, caducidad y aviso de seguridad. |
| `POST /v1/messages/template` | Solo plantillas con variables con nombre. | También plantillas de autenticación, con el código en un campo propio. Lo demás no cambia. |

## Por qué

El 2026-11-24 se revisó producción (`main` = `fd28e552`). La forma «solo envío» de New Air existe, pero un cliente como Tecfin no se puede dar de alta con lo que hay:

- **No se puede enviar un código.** Las plantillas de autenticación de Meta tienen el texto fijo con `{{1}}` y un botón de copiar código, y el código va dos veces en el envío. El endpoint solo acepta variables con nombre y no manda el botón: hoy respondería 422.
- **No existe una membresía que corte.** El plan de un cliente solo pinta una línea en el recibo de un partner. Stripe solo trabaja con partners. Pausar un cliente tampoco para los envíos de la API.
- **Nada se administra desde el panel.** La clave de envío de un cliente solo la emite un script, que además da instrucciones de Railway. Rotarla desde la ficha del partner la rompe: la clave nueva pierde el cliente.
- **El alta deja un número de relleno.** Al conectar el número real queda un segundo número activo, y la API rechaza los envíos hasta que alguien asigna un papel.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Dar de alta un cliente de solo envío desde el panel (Prioridad: P1) 🎯 MVP

Un operador de Auphere da de alta a Tecfin en el Admin como cliente «Solo envío por API», le manda el enlace para que conecte su número, crea la plantilla de código, le emite una clave y le pasa el enlace de pago. Su ficha le dice en todo momento qué falta.

**Por qué esta prioridad**: sin esto, Tecfin no existe. Todo lo demás supone que el cliente está dado de alta y conectado.

**Prueba independiente**: un operador crea el cliente, conecta un número de prueba por el enlace, crea una plantilla de autenticación y emite una clave, sin tocar un script ni la base de datos.

**Escenarios de aceptación**:

1. **Dado** el asistente de alta, **cuando** el operador elige «Solo envío por API», **entonces** el cliente nace sin agente, marcado como de solo envío, y su ficha abre con «Puesta en marcha».
2. **Dado** un cliente de solo envío, **cuando** conecta su número por el enlace, **entonces** el número queda activo y sin agente que responda.
3. **Dado** un cliente de solo envío, **cuando** el operador abre su ficha, **entonces** no ve Agente, Habilidades, Playground ni Canal del dueño, y sí ve «Envío por API».
4. **Dado** New Air (sin la marca), **cuando** el operador abre su ficha, **entonces** la ve igual que hoy.

---

### Historia 2 — Enviar un código por WhatsApp desde su sistema (Prioridad: P1)

El sistema de Tecfin llama a la API con su clave, el teléfono, el nombre de su plantilla de autenticación y el código. El cliente final recibe el mensaje con el botón de copiar código.

**Por qué esta prioridad**: es el servicio que Tecfin contrata.

**Prueba independiente**: una llamada con una plantilla de autenticación aprobada deja un mensaje en cola que sale con el código en el cuerpo y en el botón.

**Escenarios de aceptación**:

1. **Dado** una plantilla de autenticación aprobada, **cuando** el sistema envía el código, **entonces** la API responde 202 y el mensaje sale con el código en el cuerpo y en el botón.
2. **Dado** una plantilla de autenticación, **cuando** falta el código o trae variables, **entonces** la API responde 422 y dice qué corregir.
3. **Dado** un envío de New Air con variables con nombre, **cuando** llega, **entonces** se comporta exactamente como hoy.

---

### Historia 3 — Cobrar la membresía y cortar al impago (Prioridad: P1)

El operador configura la membresía de Tecfin (40 USD al mes) con cobro al cliente por Stripe. Tecfin paga por un enlace. Mientras la membresía no esté activa, la API rechaza sus envíos y lo que estuviera en cola no sale. Si un cobro falla, se corta al momento.

**Por qué esta prioridad**: es la condición del servicio que puso Luis.

**Prueba independiente**: con la membresía pendiente, la API responde 402; al pagar, responde 202; al fallar un cobro, vuelve a responder 402 y la cola se marca fallida.

**Escenarios de aceptación**:

1. **Dado** una membresía pendiente de pago, **cuando** el sistema envía un código, **entonces** la API responde 402 `membership_inactive` y no queda nada en cola.
2. **Dado** el enlace de pago, **cuando** Tecfin paga, **entonces** la membresía pasa a activa sin que nadie de Auphere intervenga y los envíos salen.
3. **Dado** una membresía activa, **cuando** Stripe no puede cobrar la renovación, **entonces** la membresía pasa a impagada y los envíos se cortan en ese momento.
4. **Dado** un mensaje en cola, **cuando** la membresía deja de estar activa antes de que salga, **entonces** se marca fallido y no sale nunca, aunque la membresía vuelva.

---

### Historia 4 — Cobrar la membresía de la bolsa del partner (Prioridad: P2)

Un cliente de un partner puede tener la misma membresía, pero la paga su partner: cada mes se descuenta de la bolsa del partner. Si el partner no tiene saldo (ni línea de crédito), la membresía queda impagada y los envíos se cortan hasta que haya saldo.

**Por qué esta prioridad**: Luis pidió las dos formas de cobro y quiere reutilizar este cargo para un consumo mínimo mensual por agente.

**Prueba independiente**: un cliente de partner con membresía a la bolsa se activa al descontarse el importe; sin saldo queda impagado; al recargar, se cobra y se reactiva solo.

**Escenarios de aceptación**:

1. **Dado** un cliente de partner, **cuando** el operador activa la membresía con cargo a la bolsa y hay saldo, **entonces** se descuenta el importe una vez y la membresía queda activa un mes.
2. **Dado** una bolsa sin saldo suficiente, **cuando** toca cobrar, **entonces** no se descuenta nada, la membresía queda impagada y se reintenta hasta que haya saldo.
3. **Dado** un cargo ya hecho este periodo, **cuando** el proceso se repite, **entonces** no se descuenta dos veces.

---

### Historia 5 — Ver cobros y últimos envíos (Prioridad: P2)

En Facturación el operador ve los cobros de la membresía. En «Envío por API» ve los últimos envíos del cliente con su estado.

**Prueba independiente**: tras un cobro y tres envíos, las dos listas los muestran con su estado real.

### Casos límite

- **Enlace de pago caducado** (Stripe lo caduca a las 24 h): el panel lo dice y deja crear otro.
- **Aviso de Stripe perdido**: el panel deja actualizar el estado desde Stripe, y un proceso periódico vuelve a leer las membresías cuyo periodo venció.
- **Un cliente sin partner** no puede tener la membresía con cargo a la bolsa: el panel no ofrece esa opción.
- **Cambiar el importe** con una suscripción de Stripe en curso no está permitido: se cancela y se crea un enlace nuevo. Con cargo a la bolsa, el importe nuevo se aplica al periodo siguiente.
- **Cancelar la membresía** corta los envíos al momento y no se cobra nada más.
- **Dos números activos sin papel** en un cliente de solo envío: el número que entra por el enlace queda como línea de avisos. Si hay dos líneas de avisos, la llamada elige con `channel_id`, como hoy.
- **«Bolsa del partner»** en esta spec es el saldo del partner (su cuenta), no la bolsa de cada cliente de la spec 047. En pantalla se dice «Del saldo del partner».
- **Plantilla de autenticación en una difusión**: se rechaza como hoy (las difusiones solo admiten variables con nombre).
- **Código con espacios, más de 15 caracteres o con un enlace**: 422 antes de encolar.
- **El cliente se dio de baja de los mensajes** (opt-out total): 409 como hoy. Un opt-out solo de marketing no bloquea un código.
- **La ausencia se diseña**: sin membresía configurada no aparece ni el paso ni la etiqueta; un cliente sin partner no ve la opción de bolsa; un cliente sin claves ve cómo crear la primera.

## Requisitos *(obligatorio)*

### Requisito 1 — Cliente de solo envío

**Historia de usuario:** Como operador de Auphere, quiero dar de alta un cliente sin agente que solo envía por API, para atender a Tecfin y a New Air desde el panel.

#### Criterios de aceptación

1. WHEN el operador crea un cliente eligiendo «Solo envío por API» THEN el sistema DEBE crearlo marcado como de solo envío y sin agente.
2. El sistema DEBE guardar la marca de solo envío como un dato explícito del cliente, apagado por defecto, de modo que todo cliente existente siga como hoy.
3. WHERE un cliente está marcado como de solo envío EL panel DEBE ocultar Agente, Habilidades, Playground y Canal del dueño, mostrar «Envío por API» y no mostrar avisos de agente sin publicar.
4. WHERE un cliente está marcado como de solo envío EL panel DEBE mostrar en su Resumen la puesta en marcha propia: número conectado, plantilla de autenticación aprobada, membresía activa (solo si tiene membresía) y al menos una clave activa, cada paso con su estado real y su acción.
5. WHEN el operador marca o desmarca un cliente existente como de solo envío THEN el sistema DEBE pedir confirmación y dejarlo en la auditoría con el nombre del operador.
6. IF el cliente no está marcado THEN el panel NO DEBE cambiar nada de lo que muestra hoy.

### Requisito 2 — Su número, conectado por el propio cliente

**Historia de usuario:** Como operador, quiero mandar a Tecfin un enlace para que conecte su número con su cuenta de Meta, para que sus mensajes los pague él.

#### Criterios de aceptación

1. WHEN un cliente de solo envío conecta un número por el enlace de conexión THEN el sistema DEBE dejar ese número activo, sin agente que responda y como línea de avisos.
2. WHEN un cliente de solo envío conecta un número THEN el panel DEBE dar la conexión por terminada sin pasos de asignar un agente.
3. El alta desde el panel NO DEBE crear números de relleno.
4. WHEN alguien escribe al número de un cliente de solo envío THEN el sistema DEBE guardar el mensaje sin abrir «Espera a una persona» ni avisar a nadie.

### Requisito 3 — Plantillas de autenticación

**Historia de usuario:** Como operador o partner, quiero crear una plantilla de código desde el diálogo de plantillas de hoy, para que Meta la apruebe.

#### Criterios de aceptación

1. WHEN se elige la categoría Autenticación en el diálogo de plantillas THEN el formulario DEBE pedir el texto del botón de copiar código, la caducidad en minutos (1 a 90) y si lleva aviso de seguridad, en lugar del texto del mensaje, y mostrar el texto fijo de Meta.
2. WHEN se envía una plantilla de autenticación a Meta THEN el sistema DEBE construirla con el formato de autenticación de Meta (cuerpo con aviso de seguridad, pie con caducidad, botón de código de un solo uso de tipo copiar).
3. WHERE la categoría es Marketing o Utilidad EL formulario y lo que se envía a Meta DEBEN quedar exactamente como hoy.
4. El sistema DEBE ofrecer lo mismo en el panel de operador y en la consola de partners.

### Requisito 4 — Enviar un código por la API

**Historia de usuario:** Como sistema de Tecfin, quiero enviar un código con una llamada, para que mi usuario lo reciba por WhatsApp.

#### Criterios de aceptación

1. WHEN una llamada a `POST /v1/messages/template` nombra una plantilla de autenticación aprobada y trae `code` THEN el sistema DEBE encolar el mensaje con el código en el cuerpo y en el botón de la plantilla y responder 202.
2. IF la plantilla es de autenticación y falta `code`, o trae `variables` THEN el sistema DEBE responder 422 diciendo qué corregir, sin encolar nada.
3. IF trae `code` y la plantilla no es de autenticación THEN el sistema DEBE responder 422.
4. IF el código está vacío, tiene más de 15 caracteres, espacios o un enlace THEN el sistema DEBE responder 422.
5. IF la llamada no trae `code` y la plantilla no es de autenticación THEN el sistema DEBE comportarse exactamente como hoy.
6. El sistema NO DEBE escribir el código en ningún log, y DEBE borrarlo del mensaje guardado en cuanto el envío termina (enviado o fallido).
7. WHEN la misma `idempotency_key` llega dos veces THEN el sistema DEBE responder como hoy (duplicado), también con códigos.
8. IF un código lleva más de 10 minutos en cola THEN el despachador NO DEBE enviarlo: lo marca fallido con `code_expired` y lo borra (revisión de seguridad, 2026-11-24).
9. IF el cliente no está activo (pausado o suspendido) y el despachador no lo visita THEN el sistema DEBE, igualmente, marcar fallidos con `code_expired` y borrar los códigos que lleven más de 10 minutos en cola. _(Revisión `/cso`, 2026-11-24.)_

### Requisito 5 — Claves de acceso del cliente desde el panel

**Historia de usuario:** Como operador, quiero emitir, rotar y revocar la clave de un cliente desde su ficha, para no depender de un script.

#### Criterios de aceptación

1. WHEN el operador abre «Envío por API» THEN el panel DEBE listar las claves de ese cliente, con su prefijo, quién y cuándo la creó, su último uso y su estado, incluidas las que ya existían (la de New Air).
2. WHEN el operador crea una clave THEN el sistema DEBE emitirla ligada a ese cliente, con permiso solo de envío, y mostrarla completa una sola vez.
3. WHEN se rota una clave ligada a un cliente THEN la clave nueva DEBE quedar ligada al mismo cliente, se rote desde la ficha del cliente o desde la del partner.
4. WHEN el operador rota o revoca una clave THEN el sistema DEBE pedir confirmación y dejarlo en la auditoría con su nombre.
5. IF el cliente no tiene partner THEN su clave DEBE colgar del partner contenedor de clientes directos de Auphere.
6. El panel DEBE mostrar cómo llama su sistema: la dirección, la cabecera y un ejemplo de petición y de respuesta, también la 402.
7. La consola de partners NO DEBE listar, rotar ni revocar claves ligadas a un cliente: las gestiona el operador desde el panel, de modo que ningún miembro de un partner obtiene el secreto de una clave de envío de un cliente. _(Revisión `/cso`, 2026-11-24.)_
8. WHEN el operador rota una clave desde la ficha del cliente THEN la nueva DEBE colgar del partner actual del cliente: si el cliente cambió de partner, su clave lo sigue.

### Requisito 6 — Membresía: configuración y formas de cobro

**Historia de usuario:** Como operador, quiero exigir a un cliente una membresía mensual y elegir quién la paga, sin cambiar los cobros que ya existen.

#### Criterios de aceptación

1. El sistema DEBE conservar sin cambios los cobros de hoy (recibo del partner y directo con pagos anotados a mano) y su pantalla de Facturación.
2. WHEN el operador configura una membresía THEN el sistema DEBE guardar su importe mensual en USD (40 por defecto) y quién la paga: el cliente por Stripe, o el partner de su bolsa.
3. IF el cliente no tiene partner THEN el sistema NO DEBE permitir el cobro a la bolsa.
4. WHEN el operador cambia el importe THEN el sistema DEBE aplicarlo al periodo siguiente si el cobro es a la bolsa, y rechazarlo con una suscripción de Stripe en curso.
5. WHEN el operador cancela la membresía THEN el sistema DEBE pedir confirmación, dejar de cobrar y cortar los envíos al momento.
6. Cada cambio de la membresía hecho por un operador DEBE quedar en la auditoría con su nombre.
7. WHERE un cliente no tiene membresía EL sistema NO DEBE cortar ninguno de sus envíos por este motivo.
8. WHEN el operador quita la membresía de un cliente THEN el sistema DEBE archivarla (nunca borrarla) y solo si no está activa ni tiene una suscripción viva.

### Requisito 7 — Membresía cobrada al cliente por Stripe

**Historia de usuario:** Como operador, quiero un enlace de pago para el cliente y ver su estado sin entrar en Stripe.

#### Criterios de aceptación

1. WHEN el operador pide el enlace de pago THEN el sistema DEBE crear una sesión de pago de Stripe de suscripción mensual por el importe de la membresía, a nombre de un cliente de Stripe propio de ese cliente (nunca el de su partner), y devolver el enlace con su caducidad.
2. WHEN Stripe confirma el pago o la suscripción queda al corriente THEN la membresía DEBE pasar a activa con su fin de periodo.
3. WHEN Stripe no puede cobrar (primer cobro fallido de una renovación) THEN la membresía DEBE pasar a impagada en ese momento.
4. WHEN Stripe cancela la suscripción THEN la membresía DEBE pasar a cancelada.
5. El sistema DEBE aplicar un aviso de Stripe solo a la membresía cuya suscripción o sesión nombra, y NO DEBE leer el cliente del cuerpo del aviso sin comprobarlo contra Stripe.
6. Un aviso de membresía NO DEBE tocar el saldo de ningún partner ni la escalera de membresías de partners.
7. WHEN el operador pulsa «Actualizar» THEN el sistema DEBE leer la suscripción en Stripe y corregir el estado.
8. El sistema DEBE volver a leer de Stripe, como mucho cada hora, las membresías por Stripe pendientes con un enlace emitido, las impagadas y las activas cuyo periodo haya vencido o que no se lean desde hace 24 horas.
9. WHEN el cliente vuelve de Stripe THEN el sistema DEBE mostrarle una página pública de «Pago recibido» (o de «Pago no completado») que no lee ni muestra datos.
10. El panel DEBE listar los cobros de la membresía leídos de Stripe, con periodo, importe, estado y enlace a la factura.
11. WHILE una suscripción de Stripe está impagada el enlace de pago DEBE ser el de su factura pendiente, y el sistema NO DEBE abrir una segunda suscripción para el mismo cliente.
12. WHEN el cliente ya tiene una suscripción guardada THEN un aviso sobre otra suscripción del mismo cliente de Stripe NO DEBE cambiar su membresía, salvo que venga de su enlace de pago vigente.
13. WHEN el operador cambia el importe o quién paga, quita o cancela una membresía con un enlace de pago abierto THEN el sistema DEBE caducar ese enlace en Stripe antes de guardar el cambio; IF Stripe no responde THEN NO DEBE guardar nada y DEBE responder 503. _(Revisión `/cso`, 2026-11-24.)_
14. WHEN el operador pide un enlace nuevo y el anterior ya se pagó sin que llegara el aviso THEN el sistema NO DEBE abrir otro: DEBE aplicar ese pago y decirlo (409 `checkout_already_paid`).

### Requisito 8 — Membresía cobrada a la bolsa del partner

**Historia de usuario:** Como operador, quiero que el partner pague la membresía de su cliente con su saldo, y que el mismo mecanismo sirva después para otros cargos fijos mensuales.

#### Criterios de aceptación

1. WHEN se activa una membresía con cargo a la bolsa THEN el sistema DEBE descontar el importe del saldo comprado del partner (dentro de su línea de crédito si la tiene) y dejarla activa hasta el mismo día del mes siguiente.
2. IF el saldo, sumada la línea de crédito, no cubre el importe THEN el sistema NO DEBE descontar nada y DEBE dejar la membresía impagada.
3. WHILE una membresía a la bolsa está impagada el sistema DEBE reintentar el cargo periódicamente y reactivarla en cuanto se cobre.
4. El sistema DEBE cobrar cada periodo una sola vez, aunque el proceso se repita o corra dos veces a la vez.
5. El cargo DEBE quedar en el libro del partner atribuido a ese cliente, como un tipo de asiento propio que no cuenta como consumo de conversaciones ni como gasto de un agente, y conciliado con el saldo.
6. El cargo NO DEBE descontarse del tope del cliente.
7. El mecanismo DEBE servir para cualquier cargo fijo mensual con su motivo (la membresía es el primero), sin cambiarlo para añadir otro.
8. El panel DEBE listar los cargos de la membresía hechos a la bolsa.
9. IF una renovación intentada antes del vencimiento no se puede cobrar THEN la membresía DEBE seguir activa hasta el fin del periodo pagado y pasar a impagada solo al vencer.

### Requisito 9 — Sin membresía activa no sale nada

**Historia de usuario:** Como Auphere, quiero que un cliente con membresía exigida no envíe nada si no está activa.

#### Criterios de aceptación

1. WHILE la membresía de un cliente no está activa la API DEBE responder 402 `membership_inactive` a sus envíos directos y a sus difusiones, sin encolar nada.
2. WHEN el despachador va a enviar una plantilla de un cliente cuya membresía no está activa THEN DEBE marcarla fallida con `membership_inactive` y no enviarla.
3. Una membresía cuenta como activa solo cuando su estado es activo y, si se cobra a la bolsa, su periodo no ha vencido.
4. La puerta NO DEBE afectar a las respuestas de un agente ni a clientes sin membresía.
5. La puerta NO DEBE llamar a Stripe: lee el estado guardado.

### Requisito 10 — Últimos envíos

**Historia de usuario:** Como operador, quiero ver los últimos envíos de plantillas del cliente con su estado.

#### Criterios de aceptación

1. WHEN el operador abre «Envío por API» THEN el panel DEBE listar los últimos 50 envíos de plantillas del cliente con la hora, el destinatario enmascarado, la plantilla y el estado (y el motivo si falló).
2. El panel NO DEBE mostrar nunca un código ni un teléfono completo.

### Requisito 11 — No romper lo que existe

#### Criterios de aceptación

1. Los envíos de New Air DEBEN seguir funcionando sin cambiar su petición ni su respuesta.
2. Las difusiones, los cobros de partners (recarga, tarjeta, pospago, recibos) y las membresías de partners DEBEN seguir igual.
3. La clave que New Air ya tiene DEBE seguir funcionando y aparecer en su ficha.
4. Una conciliación de saldo DEBE seguir cuadrando con los cargos fijos dentro.

### Requisito 12 — Documentación viva

#### Criterios de aceptación

1. El sistema DEBE tener un documento vivo del envío directo por API (clientes de solo envío, códigos, claves, membresía y su puerta) en `docs/`, y `docs/billing.md` DEBE explicar la membresía y el cargo fijo mensual.
2. El script de alta a mano DEBE dejar de ser el camino de alta y decirlo, sin instrucciones de Railway.

### Entidades clave

- **Membresía de un cliente**: importe mensual en USD, quién paga (Stripe o bolsa del partner), estado (pendiente, activa, impagada, cancelada), fin del periodo, identificadores de Stripe (cliente y suscripción), correo de facturación, última lectura de Stripe. **Es del cliente**: la alcanza la RLS por su `tenant_id`.
- **Cargo fijo mensual a la bolsa**: un asiento del libro del partner con motivo, cliente y periodo en su clave única. **Es del partner**: la alcanza la RLS por su `partner_id`.
- **Marca de solo envío**: un dato del cliente.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Un operador da de alta a Tecfin y lo deja enviando códigos sin usar un script ni tocar la base de datos.
- **CE-002**: Con la membresía sin pagar no sale ningún mensaje de Tecfin; tras pagar, el primer envío sale sin intervención de Auphere.
- **CE-003**: Un cobro fallido corta los envíos en el mismo minuto en que Stripe lo avisa.
- **CE-004**: New Air y el resto de clientes no notan ningún cambio.
- **CE-005**: Un cargo a la bolsa nunca se cobra dos veces el mismo periodo, y la conciliación del partner sigue cuadrando.

## Fuera de alcance

- **Consumo mínimo mensual por agente**: es la siguiente regla que usará el cargo fijo; aquí solo se construye el mecanismo.
- **La consola de partners para clientes de solo envío**: sigue como hoy (salvo el formulario de plantillas de autenticación). Un partner con un cliente de solo envío lo ve como cualquier cliente.
- **Impuestos y cuenta de Stripe**: el cobro real depende de la cuenta que ya usa la consola y del tratamiento fiscal (`docs/billing.md`). Es configuración, no código.
- **Plantillas de autenticación de un toque o sin toque**: solo copiar código.
- **Marcar New Air como de solo envío**: lo decide un operador desde el panel cuando quiera.

## Supuestos

- La cuenta de Stripe es la que ya usa la consola (decisión de Luis). Su webhook de producción debe recibir `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid` e `invoice.payment_failed`.
- Las sesiones de pago de Stripe caducan a las 24 horas.
- La membresía corta lo que inicia el negocio (envíos por API y difusiones); un cliente de solo envío no tiene más.

## Clarifications

### Session 2026-11-24

- Q: ¿El número es de Tecfin o de Auphere? → A: **De Tecfin**: lo conecta él con su Embedded Signup y paga sus mensajes a Meta.
- Q: ¿Cómo se cobran los 40 USD? → A: **Por Stripe**, con la cuenta que ya usa la consola.
- Q: ¿Qué pasa sin membresía activa? → A: **No se envía el mensaje.**
- Q: ¿Los 40 USD incluyen Meta? → A: **No**, son solo lo de Auphere.
- Q: ¿Cuándo se corta un impago? → A: **Al primer cobro fallido.**
- Q: ¿Cobros y últimos envíos ahora o después? → A: **Ahora**, nada queda pendiente.
- Q: ¿Se puede cobrar de la bolsa del partner? → A: **Sí, las dos formas**; el cargo mensual se reutilizará para un consumo mínimo por agente.
- Q: ¿Se pueden romper los cobros de hoy? → A: **No**: recibo del partner y directo a mano siguen igual.
