# Especificación: Correos con oficio

**Rama**: `051-correos-con-oficio` · **Creada**: 2026-10-30 · **Estado**: Borrador

**Entrada**: descripción del usuario: «Vamos a trabajar en la mejora de los mails, vamos a crear templates para el envío de los correos para que sean profesionales. Además debemos apagar el envío de los correos en staging y que sean solo logs. Asegúrate de que los emails tengan títulos descriptivos, descripciones bien redactadas, call to action no ambiguos y con el branding de Auphere, todo eso como redactado por humano y que no parezca hecho por IA.»

Decisiones del owner del 2026-10-30, recogidas en la nota de KB: plantillas **alojadas en Resend**; en staging el log guarda **metadatos y enlaces de acción**; respuestas a soporte; firma **«El equipo de Auphere»**.

**Tercera revisión del owner, el mismo día**: las alertas de **monitorización** dejan de enviarse por correo, porque se va a monitorizar con Datadog. Son las seis del vigilante de la plataforma y la conciliación diaria con Meta. Siguen escribiéndose en el registro, como `platform_alert` con nivel de error, para que Datadog las recoja. Las dos alertas internas que piden trabajo a una persona (la consulta de soporte de un partner y la petición de borrado de cuenta) siguen saliendo por correo.

**Segunda revisión del owner, el mismo día**: en staging llegan de verdad **solo los correos de acceso**, los que hacen falta para seguir operando (confirmar el alta, «ya tienes cuenta», invitación al equipo, invitación de cliente, restablecer la contraseña y aviso de contraseña cambiada). Todo lo demás —recibos, cobros, alertas de saldo y consumo, avisos y alertas internas— queda en el registro.

**Revisión del owner del mismo día**, sobre el primer borrador:

- los alias de las plantillas empiezan por `auphere-`;
- cada correo sale en el idioma de la cuenta de quien lo recibe, cuando se sabe;
- las direcciones de Auphere van en inglés (`notifications@`, `billing@`, `support@`) y `contacto@` sigue como está;
- ningún correo lleva la línea «por qué lo recibes»;
- se quita «se dan de baja tus máquinas», que no se entendía;
- el texto tiene que leerse como escrito por un profesional para un usuario común, no por una máquina.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API y el worker, que ya envían correo por Resend. No se abre ninguna superficie nueva: Resend ya es proveedor, y las plantillas viven en la misma cuenta que hoy envía |
| **Garantías de aislamiento tocadas** | **6**: el registro de cada correo, enviado o retenido, lleva el negocio (partner o cliente) al que pertenece cuando lo tiene. **1, solo rozada**: el destinatario y los datos de cada correo se siguen resolviendo donde hoy, desde el contexto del servidor; esta spec cambia la forma del correo, no a quién va ni con qué datos |
| **Nota de KB que la justifica** | `[[research/2026-10-30-correos-con-oficio]]` · `[[../brand/voice-and-copy]]` · `[[../brand/brand-system]]` |
| **Qué se mide** | Nada de modelo. Cada correo cuesta lo mismo en Resend que hoy; staging deja de gastar cuota. Ningún correo gasta saldo de partner |

## Origen

Medido el 2026-10-30 contra `develop` (`c99aed95`) y la cuenta de Resend:

- **Staging escribe a personas reales.** Su secreto lleva la clave de Resend, así que un alta, una invitación o un aviso de saldo probados en staging llegan a buzones de verdad, desde el dominio de producción.
- **Cada correo se escribe a mano donde se envía.** Hay **21 correos** repartidos por la API, el worker y un script, y cada uno lleva su propio HTML. Ninguno tiene logo ni firma común. Los estilos son sueltos, con tipografía y grises genéricos. En varios correos la única llamada a la acción es un enlace desnudo.
- **Hay correos que no funcionan.** La invitación al equipo no lleva enlace: solo una ruta relativa dentro de `<code>`. La del script de alta de pilotos es relativa salvo que se pase un parámetro.
- **Uno vuelca datos internos.** Los avisos de la consola al partner llegan como `[Auphere] model.retirement (warning)`, con una lista `clave: valor` del contenido del aviso.
- **El tono cambia de un correo a otro.** Unos usan «vosotros», otros «tú» y otros el «te dieron» de una sola variante. Las alertas de plataforma llevan el prefijo `[Nexus]`; el resto, `[Auphere]` o nada. El correo de la bandeja y el de escalado tienen el mismo asunto y pueden llegar por la misma conversación.
- **Siete valores van sin escapar**, entre ellos la referencia de cliente que escribe el partner.
- **Nadie lee las respuestas.** El alta y la contraseña salen de `no-reply@`. El resto sale de `facturacion@` porque es el remitente por defecto, aunque no haya nada que facturar. Solo un correo lleva `reply_to`, y tres piden «responde a este correo» sin que nadie de soporte lo vaya a leer.

El inventario completo, con el texto actual de cada correo y su sustituto, está en `contracts/catalogo.md`.

## Clarificaciones

### Sesión 2026-10-30

- P: ¿Dónde viven las plantillas? → R: Alojadas en Resend, editables en su panel; el código envía alias y variables.
- P: Con el envío apagado en staging, ¿qué queda en el registro? → R: Metadatos (plantilla, destinatario, asunto) y los enlaces de acción. Producción no puede arrancar en ese modo.
- P: ¿A qué buzón van las respuestas? → R: Al de soporte. Con la revisión del mismo día, en inglés: support@auphere.com.
- P: ¿En qué idioma sale cada correo? → R: En el de la cuenta de quien lo recibe, si se sabe; si no, en español.
- P: ¿Cómo se llaman las direcciones? → R: En inglés: notifications@, billing@ y support@. contacto@ no cambia.
- P: ¿Quién firma? → R: «El equipo de Auphere».

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Staging solo escribe lo que hace falta para operar (Prioridad: P1)

Alguien del equipo prueba en staging un alta, una invitación o un restablecimiento de contraseña, y el correo le llega: sin él no puede seguir. Lo demás —un recibo, una alerta de saldo, un aviso de consola, una alerta interna— no sale: queda en los registros de staging con su plantilla, destinatario, asunto y enlaces. Son los correos automáticos, los que escribirían a alguien sin que nadie los pida.

**Por qué esta prioridad**: hoy staging puede escribir a clientes reales desde el dominio de producción. Es el riesgo más alto y el cambio más pequeño.

**Prueba independiente**: con el despliegue en staging, pedir un restablecimiento de contraseña y una invitación de equipo: los dos llegan al buzón. Forzar una alerta de saldo: Resend no registra ese envío y el registro tiene su `email.suppressed`.

**Escenarios de aceptación**:

1. **Dado** el entorno de staging, **cuando** la plataforma va a enviar un correo de acceso, **entonces** lo envía.
2. **Dado** el entorno de staging, **cuando** la plataforma va a enviar cualquier otro correo, **entonces** no llama al proveedor y deja una entrada de registro con la plantilla, el destinatario, el asunto y los enlaces de acción, y quien lo pidió recibe el mismo resultado que si hubiera salido.
3. **Dado** producción, **cuando** alguien configura por error el modo de solo registro, **entonces** la API y el worker se niegan a arrancar y dicen por qué.
4. **Dado** staging, **cuando** el equipo quiere probar una plantilla de verdad, **entonces** puede activar el envío real de forma explícita, y el arranque deja escrito que staging está enviando.

---

### Historia 2 — Cada correo se reconoce como de Auphere y se entiende de un vistazo (Prioridad: P1)

Una dueña de agencia recibe una invitación, un recibo o un aviso de saldo. Por el asunto sabe de qué va antes de abrirlo. Al abrirlo ve el logo de Auphere y entiende qué ha pasado, qué tiene que hacer y qué pasa si no hace nada. Hay un solo botón, y su texto dice exactamente qué pasa al pulsarlo. El correo lo firma el equipo de Auphere y suena a una persona, no a una máquina.

**Por qué esta prioridad**: el correo es, muchas veces, lo primero que un partner ve de Auphere. Hoy no transmite ni marca ni oficio.

**Prueba independiente**: enviar cada plantilla publicada a la dirección de pruebas de Resend y revisar el resultado contra la guía de redacción (`contracts/redaccion.md`) y la de marca. La comprobación automática de plantillas (Historia 4) pasa en verde.

**Escenarios de aceptación**:

1. **Dado** cualquier correo del catálogo, **cuando** llega, **entonces** su asunto nombra la acción o el hecho concreto (qué y de quién) y no es genérico («Notificación», «Aviso», «Información importante»).
2. **Dado** un correo que pide hacer algo, **cuando** se abre, **entonces** tiene **una** llamada a la acción principal, con un verbo y su objeto («Aceptar la invitación», «Restablecer la contraseña»), y debajo el enlace en texto para quien no pueda pulsar el botón.
3. **Dado** un correo que solo informa, **cuando** se abre, **entonces** no inventa un botón: o no lleva ninguno, o lleva uno que lleva al detalle de lo que cuenta.
4. **Dado** cualquier correo, **cuando** se abre, **entonces** lleva el logo de Auphere, los colores de la marca, el saludo «Hola,», la firma «El equipo de Auphere» y un pie mínimo, sin línea de «por qué lo recibes».
6. **Dado** un destinatario con cuenta en inglés, **cuando** recibe cualquier correo externo, **entonces** le llega en inglés; **dado** uno sin cuenta conocida, **entonces** le llega en español.
5. **Dado** un cliente de correo que bloquea imágenes, **cuando** se abre el correo, **entonces** se entiende igual: el logo tiene texto alternativo y nada importante va dentro de una imagen.

---

### Historia 3 — Responder un correo llega a alguien (Prioridad: P2)

Un partner responde a un recibo para preguntar por un cargo, o a un aviso de saldo para pedir ayuda. Su respuesta llega a support@auphere.com, donde alguien la lee.

**Por qué esta prioridad**: un correo que firma «el equipo» y no admite respuesta contradice su propio tono.

**Prueba independiente**: inspeccionar las cabeceras de cada plantilla enviada a la dirección de pruebas: todas llevan `reply_to` a support@auphere.com y ninguna sale de una dirección «no-reply».

**Escenarios de aceptación**:

1. **Dado** cualquier correo del catálogo, **cuando** se envía, **entonces** la dirección de respuesta es support@auphere.com.
2. **Dado** un recibo o un aviso de cobro, **cuando** se envía, **entonces** sale de la dirección de facturación; **dado** cualquier otro correo, **entonces** sale de una dirección de notificaciones que no dice «no responder».

---

### Historia 4 — El texto se cambia en Resend sin romper el envío (Prioridad: P2)

Luis ajusta en el panel de Resend la redacción de una plantilla y la publica. El siguiente correo de ese tipo sale con el texto nuevo sin desplegar nada. Si alguien borra una variable que el código envía, despublica una plantilla o le cambia el alias, el equipo se entera antes de que un partner deje de recibir correos.

**Por qué esta prioridad**: alojar el texto fuera del repositorio fue una decisión consciente; esta historia es su red de seguridad.

**Prueba independiente**: ejecutar la comprobación de plantillas contra la cuenta de Resend. Con todo publicado y en orden, pasa. Al quitar una variable de una plantilla de prueba, falla y nombra la plantilla y la variable.

**Escenarios de aceptación**:

1. **Dado** el catálogo de correos del código, **cuando** se ejecuta la comprobación, **entonces** verifica que cada plantilla existe, está publicada, declara exactamente las variables que el código envía y respeta las reglas de redacción comprobables.
2. **Dado** un envío que Resend rechaza (plantilla inexistente, sin publicar o con una variable de menos), **cuando** ocurre, **entonces** el registro de error nombra el tipo de correo y la plantilla, y el trabajo que produjo el correo no se deshace.

---

### Historia 5 — Lo que ya protegía un correo sigue protegido (Prioridad: P1)

Las reglas que specs anteriores escribieron sobre el contenido de ciertos correos sobreviven al cambio de plantilla. El aviso de «tu contraseña ha cambiado» sigue sin un solo enlace. Un correo de alta no delata si la dirección ya tenía cuenta. Un nombre de negocio con caracteres raros no rompe el correo ni inyecta nada en él.

**Por qué esta prioridad**: cambiar la forma no puede reabrir una puerta que ya se cerró.

**Prueba independiente**: las pruebas de las specs 006 y 011 sobre estos correos siguen en verde, adaptadas al envío por plantilla, y la prueba de escapado envía un nombre con marcas HTML.

**Escenarios de aceptación**:

1. **Dado** el aviso de contraseña cambiada, **cuando** se compone, **entonces** no lleva ningún enlace salvo la dirección de contacto de seguridad como `mailto:`, ni siquiera en el logo o el pie.
2. **Dado** un valor que viene de un usuario (nombre de negocio, nombre de persona, texto de una consulta de soporte), **cuando** viaja a la plantilla, **entonces** llega escapado y se ve como texto.
3. **Dado** los dos correos del alta (cuenta nueva y cuenta existente), **cuando** se envían, **entonces** salen del mismo remitente con la misma estructura.
4. **Dado** un correo que hoy respeta el idioma de la persona (`es` o `en`), **cuando** se envía, **entonces** sigue llegando en su idioma.

---

### Casos límite

- **Una lista de longitud variable** (las líneas de un recibo, varios clientes en una alerta de consumo): las plantillas no admiten bucles. El correo resume (total, número de elementos, el más relevante) y enlaza al detalle en la consola.
- **Un valor que supera el tope de Resend** (2 000 caracteres por variable, como el texto libre de una consulta de soporte): se recorta con una marca visible de que sigue, y el texto completo se consulta donde vive.
- **Resend caído o lento**: el comportamiento de hoy se mantiene. El envío nunca lanza, devuelve que no salió y lo deja en el registro.
- **Un correo sin negocio** (alta, alertas internas de operador): el registro lo dice explícitamente en vez de dejar el campo vacío sin explicación.
- **Un destinatario múltiple** (avisos a todos los dueños de un partner): una sola entrada de registro con todos los destinatarios, como hoy.
- **Correos para el equipo de Auphere** (alertas de plataforma, conciliación de Meta): usan la misma marca en una variante sobria, interna, con la misma regla de un asunto que diga qué pasa.

## Requisitos *(obligatorio)*

### Requisito 1 — Modo de entrega por entorno

**Historia:** como equipo de Auphere, quiero que staging no escriba a nadie y que producción no pueda dejar de escribir, para que una prueba nunca llegue a un cliente y un error de configuración nunca deje a un partner sin correo.

1.1 CUANDO el entorno es staging y no hay otra orden explícita, ENTONCES el sistema DEBE enviar los correos de acceso (confirmar el alta, «ya tienes cuenta», invitación al equipo, invitación de cliente, restablecer la contraseña y aviso de contraseña cambiada) y DEBE retener todos los demás; CUANDO el entorno es local o CI, ENTONCES DEBE retenerlos todos. Retener es no llamar al proveedor y dejar una entrada de registro por correo con el tipo de correo, la plantilla, los destinatarios, el asunto y los enlaces de acción.

1.2 CUANDO un correo queda retenido en el registro, ENTONCES el sistema DEBE devolver a quien lo pidió el mismo resultado que un envío correcto.

1.3 CUANDO el entorno es producción y el modo configurado retiene algún correo (solo registro, o solo acceso), ENTONCES la API y el worker DEBEN negarse a arrancar con un mensaje que nombre la variable.

1.4 CUANDO staging se configura de forma explícita para enviarlo todo, ENTONCES el sistema DEBE enviar por el proveedor y DEBE dejar escrito en el arranque, como aviso, que staging envía todo el correo real. CUANDO se configura para no enviar nada, ENTONCES DEBE retenerlo todo.

1.5 CUANDO el modo es de envío real, ENTONCES el registro de cada correo NO DEBE incluir los enlaces de acción.

1.6 CUANDO un correo pertenece a un partner o a un cliente, ENTONCES su entrada de registro, retenida o enviada, DEBE llevar ese negocio como atributo; CUANDO no pertenece a ninguno, ENTONCES DEBE decirlo con un valor explícito.

### Requisito 2 — Un catálogo cerrado de correos

**Historia:** como equipo de Auphere, quiero que cada correo sea un tipo con nombre, para saber qué envía la plataforma y no volver a tener HTML escrito a mano en el sitio que envía.

2.1 El sistema DEBE enviar todo correo a través de un catálogo cerrado en el que cada tipo declara su plantilla en Resend, su remitente, sus variables y si lleva enlaces de acción.

2.2 CUANDO un sitio del código envía un correo, ENTONCES DEBE hacerlo por un tipo del catálogo; ningún sitio DEBE componer ni enviar HTML propio.

2.3 CUANDO se envía un tipo del catálogo, ENTONCES el sistema DEBE comprobar antes de llamar al proveedor que lleva todas sus variables, y SI falta alguna, ENTONCES DEBE no enviar y DEBE registrar el error con el tipo y la variable.

2.4 El catálogo DEBE cubrir todos los correos del inventario de `contracts/catalogo.md`.

2.5 CUANDO una familia de correos comparte forma y su texto ya existe en la consola (los avisos al partner y al cliente, las alertas internas), ENTONCES PUEDE usar una plantilla genérica cuyo texto por tipo vive en el código; CUANDO un tipo de esa familia que puede salir por correo no tiene texto propio, ENTONCES el sistema DEBE enviar el texto genérico y DEBE dejarlo en el registro.

2.6 Todo enlace de acción DEBE ser absoluto, construido desde la dirección pública de la consola del entorno.

### Requisito 3 — La marca de Auphere en cada correo

**Historia:** como partner, quiero reconocer de un vistazo que el correo es de Auphere, para fiarme de él.

3.1 Cada plantilla DEBE llevar el logo de Auphere servido como imagen PNG por HTTPS, con texto alternativo «Auphere», y sin enlace en los correos de seguridad.

3.2 Cada plantilla DEBE usar la paleta de marca: fondo hueso, texto tinta, llamada a la acción verde Caribe con texto negro, acentos verde Bangladesh, radios de 4 px en botones, sin gradientes, sombras ni brillos.

3.3 Cada plantilla DEBE abrir con «Hola,» y cerrar con la firma «El equipo de Auphere» y un pie con el enlace a auphere.com, salvo donde un requisito previo prohíba enlaces. NO DEBE llevar una línea de «por qué recibes este correo».

3.4 Cada plantilla DEBE entenderse con las imágenes bloqueadas y DEBE leerse en un móvil de 360 px sin desplazamiento horizontal.

3.5 Cada plantilla DEBE incluir un texto de previsualización que complete el asunto en vez de repetirlo.

### Requisito 4 — Redacción humana y sin ambigüedad

**Historia:** como persona que recibe el correo, quiero entender qué pasó y qué tengo que hacer en la primera frase, escrito como lo escribiría alguien del equipo.

4.1 El asunto de cada tipo DEBE nombrar el hecho o la acción concreta, DEBE caber en 60 caracteres sin contar el nombre de negocio y NO DEBE usar palabras genéricas («Notificación», «Aviso», «Información», «Actualización») como núcleo.

4.2 La primera frase de cada correo DEBE decir qué ha pasado; la segunda, qué tiene que hacer la persona o, si no tiene que hacer nada, decirlo.

4.3 CUANDO un correo pide una acción, ENTONCES DEBE tener exactamente una llamada a la acción principal, con un verbo en infinitivo y su objeto, y DEBE repetir el enlace en texto debajo.

4.4 Cada correo DEBE tutear, DEBE seguir la guía de voz de Auphere y NO DEBE contener las palabras de la lista negra de marca ni las muletillas de `contracts/redaccion.md`.

4.5 Cada correo que caduca o tiene un plazo DEBE decir el plazo con la fecha o la duración concreta.

### Requisito 5 — Remitentes y respuestas

5.1 Todo correo DEBE llevar support@auphere.com como dirección de respuesta, salvo la petición interna de borrado de cuenta, que DEBE seguir respondiendo a la persona que la pidió.

5.2 Los recibos y avisos de cobro DEBEN salir de la dirección de facturación; el resto DEBE salir de una dirección de notificaciones, y ninguno DEBE salir de una dirección «no-reply».

5.3 Los dos correos del alta DEBEN salir del mismo remitente.

### Requisito 6 — Lo que ya protegían los correos

6.1 El aviso de contraseña cambiada NO DEBE contener ningún enlace salvo el `mailto:` del contacto de seguridad (spec 011, R4.3).

6.2 CUANDO un valor de una variable procede de un usuario, ENTONCES el sistema DEBE escaparlo antes de enviarlo a la plantilla.

6.3 CUANDO un valor supera el tope de longitud de Resend, ENTONCES el sistema DEBE recortarlo con una marca visible y NO DEBE fallar el envío.

6.4 CUANDO se conoce el idioma de la cuenta del destinatario, ENTONCES todo correo externo DEBE salir en ese idioma, con una plantilla en español y otra en inglés; CUANDO no se conoce, ENTONCES DEBE salir en español. Un correo a varias personas DEBE salir una vez por idioma. Las alertas internas van solo en español.

### Requisito 7 — Plantillas comprobables

7.1 El repositorio DEBE incluir una comprobación que, contra la cuenta de Resend, verifique por cada tipo del catálogo que su plantilla existe, está publicada, declara exactamente sus variables, lleva la firma y cumple las reglas comprobables de redacción (lista negra, una sola llamada a la acción, sin enlaces donde están prohibidos).

7.2 CUANDO Resend rechaza un envío, ENTONCES el registro de error DEBE nombrar el tipo de correo, la plantilla y el estado devuelto.

### Requisito 9 — La monitorización no va por correo

**Historia:** como equipo de Auphere, quiero que la salud de la plataforma se vigile en una herramienta de monitorización y no en el buzón, para que una alerta repetida cada hora no entierre lo que sí hay que leer.

9.1 CUANDO el vigilante de la plataforma detecta un problema (cola atascada, mensajes en la DLQ, ráfaga de errores, servicio sin latido, caché degradada, fallos de envío a Meta), ENTONCES el sistema NO DEBE enviar correo y DEBE dejar un `platform_alert` de nivel error con su tipo, título y detalle.

9.2 CUANDO la conciliación diaria con Meta encuentra mensajes sin guardar, ENTONCES el sistema NO DEBE enviar correo y DEBE dejar en el registro, con nivel de error, el día y cada canal afectado.

9.3 La consulta de soporte y la petición de borrado de cuenta DEBEN seguir enviándose por correo.

### Requisito 8 — Documentación viva

8.1 Los documentos de `docs/` que describen el envío de correo (recuperar la contraseña, registro de partners, paso a producción) DEBEN describir el modo por entorno, el catálogo y cómo cambiar una plantilla, en el mismo cambio que el código.

### Entidades clave

- **Tipo de correo**: un correo que la plataforma sabe enviar. Tiene un nombre estable, una plantilla por idioma en Resend, un remitente, sus variables (con cuáles vienen de un usuario y cuáles son enlaces de acción) y a qué negocio pertenece.
- **Plantilla**: el cuerpo del correo alojado en Resend, publicado, con su asunto por defecto y sus variables.
- **Modo de entrega**: envío real o solo registro, decidido por entorno, con producción obligada al envío real.

## Criterios de éxito *(obligatorio)*

- **CE-001**: tras desplegar en staging, recorrer alta, invitación y restablecimiento hace llegar **los tres** correos; un aviso de saldo deja **cero** envíos nuevos en Resend y su entrada `email.suppressed` en el registro.
- **CE-002**: el **100 %** de los tipos del catálogo tienen plantilla publicada y la comprobación de plantillas pasa en verde.
- **CE-003**: **ningún** sitio del código compone HTML de correo; la prueba de barrido lo confirma.
- **CE-004**: en una lectura de cinco segundos de cada correo, una persona ajena al proyecto sabe decir qué pasó y qué tiene que hacer. Se registra en `evidence/`.
- **CE-005**: las pruebas existentes sobre el contenido de los correos de las specs 006 y 011 siguen en verde, adaptadas.

## Supuestos

- La cuenta de Resend es la misma para staging y producción; con staging en modo registro, las plantillas solo las usa producción, y staging cuando se active el envío explícito.
- Los correos en español usan el registro neutro de `voice-and-copy.md`; los ingleses se escriben en inglés, no se traducen palabra por palabra. El idioma de una cuenta es `console_auth.principals.locale`.
- El logo se sirve desde `https://www.auphere.com/brand/auphere-logo.png`, publicado por la web de Auphere.
- El tipo de letra de marca (Helvena) no está disponible en los clientes de correo: el tema de la plantilla cae a la familia sin serifa del sistema.
- support@auphere.com existe y alguien lo lee; si no existe aún, es configuración del owner y no bloquea el código.
- Con las plantillas alojadas fuera de git, el texto de los cuerpos no se versiona en el repositorio: el catálogo y la comprobación son la red de seguridad.

## Fuera de alcance

- Correos de marketing, boletines y difusiones.
- Notificaciones que no son correo (push, WhatsApp, avisos dentro de la consola).
- Seguimiento de aperturas o clics: se mantienen apagados.
- **Las alertas de monitorización por correo** (Requisito 9): se retiran, y su sustituto es Datadog, fuera de esta spec.
- **Correos que hoy no existen.** El impago de la membresía (`billing.payment_failed`, `billing.unpaid`, `billing.canceled`) no manda correo. Se encontró en el inventario y es otra conversación: añadirlo cambia lo que el producto hace, no cómo lo dice.
