# Especificación: WhatsApp al día (Meta 2026)

**Rama**: trabajo en `develop` (decisión del owner) · **Creada**: 2026-10-29 · **Estado**: Borrador

**Entrada**: descripción del usuario: «Arma un spec para dejar up to date la configuración de WhatsApp para incluir los eventos pendientes, actualizar las formas de conexión e inicio de sesión, etc. Esto es nuestro principal fuerte así que debe estar bien construido y actualizado.» Base: [whatsapp-antes-de-la-revision.md](../049-meta-instagram-messenger/whatsapp-antes-de-la-revision.md), revisión de la documentación oficial de Meta y del código de `develop` hecha el 2026-10-29.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: API de la consola y webhook de la plataforma, la misma superficie que WhatsApp ya tiene abierta |
| **Garantías de aislamiento tocadas** | **1**: el negocio de cada evento sale del canal registrado; los eventos de cuenta se atribuyen por la cuenta de WhatsApp Business, nunca por el contenido. **4**: el hilo de una persona no se parte ni se mezcla al cambiar de teléfono a identificador de Meta. **6**: logs y trazas etiquetados con negocio y canal. **8**: la persona la identifica la plataforma, nunca un argumento del modelo; dos personas distintas nunca se funden en una |
| **Nota de KB que la justifica** | `[[whatsapp-connector/decisions/ADR-027-meta-tech-provider-direct]]` · `[[whatsapp-connector/02-embedded-signup]]` · `[[whatsapp-connector/04-webhooks]]` · `[[whatsapp-connector/13-meta-canales-investigacion-2026-10]]` |
| **Qué se mide** | Nada nuevo de modelo. Lo que Meta cobra por mensaje se **registra y se enseña**, no se cobra: Auphere es Tech Provider sin línea de crédito y Meta factura directamente al negocio (`01-meta-tech-provider.md`) |

## Origen

WhatsApp es el canal con el que Auphere vende y atiende. Medido el 2026-10-29 contra la documentación oficial de Meta y el código:

- **Se descartan eventos que Meta ya nos envía.** Hay 14 campos suscritos y solo 6 tienen tratamiento. Los demás se registran como «campo no tratado» y se tiran: bajas de marketing, calidad y categoría de plantillas, alertas y revisión de cuenta, límites, nombre visible. De cada lote solo se procesa el primer mensaje, el primer estado y el primer eco.
- **Personas que pueden quedar sin respuesta.** Desde 2026 una persona puede escribir con nombre de usuario y sin número visible (identificador de Meta, BSUID). Hoy ese mensaje se descarta en silencio. Meta exige a todos los partners soportarlo.
- **Conexión con fecha de caducidad.** El registro integrado usa parámetros de la versión 3, que Meta dejó de servir el 2026-10-15. Una opción del registro (compartir solo la cuenta) deja de funcionar el 2026-11-16. Las llamadas del servidor van fijas en una versión de la API de 2025.
- **Precio 2026.** Desde el 2026-10-01 Meta cobra los mensajes de servicio por encima de 1000 por número al mes y los de utilidad dentro de la ventana. No guardamos si un mensaje se cobra ni cuánto.
- **Huecos funcionales.**
  - Una pulsación en un botón de plantilla llega como «no soportado».
  - El anuncio del que viene un cliente se pierde.
  - Las plantillas de autenticación no se pueden crear, porque falta el botón de copiar código.
  - La ubicación sale como texto.
  - El perfil del negocio no se puede editar.
  - El PIN de dos pasos se genera y se pierde.
- **Revisión de Meta.** `catalog_management` y `business_management` esperan envío, y sus guías oficiales piden demostrar usos que la consola no tiene todavía.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Nadie se queda sin respuesta (Prioridad: P1)

Una persona escribe al negocio con su nombre de usuario de WhatsApp, sin número visible, o manda tres mensajes seguidos que Meta entrega juntos. El agente la atiende igual que a cualquiera y en la bandeja aparece una sola conversación con todos sus mensajes.

**Por qué esta prioridad**: hoy esos mensajes se pierden sin que nadie lo sepa. Es la promesa básica del producto.

**Prueba independiente**: con un número de prueba, enviar un mensaje desde una cuenta con nombre de usuario y un lote de varios mensajes. El agente responde a todos y ninguno queda fuera de la bandeja.

**Escenarios de aceptación**:

1. **Dado** una persona que escribe solo con su identificador de Meta, **cuando** llega el mensaje, **entonces** el agente responde y la conversación aparece en la bandeja.
2. **Dado** una persona que antes escribía con su número y ahora llega con identificador de Meta y número, **cuando** escribe, **entonces** sigue en la misma conversación, con su historial.
3. **Dado** un lote con varios mensajes, estados o ecos, **cuando** llega, **entonces** se procesan todos, cada uno una vez.
4. **Dado** dos personas distintas, **cuando** escriben, **entonces** nunca acaban en la misma conversación aunque una de ellas no tenga número.

---

### Historia 2 — Conectar un número sigue funcionando después de noviembre (Prioridad: P1)

Un partner conecta el WhatsApp de un cliente por cualquiera de las vías que existen: Cloud API, coexistencia con la app, el enlace que abre el dueño en su teléfono y la vía beta de inicio de sesión con WhatsApp. Funciona con la versión vigente del registro de Meta, también después del 2026-11-16.

**Por qué esta prioridad**: sin conexión no hay clientes nuevos, y la fecha de Meta es fija.

**Prueba independiente**: conectar un número por cada vía en staging, con la configuración nueva, y verificar que el número queda activo, suscrito y atendiendo.

**Escenarios de aceptación**:

1. **Dado** cada vía de conexión, **cuando** el partner o el dueño la completa, **entonces** el número queda activo y el agente responde.
2. **Dado** el registro de Meta, **cuando** se abre, **entonces** usa la versión vigente y ningún parámetro retirado.
3. **Dado** un número conectado por Cloud API, **cuando** termina el alta, **entonces** su PIN de dos pasos queda guardado y cifrado, y el operador puede rotarlo.
4. **Dado** un alta que Meta rechaza o que la persona cancela, **cuando** vuelve a la consola, **entonces** ve qué pasó y cómo seguir, sin canal a medias.

---

### Historia 3 — La cuenta avisa antes de romperse (Prioridad: P1)

Meta baja la calidad de una plantilla, la pausa o la recategoriza, alerta de un límite de mensajería, cambia el estado de revisión de la cuenta o rechaza el nombre visible. El partner lo ve en la consola en el momento, con qué significa y qué hacer, y el agente deja de usar lo que ya no puede usar.

**Por qué esta prioridad**: hoy el partner se entera cuando un envío falla. Es la diferencia entre gestionar la cuenta y apagar fuegos.

**Prueba independiente**: inyectar cada evento de Meta en staging y ver el aviso en la consola, el estado nuevo de la plantilla o del número y la entrada en la auditoría.

**Escenarios de aceptación**:

1. **Dado** una plantilla pausada, rechazada o deshabilitada, **cuando** llega el evento, **entonces** el agente no la ofrece y el partner ve el motivo.
2. **Dado** una plantilla recategorizada, **cuando** llega el evento, **entonces** su categoría y su precio esperado se actualizan y el partner lo ve.
3. **Dado** una alerta o restricción de la cuenta, **cuando** llega, **entonces** el canal muestra el problema con su motivo y queda en la auditoría.
4. **Dado** un evento de la cuenta que no trae número (solo la cuenta de WhatsApp Business), **cuando** llega, **entonces** se atribuye a todos los números de esa cuenta del mismo negocio.

---

### Historia 4 — Una baja de marketing se respeta siempre (Prioridad: P1)

Una persona se da de baja de mensajes de marketing desde WhatsApp, o escribe «baja». Ninguna campaña, recordatorio de marketing ni plantilla de marketing le vuelve a llegar hasta que ella misma lo reactive. Los mensajes de servicio y utilidad siguen funcionando.

**Por qué esta prioridad**: es una obligación con la persona y con Meta, y hoy la señal oficial de Meta se descarta.

**Prueba independiente**: darse de baja desde la app de WhatsApp de prueba e intentar una campaña: no sale, y la consola dice por qué.

**Escenarios de aceptación**:

1. **Dado** una baja de marketing de Meta, **cuando** llega, **entonces** se registra y bloquea los envíos de marketing a esa persona en ese número.
2. **Dado** una reactivación de Meta, **cuando** llega, **entonces** la baja se levanta y queda constancia.
3. **Dado** una baja por palabra clave, **cuando** la persona vuelve a escribir pidiendo mensajes, **entonces** el operador puede levantarla con su registro.
4. **Dado** una persona dada de baja de marketing, **cuando** se le envía una plantilla de utilidad o un mensaje de servicio, **entonces** sí sale.

---

### Historia 5 — Plantillas y mensajes completos (Prioridad: P2)

El partner crea plantillas con imagen, vídeo o documento en la cabecera, de autenticación con botón de copiar código y en carrusel. El agente envía ubicaciones nativas, pide la ubicación, muestra que está escribiendo, entiende cuándo alguien pulsa un botón de una plantilla y sabe de qué anuncio viene un cliente.

**Por qué esta prioridad**: amplía lo que los clientes pueden hacer. Va después de que nada se pierda.

**Prueba independiente**: crear una plantilla de cada tipo en staging y que Meta la apruebe. Pulsar un botón de plantilla y ver la respuesta del agente. Pedir la ubicación y recibirla.

**Escenarios de aceptación**:

1. **Dado** una plantilla con cabecera multimedia, de autenticación o en carrusel, **cuando** el partner la crea, **entonces** Meta la recibe con su formato correcto y su estado aparece en la consola.
2. **Dado** una persona que pulsa un botón de respuesta rápida de una plantilla, **cuando** llega, **entonces** el agente recibe qué botón pulsó y responde.
3. **Dado** una persona que llega desde un anuncio de clic a WhatsApp, **cuando** escribe, **entonces** la conversación guarda el anuncio y el agente lo tiene como contexto.
4. **Dado** que el agente está preparando la respuesta, **cuando** pasa un momento, **entonces** la persona ve que está escribiendo.
5. **Dado** que el agente envía una ubicación o la pide, **cuando** sale, **entonces** la persona la ve como ubicación de WhatsApp, no como texto.

---

### Historia 6 — Lo que cuesta y lo que queda (Prioridad: P2)

El partner ve por cliente y por número cuántos mensajes cobró Meta y de qué tipo, y en qué límite de mensajería está el portafolio. Así puede explicarle a su cliente la factura de Meta.

**Por qué esta prioridad**: el precio de Meta cambió el 2026-10-01 y la pregunta llegará.

**Prueba independiente**: enviar mensajes de servicio, utilidad y marketing en staging y ver su clasificación y si se cobran en la consola.

**Escenarios de aceptación**:

1. **Dado** un mensaje entregado, **cuando** llega su estado, **entonces** queda registrado si Meta lo cobra, de qué tipo y con qué categoría.
2. **Dado** un cliente, **cuando** el partner abre su consumo, **entonces** ve los mensajes de Meta del mes por categoría, separados de lo que cobra Auphere.
3. **Dado** un cambio del límite de mensajería del portafolio, **cuando** llega, **entonces** se ve en la ficha del número.

---

### Historia 7 — El perfil del negocio, desde la consola (Prioridad: P3)

El partner edita desde la consola la foto, la descripción, la dirección, el correo, las webs y el sector del perfil de WhatsApp del cliente, y ve el estado del nombre visible.

**Por qué esta prioridad**: hoy obliga a entrar en el administrador de Meta. Es comodidad, no riesgo.

**Prueba independiente**: cambiar la descripción en staging y verla en WhatsApp.

**Escenarios de aceptación**:

1. **Dado** un número conectado por Cloud API, **cuando** el partner guarda el perfil, **entonces** WhatsApp lo muestra.
2. **Dado** un número en coexistencia, **cuando** se abre el perfil, **entonces** la consola dice que se edita desde la app de WhatsApp Business y no ofrece el formulario.

---

### Historia 8 — Revisión de Meta de catálogo y portafolio (Prioridad: P2)

El equipo puede demostrar, con una cuenta de revisor y un número por Cloud API, los usos que las guías oficiales piden para `catalog_management` y `business_management`, y enviarlos en la misma solicitud que Instagram y Messenger.

**Por qué esta prioridad**: Meta revisa la app entera en cada envío y no deja editarlo. Lo que no entre ahora espera al siguiente.

**Prueba independiente**: seguir el guion con la cuenta de revisor y grabar un vídeo por permiso que cumpla la guía oficial.

**Escenarios de aceptación**:

1. **Dado** el guion de `catalog_management`, **cuando** se sigue, **entonces** se ve conceder el permiso y, en la consola, crear el catálogo del negocio, añadir un producto, editarlo y borrarlo (Historia 9), y la tarjeta de ese producto llega por WhatsApp.
2. **Dado** el guion de `business_management`, **cuando** se sigue, **entonces** se ve el uso real (catálogos del portafolio del negocio) y la descripción nombra el permiso del que depende.

---

### Historia 9 — El catálogo de WhatsApp sin salir de Auphere (Prioridad: P2)

Cualquier negocio, sea del tipo que sea, puede querer que el agente enseñe sus productos o servicios con tarjetas de WhatsApp. Hoy necesita crear el catálogo en el Administrador de comercio de Meta, cargarlo allí y enlazarlo. Con esta historia lo hace desde la página del número en la consola, en el mismo sitio donde configura a quién responde el agente. La sección está en **todos** los números; quien no la necesita no la configura:
- si no tiene catálogo, lo crea;
- añade, edita, oculta o borra sus productos, con foto, precio y disponibilidad;
- el agente los usa al momento.

Un negocio que ya alimenta su catálogo desde su tienda (WooCommerce, Shopify) lo ve y lo enlaza, pero no lo edita aquí: la verdad está en su tienda.

**Por qué esta prioridad**: lleva a todos los clientes una función que hoy solo tienen los que ya alimentan su catálogo desde una tienda. Además es el uso que la revisión de Meta pide demostrar. No es una pantalla para la revisión: es la forma de vender por WhatsApp sin aprender otra herramienta.

**Prueba independiente**: con un número de prueba por Cloud API y un negocio sin catálogo, crear el catálogo desde la consola, añadir tres productos y preguntar por uno al número. Llega su tarjeta. Después editar el precio, volver a preguntar y comprobar que llega el precio nuevo.

**Escenarios de aceptación**:

1. **Dado** un número sin catálogo, **cuando** el partner abre la sección Catálogo, **entonces** ve qué gana el negocio con uno y un único botón para crearlo. Al crearlo queda enlazado al número.
2. **Dado** un catálogo creado desde Auphere, **cuando** el partner añade un producto con nombre, foto, precio y disponibilidad, **entonces** aparece en la lista con su estado en Meta («en revisión», «visible», «rechazado» con el motivo) y el agente puede enseñarlo en cuanto Meta lo acepta.
3. **Dado** un producto, **cuando** el partner cambia su precio o lo marca como agotado, **entonces** la tarjeta de WhatsApp lo refleja y el agente deja de ofrecerlo si está agotado.
4. **Dado** un producto, **cuando** el partner lo borra, **entonces** se le pide confirmación con el nombre del producto, desaparece del catálogo y el agente deja de ofrecerlo.
5. **Dado** un catálogo que alimenta la tienda del negocio, **cuando** el partner lo abre, **entonces** ve sus productos sin poder editarlos, con la frase «Se gestiona desde {tienda}» y un enlace a la tienda.
6. **Dado** un número en coexistencia, **cuando** el partner abre la sección, **entonces** ve que el catálogo se gestiona desde la app de WhatsApp Business y puede apuntar el catálogo que ya tiene, como hoy.
7. **Dado** un catálogo con decenas de productos, **cuando** el partner lo abre, **entonces** puede buscarlos y filtrarlos por disponibilidad sin que la página se vuelva lenta.

---

### Casos límite

- **Identidad.**
  - Una persona llega primero con identificador de Meta y luego con número, o al revés: es la misma conversación si Meta da los dos en un mismo evento. Si no, son dos personas hasta que Meta las enlace.
  - El identificador de Meta cambia (evento de sistema): la conversación sigue y el cambio queda registrado.
- **Lotes.** Uno que mezcla mensajes de dos números de la misma cuenta: cada mensaje va a su número. Si un elemento falla, no impide procesar el resto.
- **Eventos de cuenta.** Uno de una cuenta que ningún cliente tiene conectada se ignora sin tocar datos. Uno de un número de Auphere (canal del dueño) sigue su camino actual.
- **Plantillas.** Una recategorizada a marketing a la que la persona tiene baja: no sale.
- **Ventana de 24 h.** Fuera de ella, el agente solo puede usar plantillas aprobadas. El rechazo se explica sin reintentos.
- **Precio.** Un mensaje que Meta no cobra se registra como no cobrado, no como «sin dato».
- **Conexión.** Alguien abre el registro con una versión vieja guardada en caché: la consola la detecta y recarga la configuración vigente.
- **Catálogo.**
  - Meta rechaza un producto por política o por la imagen: el producto se queda, marcado con el motivo y la forma de corregirlo, y el agente no lo ofrece.
  - Se borra en Meta un catálogo que estaba enlazado: el número deja de enviar tarjetas, el agente responde con texto y la sección ofrece volver a crearlo o enlazar otro.
  - Dos personas editan el mismo producto a la vez: la segunda ve que cambió y no pisa el cambio sin querer.
- **Sin disponibilidad.** Lo que un número no admite (perfil en coexistencia, plantillas de autenticación sin el permiso del negocio) no se ofrece apagado: no aparece, y la ficha del número dice por qué cuando el partner lo busca (constitución §V).

## Requisitos *(obligatorio)*

### Requisito 1 — El webhook procesa todo lo que Meta envía

**Historia de usuario:** Como plataforma, quiero tratar cada evento de WhatsApp al que estamos suscritos, para que ninguno se pierda en silencio.

#### Criterios de aceptación

1. WHEN llega un lote con varios mensajes, estados, ecos o cambios THEN el sistema DEBE procesar cada elemento una sola vez, en el orden de Meta.
2. IF un elemento del lote no se puede procesar THEN el sistema DEBE registrarlo con su motivo y seguir con el resto, y NO DEBE responder error a Meta.
3. El sistema DEBE dar tratamiento a cada campo suscrito: `messages`, `message_template_status_update`, `message_template_quality_update`, `template_category_update`, `account_update`, `account_alerts`, `account_review_update`, `business_capability_update`, `phone_number_name_update`, `phone_number_quality_update`, `user_preferences`, `business_username_updates`, `history`, `smb_app_state_sync` y `smb_message_echoes`.
4. WHEN llega un campo no suscrito o desconocido THEN el sistema DEBE registrarlo sin datos personales y responder éxito.
5. WHEN un mensaje entrante trae errores o es de sistema (cambio de número o de identificador) THEN el sistema DEBE registrarlo y actualizar la identidad de la persona sin disparar al agente.
6. WHEN un mensaje entrante trae `deleted` o el estado de salida es `warning` THEN el sistema DEBE reflejarlo en la conversación.
7. El sistema DEBE responder a Meta en menos de 20 segundos y procesar fuera de la petición lo que tarde.

### Requisito 2 — Identidad por identificador de Meta (BSUID) y nombre de usuario

**Historia de usuario:** Como cliente final, quiero que me atiendan aunque escriba con mi nombre de usuario de WhatsApp, para no tener que enseñar mi número.

#### Criterios de aceptación

1. WHEN llega un mensaje THEN el sistema DEBE identificar a la persona por el identificador de Meta cuando venga, y por el número cuando venga; los dos campos son opcionales.
2. WHERE un evento trae a la vez identificador de Meta y número EL sistema DEBE asociarlos a la misma persona, sin crear una nueva.
3. IF dos personas distintas comparten un dato parcial THEN el sistema NO DEBE fundirlas en una.
4. WHEN el agente o una persona del equipo responde THEN el sistema DEBE enviar al destinatario que Meta admite para esa persona: número o identificador.
5. WHEN llega un cambio de nombre de usuario del negocio (`business_username_updates`) THEN el sistema DEBE guardarlo y mostrarlo en la ficha del número.
6. Las bajas de marketing, el historial y la auditoría DEBEN seguir a la persona, no a un dato concreto de ella.
7. El identificador de la persona NO DEBE ser nunca un argumento del modelo.

### Requisito 3 — Conexión e inicio de sesión vigentes

**Historia de usuario:** Como partner, quiero conectar el WhatsApp de mi cliente por la vía que le convenga, para que empiece a atender sin pasos manuales.

#### Criterios de aceptación

1. El sistema DEBE usar en todas las vías la versión vigente del registro integrado de Meta, sin parámetros retirados, antes del 2026-11-16. Las vías son: Cloud API, coexistencia, enlace del dueño (spec 040), inicio de sesión con WhatsApp (beta) y número propio de Auphere.
2. WHEN el alta termina THEN el sistema DEBE dejar el número suscrito, registrado (Cloud API), con su nombre visible y su estado, y avisar al partner del resultado.
3. WHEN se registra un número por Cloud API THEN el sistema DEBE guardar cifrado su PIN de dos pasos y permitir al operador rotarlo, con auditoría.
4. IF el alta falla en cualquier paso THEN el sistema DEBE decir cuál y cómo seguir, y NO DEBE dejar canal ni credenciales a medias.
5. El sistema DEBE usar una sola versión de la API de Meta, configurable, en el servidor y en las consolas, igual o superior a v25.
6. WHEN Meta anuncia la retirada de la versión configurada THEN el sistema DEBE avisar al operador con al menos 60 días de margen.

### Requisito 4 — Salud de la cuenta y de las plantillas

**Historia de usuario:** Como partner, quiero enterarme de cualquier cambio de Meta en la cuenta o las plantillas de mi cliente, para actuar antes de que falle un envío.

#### Criterios de aceptación

1. WHEN cambia el estado, la calidad o la categoría de una plantilla THEN el sistema DEBE actualizarla, avisar al partner y dejar de ofrecerla al agente si ya no se puede enviar.
2. WHEN llega una alerta, una restricción, una revisión o un cambio de capacidad de la cuenta THEN el sistema DEBE reflejarlo en el estado del canal con su motivo y en la auditoría.
3. WHEN un evento de la cuenta no trae número THEN el sistema DEBE aplicarlo a los números de esa cuenta del negocio dueño.
4. WHEN Meta resuelve el nombre visible THEN el sistema DEBE mostrar el resultado y, si lo rechaza, el motivo.
5. El agente DEBE comprobar el estado de la plantilla sin distinguir mayúsculas.

### Requisito 5 — Bajas de marketing

**Historia de usuario:** Como cliente final, quiero dejar de recibir publicidad de un negocio sin perder su atención, para decidir qué me llega.

#### Criterios de aceptación

1. WHEN llega una baja de Meta (`user_preferences` con `stop`) THEN el sistema DEBE bloquear los mensajes de marketing a esa persona en ese número.
2. WHEN llega una reactivación (`resume`) THEN el sistema DEBE levantar la baja y dejar constancia.
3. WHEN una persona escribe una palabra de baja THEN el sistema DEBE tratarlo igual que una baja de marketing.
4. WHERE la persona tiene baja de marketing EL sistema DEBE seguir enviando servicio y utilidad.
5. El operador DEBE poder levantar una baja por palabra clave con el motivo, con auditoría.

### Requisito 6 — Plantillas completas

**Historia de usuario:** Como partner, quiero crear desde la consola todos los tipos de plantilla que Meta acepta, para no depender del administrador de Meta.

#### Criterios de aceptación

1. El sistema DEBE permitir crear plantillas con cabecera de texto, imagen, vídeo o documento, con cuerpo, pie y botones: respuesta rápida, URL, teléfono y copiar código.
2. El sistema DEBE permitir crear plantillas de autenticación con el botón que exige Meta.
3. El sistema DEBE permitir crear y enviar plantillas en carrusel.
4. WHEN el agente envía una plantilla THEN el sistema DEBE rellenar sus parámetros de cabecera, cuerpo y botones con el formato de Meta.
5. WHEN Meta rechaza una plantilla THEN el sistema DEBE mostrar el motivo con la acción sugerida.

### Requisito 7 — Mensajes entrantes y salientes completos

**Historia de usuario:** Como cliente final, quiero que el agente entienda lo que pulso y me responda con los formatos de WhatsApp, para no tener que escribirlo todo.

#### Criterios de aceptación

1. WHEN una persona pulsa un botón de respuesta rápida de una plantilla THEN el sistema DEBE entregar al agente el botón pulsado y la plantilla de origen.
2. WHEN una persona llega desde un anuncio de clic a WhatsApp THEN el sistema DEBE guardar el anuncio en la conversación y ofrecerlo al agente como contexto.
3. WHEN una persona manda contactos THEN el sistema DEBE entregarlos al agente legibles.
4. WHILE el agente prepara una respuesta EL sistema DEBE mostrar a la persona el indicador de escritura, junto con el acuse de lectura.
5. WHEN el agente envía una ubicación THEN el sistema DEBE enviarla como ubicación de WhatsApp.
6. WHEN el agente pide la ubicación THEN el sistema DEBE enviar la petición nativa de Meta y entregar la respuesta como ubicación.

### Requisito 8 — Precio por mensaje y límites

**Historia de usuario:** Como partner, quiero saber qué mensajes cobra Meta a mi cliente y qué límite tiene, para explicarle su factura y planificar campañas.

#### Criterios de aceptación

1. WHEN llega el estado de un mensaje con precio THEN el sistema DEBE guardar si se cobra, su tipo y su categoría.
2. El sistema DEBE mostrar por cliente y mes los mensajes de Meta por categoría y cuántos se cobraron, como información, separado de lo que cobra Auphere.
3. El sistema NO DEBE cobrar al partner los mensajes de Meta: Meta los factura directamente al negocio.
4. WHEN cambia el límite de mensajería del portafolio o el tramo de precio THEN el sistema DEBE mostrarlo en la ficha del número.

### Requisito 9 — Perfil del negocio

**Historia de usuario:** Como partner, quiero editar el perfil de WhatsApp de mi cliente desde la consola, para mantenerlo al día sin entrar en Meta.

#### Criterios de aceptación

1. WHERE el número está conectado por Cloud API EL sistema DEBE permitir leer y editar foto, descripción, información, dirección, correo, webs y sector.
2. WHERE el número está en coexistencia EL sistema NO DEBE ofrecer el formulario, y DEBE decir que se edita desde la app.
3. Cada cambio DEBE quedar en la auditoría con quién lo hizo.

### Requisito 10 — Material de revisión de Meta

**Historia de usuario:** Como responsable de la integración, quiero un guion reproducible para `catalog_management` y `business_management`, para enviarlos en la misma solicitud que Instagram y Messenger.

#### Criterios de aceptación

1. El kit DEBE tener una cuenta de revisor y un número de demo conectado por Cloud API en un portfolio con catálogo.
2. WHEN se sigue el guion de cada permiso THEN DEBE producirse una llamada exitosa reciente y un vídeo que cumpla la guía oficial de ese permiso.
3. El kit DEBE incluir las instrucciones del revisor actualizadas para WhatsApp, catálogo, Instagram y Messenger.
4. El envío NO DEBE incluir permisos sin uso: `whatsapp_business_manage_events` y `ads_read` quedan fuera.

### Requisito 11 — Catálogo de productos en la consola

**Historia de usuario:** Como partner, quiero crear y mantener el catálogo de productos del número de mi cliente desde su página en la consola, para que el agente enseñe tarjetas de producto sin usar herramientas de Meta.

#### Criterios de aceptación

1. La sección DEBE estar disponible en **todos** los números de WhatsApp de cualquier cliente, sin depender del tipo de negocio, la plantilla del agente ni el plan. Es opcional: un número sin catálogo funciona igual que hoy, y la sección solo invita a crearlo.
2. La gestión DEBE vivir en la página de configuración del número en la consola nueva, como una sección más de su índice («Catálogo»). DEBE usar los componentes, la barra de guardado, los estados y las reglas de accesibilidad del sistema de diseño de la consola (spec 047, prototipo `agente.md` §8), sin pantallas ni patrones propios.
3. WHERE el número no tiene catálogo EL sistema DEBE ofrecer crearlo en el portafolio del negocio y enlazarlo al número en un solo paso.
4. El sistema DEBE permitir crear, editar, ocultar y borrar productos: nombre, descripción, foto, precio con moneda, disponibilidad y enlace opcional. El identificador del producto DEBE generarse solo y no pedirse.
5. WHEN se guarda un producto THEN el sistema DEBE mostrar su estado en Meta y, si Meta lo rechaza, el motivo y cómo corregirlo.
6. IF el catálogo se alimenta desde una tienda o un archivo del negocio THEN el sistema DEBE mostrarlo en solo lectura, diciendo de dónde viene, y NO DEBE ofrecer editarlo.
7. WHERE el número está en coexistencia EL sistema DEBE explicar que el catálogo se gestiona desde la app y mantener el enlace manual de hoy.
8. Borrar un producto DEBE pedir confirmación con su nombre. Cada creación, cambio y borrado DEBE quedar en la auditoría con la persona.
9. WHEN un producto cambia THEN el agente DEBE usar el dato nuevo en su siguiente respuesta, y NO DEBE ofrecer productos ocultos, agotados ni rechazados.
10. La lista DEBE tener buscador y filtro por disponibilidad, y estados de vacío, carga, error y parcial (constitución §V).
11. Solo quien tiene permiso de escritura en los canales del cliente DEBE poder editar. Quien solo lee DEBE ver el catálogo sin controles de edición.
12. WHEN un número tiene un catálogo enlazado THEN el agente que atiende ese número DEBE poder buscar productos y enviar sus tarjetas, sin cambiar de plantilla ni de versión del agente. Sin catálogo, el agente no tiene esas capacidades y no las menciona.

### Entidades clave

- **Número de WhatsApp (canal)**: de un negocio (RLS por tenant). Gana su nombre de usuario, el estado del nombre visible, el límite y tramo de su portafolio, el estado de revisión de la cuenta y el PIN de dos pasos (cifrado).
- **Persona (cliente final)**: del negocio. Se identifica por el identificador de Meta, por el número, o por ambos asociados; la plataforma decide cuál.
- **Baja de marketing**: persona y número, origen (Meta o palabra clave), fecha de alta y de reactivación.
- **Plantilla**: del negocio y su cuenta de WhatsApp. Estado, calidad, categoría, tipo de cabecera, botones, carrusel y motivo del último cambio.
- **Precio del mensaje**: por mensaje saliente, si se cobra, el tipo y la categoría.
- **Origen de anuncio**: por conversación, el anuncio de clic a WhatsApp del que vino la persona.
- **Catálogo y producto**: del portafolio del negocio en Meta, enlazado a un número (RLS por tenant a través del canal). Del catálogo se guarda su origen (creado en Auphere, tienda o archivo). De cada producto, su estado en Meta y el motivo del último rechazo. La fuente de verdad del producto es Meta.

## Criterios de éxito *(obligatorio)*

- **CE-001**: cero eventos de campos suscritos acaban como «no tratado» durante una semana de tráfico de staging y producción.
- **CE-002**: el 100 % de los elementos de cada lote se procesan, medido con lotes de prueba de 2 a 50 elementos.
- **CE-003**: una persona que escribe solo con identificador de Meta recibe respuesta del agente en menos de un minuto en el 95 % de los intentos.
- **CE-004**: las cinco vías de conexión terminan con el número atendiendo, en staging, después del 2026-11-16.
- **CE-005**: cero mensajes de marketing enviados a personas con baja, en la batería de pruebas.
- **CE-006**: el partner ve un aviso de un cambio de plantilla o de cuenta menos de 5 minutos después de que Meta lo envíe.
- **CE-007**: cero mezclas de personas o de negocios en la batería de aislamiento con identificadores de Meta y números.
- **CE-008**: WhatsApp no cambia para quien ya lo usa: las conversaciones existentes siguen en su hilo y los envíos de hoy salen igual.
- **CE-009**: un negocio sin catálogo llega desde la página del número a su primera tarjeta de producto en WhatsApp en menos de 5 minutos, sin abrir ninguna herramienta de Meta.
- **CE-010**: un cambio de precio o de disponibilidad se refleja en la siguiente respuesta del agente en el 100 % de los casos de prueba.

## Fuera de alcance

- **Flows de WhatsApp, llamadas, grupos y pagos**: cada uno es un producto en sí. Grupos exige cuenta oficial y pagos solo existe en India y Brasil.
- **Marketing Messages API y Conversions API (`whatsapp_business_manage_events`)**: sin caso de uso de anuncios todavía.
- **Agente de negocio de Meta (Meta Business Agent)**: compite con el producto; se estudia aparte.
- **Cobrar los mensajes de Meta**: Auphere no tiene línea de crédito; Meta factura al negocio.
- **Instagram y Messenger**: spec 049.

## Supuestos

- Meta factura directamente a cada negocio. Auphere registra y enseña el precio, no lo cobra.
- Se adopta la **versión 4 del registro integrado** de forma explícita antes del 2026-11-16. La 5, publicada el 2026-10-20, se evalúa en el plan y se adopta si no rompe la coexistencia ni el enlace del dueño.
- La versión de la API de Meta sube a v25 o superior en todo el sistema. Instagram y Messenger ya usan v26.
- Los permisos de WhatsApp ya aprobados (`whatsapp_business_messaging`, `whatsapp_business_management`) cubren identificadores de Meta, indicador de escritura, ubicación, perfil y plantillas: no hace falta pedir nada nuevo para ellos.
- La consola en uso es la nueva (spec 047): todo lo visible se diseña ahí.
- Los eventos se inyectan en staging con cargas firmadas para probar sin esperar a Meta.
- La spec cubre todo lo anterior y el plan lo parte en iteraciones por prioridad. P1 va primero, por el riesgo de perder mensajes y por la fecha de Meta.
- **Catálogo** (decisión del owner, 2026-10-29, opción A): se construye la gestión de productos en la consola, con el diseño nuevo y como función de producto, no como pantalla para la revisión. Necesita `catalog_management` (y `business_management` para crear el catálogo en el portafolio). Hasta la aprobación de Meta funciona para cuentas con rol en la app, así que el material de revisión se graba con ella.
