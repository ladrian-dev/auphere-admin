# Vídeos para la revisión de Meta: requisitos y plan de grabación

Fecha: 2026-11-01. Investigación solo en la web: no se ha tocado el Dashboard de Meta ni el código.

Complementa a `03-permisos-meta.md` (estado de cada permiso) y a `04-guiones-de-grabacion.md` (guiones escena a escena). Este documento dice **qué exige Meta** y **cómo organizar las grabaciones**. Los guiones de `04` deben ajustarse a lo que se dice aquí.

App: `957213733862330` («Auphere»), portfolio de Facelad, Tech Provider.

## Cómo leer este documento

Cada afirmación lleva una de estas marcas:

- **[Oficial]**: está en `developers.facebook.com`, leído el 2026-11-01.
- **[Terceros]**: guías de otras empresas o hilos del foro de Meta. Sirve como pista, no como regla.
- **[Sin documentar]**: no lo he encontrado en ninguna fuente oficial. Va con la recomendación del equipo.

---

## 1. Requisitos de la grabación

| Tema | Qué dice Meta o la práctica | Marca |
|---|---|---|
| Cobertura | Cada permiso y cada función pedidos necesitan una grabación. «Any requested permission or feature missing a screen recording will not be approved.» | [Oficial] [guía de envío](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide) |
| Contenido | El usuario concede el permiso y después se ve cómo la app usa los datos. Hay que empezar con la sesión cerrada y grabar el flujo completo hasta tener la sesión iniciada | [Oficial] [screen recordings](https://developers.facebook.com/docs/app-review/submission-guide/screen-recordings) |
| Botón de login de negocio | Si se usa Facebook Login for Business, el botón tiene que verse, igual que la autorización completa con la concesión de cada permiso | [Oficial] screen recordings |
| Por qué se pide el permiso | No se explica en el vídeo. Va en el texto de uso del formulario | [Oficial] screen recordings |
| Resolución | 1080 px o más. Ancho del monitor de 1440 px o menos mientras se graba. Pantalla completa o solo la ventana de la app | [Oficial] screen recordings |
| Idioma | Interfaz en inglés si es posible. Si no, o si algo no se entiende solo, añadir rótulos o tooltips y explicar los botones que no sean obvios | [Oficial] screen recordings y [Instagram app review](https://developers.facebook.com/docs/instagram-platform/app-review) |
| Audio | Sin audio: el revisor no lo escucha. Algunas guías de terceros (Chatwoot) proponen narrar, pero la guía oficial lo descarta | [Oficial] |
| Subtítulos | Meta pide «captions or tool-tips» cuando hacen falta. No exige un formato de subtítulos (SRT): basta con texto incrustado en el vídeo | [Oficial] para el texto en pantalla. El formato es [Sin documentar] |
| Cursor y ratón | Usar el ratón más que el teclado y agrandar el cursor | [Oficial] screen recordings |
| Anotaciones y zoom | Rótulos para cada permiso y función. Zoom en lo que cueste ver | [Oficial] screen recordings |
| Herramientas | Camtasia, Snagit, QuickTime u OBS, y iMovie para rótulos y zoom | [Oficial] screen recordings |
| Mensajería | En `instagram_manage_messages` y `pages_messaging`, el vídeo tiene que mostrar un mensaje enviado desde la app que **llega a la bandeja** de Instagram o de Messenger. Tiene que ser una grabación, no capturas | [Oficial] [Permissions reference](https://developers.facebook.com/docs/permissions) |
| Misma app | La app que se graba tiene que ser la misma que se envía (mismo App ID). Si no, rechazo | [Oficial] [Instagram Messaging, apps for other businesses](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/app-review/apps-for-other-businesses) |
| Formato del archivo | No documentado. Usar MP4 (H.264) con la extensión en minúsculas | [Sin documentar] |
| Tamaño máximo | No documentado. En el foro hay errores al subir un MP4 de 20 MB, sin una causa clara ([hilo](https://developers.secure.facebook.com/community/threads/953076756848227)). Recomendación: menos de 100 MB por vídeo, y si falla, volver a codificar y probar con otro navegador | [Sin documentar] [Terceros] |
| Duración | Sin límite documentado. Recomendación: 1 a 3 minutos por vídeo, cortando esperas y cargas | [Sin documentar] |
| Cuentas de prueba | Los revisores prueban con **sus propias** cuentas de Facebook. No se incluyen credenciales personales ni de usuarios de prueba de Facebook o Instagram. Una cuenta falsa con sus credenciales en el envío rechaza toda la solicitud | [Oficial] guía de envío, [common mistakes](https://developers.facebook.com/docs/app-review/submission-guide/common-mistakes) y apps for other businesses |

**Para grabar se pueden usar cuentas reales de prueba del equipo**, como la cuenta profesional de demo y una cuenta personal que escriba. Lo que se prohíbe son las cuentas falsas y dar credenciales de Facebook. Los usuarios de prueba de Facebook (test users) no sirven para Instagram profesional ni para un portfolio real. Esto último no lo he visto documentado y es práctica habitual.

---

## 2. Requisitos del envío (fuera del vídeo)

| Requisito | Detalle | Marca y fuente |
|---|---|---|
| Acceso avanzado | Hace falta para atender a negocios sin rol en la app. Se aprueba **permiso a permiso**. Con acceso estándar, solo se pueden pedir permisos a usuarios con rol y las funciones solo están activas para ellos | [Oficial] [Access levels](https://developers.facebook.com/docs/graph-api/overview/access-levels) |
| Verificación del negocio | Obligatoria para el acceso avanzado, Human Agent y Business Asset User Profile Access. Facelad ya pasó la revisión de WhatsApp, así que debería estar hecha. Hay que confirmarlo en el Dashboard | [Oficial] Access levels, [Human Agent](https://developers.facebook.com/docs/features-reference/human-agent), [BAUPA](https://developers.facebook.com/docs/features-reference/business-asset-user-profile-access) |
| Llamada con éxito | Al menos una llamada con éxito por cada permiso con acceso avanzado en los 30 días anteriores al envío. Puede hacerse desde la app o desde Graph API Explorer. La llamada tarda hasta 2 días en aparecer. **Afecta a los permisos nuevos**: `pages_read_user_content` y `pages_manage_engagement` tienen que tener ya su llamada | [Oficial] guía de envío |
| Texto de uso por permiso | Uno distinto para cada permiso: cómo ayuda al usuario, por qué hace falta, cómo se usan los datos y por qué la app sería peor sin él. **No copiar y pegar entre permisos** | [Oficial] guía de envío |
| Dependencias | Si un permiso depende de otro, los dos van en el mismo envío. Si `business_management` se pide como dependencia, hay que decir de qué permiso depende | [Oficial] Instagram app review y Permissions reference |
| Plataforma | Website, con la URL donde el usuario entra y configura la bandeja (la consola) | [Oficial] apps for other businesses |
| Instrucciones para el revisor | Paso a paso: cómo entrar, cómo conceder permisos con Facebook Login for Business y cómo configurar la bandeja. Si el login de la app no es de Facebook, hay que dar usuario y contraseña de prueba de la consola | [Oficial] apps for other businesses |
| Accesibilidad | El revisor tiene que poder abrir y usar la app. Si no puede, se rechaza **todo** el envío | [Oficial] common mistakes |
| App terminada | Una app que parezca inacabada se rechaza. No se piden permisos «para más adelante» | [Oficial] common mistakes |
| Ajustes básicos | Icono de 1024×1024, URL de la política de privacidad (Meta la enseña en el diálogo de permisos), categoría y correo de contacto | [Oficial] guía de envío e Instagram app review |
| Borrado de datos | URL de callback de borrado (POST firmado con `signed_request`, que responde `{url, confirmation_code}`) o URL con instrucciones de borrado, en Ajustes básicos. La política de privacidad tiene que explicar cómo pedir el borrado | [Oficial] [Data deletion callback](https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback) |
| Preguntas de tratamiento de datos | Se responden en el paso 2 del envío: procesadores, transferencias y peticiones de autoridades | [Oficial] guía de envío |
| Data Use Checkup | Es anual para las apps con acceso avanzado. Meta lo está integrando en una «data access renewal» única al año. No forma parte del envío, pero tras la aprobación habrá que certificar el uso de cada permiso | [Oficial] [Data Use Checkup](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/data-use-checkup) y [FAQ de data access renewal](https://developers.facebook.com/documentation/resp-plat-initiatives/data-access-renewal/faqs) |
| Página publicada (Messenger) | La Página de Facebook asociada tiene que estar publicada | [Oficial] [Messenger app review](https://developers.facebook.com/docs/messenger-platform/app-review) |
| Webhook sano (Messenger) | Responder `200 OK` en menos de 20 s y estar suscrito a `messaging_policy_enforcement` | [Oficial] Messenger app review |
| Partes cerradas | Si hay partes de la app cerradas, dar al revisor una forma de entrar: credenciales o una frase que dispare el flujo | [Oficial] Messenger app review |
| Login de Instagram | La app usa Facebook Login **o** Instagram Login, no las dos. Auphere usa «Instagram API with Facebook Login», que es lo correcto para los permisos `instagram_*` sin `business` | [Oficial] Instagram app review |

### Facebook Login for Business en el vídeo

- Tiene que verse el botón y la ventana de Meta.
- Tiene que verse la elección de la Página o de la cuenta de Instagram.
- Tiene que verse la pantalla de permisos aceptada.
- Para `business_management`, Meta pide además que la app **avise al administrador de la Página** de que tiene que dar permisos explícitos para gestionar los activos del negocio. Hay que añadir una línea de texto en la consola, junto al botón «Connect», y que salga en el vídeo.

Fuentes: [Oficial] screen recordings y apps for other businesses.

---

## 3. Qué mostrar por cada permiso o función

Los textos de uso son **borradores en inglés**: el formulario es en inglés y lo lee un revisor angloparlante. Hay que adaptarlos al producto real y no reutilizar frases entre permisos.

### 3.1 Instagram (configuración de login de Instagram)

#### `instagram_basic`

- **Uso permitido** [Oficial]: leer metadatos básicos de la cuenta profesional, como el usuario y el ID.
- **Dependencias según la referencia** [Oficial]: `pages_read_user_content` y `pages_show_list`.
- **Qué mostrar:**
  1. Sesión cerrada en la consola.
  2. Login del partner.
  3. Cliente → agente → Channels → Instagram → Connect.
  4. Ventana de Facebook Login for Business con la elección de la cuenta de Instagram.
  5. Pantalla de permisos aceptada.
  6. Vuelta a la consola con la tarjeta que muestra **@usuario y foto**.
- **Requisito específico** [Oficial]: en el texto hay que nombrar los campos concretos que se usan y dónde salen en la app. El vídeo tiene que enseñar la elección de la cuenta de Instagram.
- **Borrador:** «Auphere is a customer-messaging platform used by agencies to run an AI assistant and a team inbox for their client businesses. When a business connects its Instagram professional account through Facebook Login for Business, we read the account's `id`, `username` and `profile_picture_url`. We show them on the channel card in the console, so the business can confirm the right account is connected. The `id` routes each incoming DM to the correct client workspace.»

#### `instagram_manage_messages`

- **Uso permitido** [Oficial]: leer conversaciones, responder y usar herramientas de terceros (CRM o bandeja) para los DM.
- **Dependencias** [Oficial]: `instagram_basic`, `pages_read_engagement` y `pages_show_list`.
- **Qué mostrar:**
  1. Desde una cuenta personal, en el móvil, se manda un DM a la cuenta de demo.
  2. El DM aparece en la bandeja de Auphere.
  3. El asistente responde. Meta pide que la respuesta automática llegue **en menos de 30 s** [Oficial].
  4. En el móvil se ve la respuesta en Instagram.
  5. Una persona del equipo toma el control y responde a mano desde la consola, y la respuesta llega al móvil.
  6. Gestión de un mensaje anulado: el usuario anula un DM en el móvil y la consola lo refleja.
- **Pantalla a pantalla:** Meta pide un vídeo del mensaje enviado desde la app y que **llega a la bandeja de Instagram**, no capturas [Oficial].
- **Formulario** [Oficial]:
  - Indicar si es «automated experience», «custom inbox» o las dos. Auphere es las dos.
  - Si es bandeja propia: explicar cómo leer, responder y borrar mensajes a mano.
  - Si es automatizada: explicar cómo probar el traspaso a una persona.
  - Explicar cómo probar los mensajes anulados.
- **Elementos de Instagram** [Oficial]: la guía pide montar quick replies, ice breakers y menú persistente «so users can interact in several ways». No queda claro si es obligatorio o «si aplica».
  - **Riesgo:** si Auphere no tiene ice breakers ni quick replies, hay que decirlo en el texto o añadirlos.
  - Hay que comprobar también que la consola trata `is_deleted` (mensaje anulado), porque Meta pide probarlo.
- **cURL** [Oficial]: la referencia pide además generar un cURL de envío con el API Integration Helper del Dashboard.
- **Borrador:** «Businesses use Auphere as both an automated assistant and a custom inbox for Instagram Direct. Incoming DMs arrive through the `messages` webhook, are stored in the client's workspace, and the AI assistant replies with the Send API within seconds. At any moment a team member can take over the thread from the Auphere inbox, reply manually, and hand it back. Without this permission the business could not answer its customers' DMs from Auphere.»

#### `instagram_manage_comments`

- **Uso permitido** [Oficial]: leer, crear, ocultar y borrar comentarios de la cuenta, y leer y responder en medios donde se menciona al negocio.
- **Dependencias** [Oficial]: `instagram_basic`, `pages_read_engagement` y `pages_show_list`.
- **Ojo:** en la referencia oficial, el texto de ejemplo de este permiso está copiado de otro (`instagram_content_publish`). No sirve de plantilla.
- **Qué mostrar:**
  1. Desde una cuenta personal, se comenta una publicación de la cuenta de demo («Price?»).
  2. El comentario llega a Auphere y se ve en la consola, con su texto y el post.
  3. El asistente publica la **respuesta pública** bajo el comentario, y se ve en la app de Instagram.
  4. El asistente manda **una respuesta privada** por DM (`recipient.comment_id`), y se ve en los DM del móvil.
  5. Si la consola permite ocultar o borrar comentarios, enseñarlo. Si no lo permite, no prometerlo en el texto.
- **Borrador:** «Auphere lets a business answer comments on its own Instagram posts. When a customer comments, we receive the `comments` webhook. The comment, with its post, appears in the Auphere console. The assistant then posts a short public reply under the comment and, when the comment asks for details such as a price, sends one private reply to the commenter's DM. Team members can see every comment and reply in the console.»

#### `business_management` (en las dos configuraciones)

- **Qué decir** [Oficial]:
  - Es una dependencia de `pages_messaging` y `pages_show_list`, y en Instagram de `instagram_manage_messages`. En Auphere sirve además para listar los catálogos del portfolio del cliente (ver `03`).
  - En el texto hay que nombrar el permiso principal del que depende.
- **Qué mostrar** [Oficial]:
  1. El administrador de la Página pasa por Facebook Login for Business.
  2. Elige las Páginas o las cuentas de Instagram.
  3. Concede los permisos.
  4. La consola le avisa de que tiene que darlos de forma explícita.
- **Borrador:** «`business_management` is required as a dependency of `pages_messaging`, `pages_show_list` and `instagram_manage_messages`. Our agency customers connect assets that belong to their clients' business portfolios. During Facebook Login for Business, the admin selects the Page or Instagram account of the client's business and explicitly grants access. Auphere then reads only the assets that were shared with it.»

### 3.2 Messenger (configuración «Auphere Messenger»)

#### `pages_show_list`

- **Uso permitido** [Oficial]: mostrar las Páginas que gestiona la persona y comprobar que gestiona una Página concreta.
- **Qué mostrar:**
  1. El login.
  2. La lista de Páginas en la ventana de Meta.
  3. En la consola, la Página conectada con su nombre.
- **Borrador:** «When the business clicks "Connect Messenger", we list the Pages the admin manages so they can choose which Page Auphere will answer for, and we verify that the admin manages the selected Page before connecting it.»

#### `pages_manage_metadata`

- **Uso permitido** [Oficial]: suscribirse a los webhooks de la Página y cambiar sus ajustes.
- **Qué mostrar** [Oficial]: el usuario suscribe la Página a los eventos de webhook.
  - En Auphere no hay un interruptor: la suscripción (`POST /{page-id}/subscribed_apps`) ocurre al conectar.
  - En el vídeo: rótulo «Auphere subscribes the Page to messages and feed webhooks». Después, un mensaje que llega, y luego **Disconnect**, tras lo cual un mensaje nuevo ya no llega (escenas 4-5 de V-MS-1 en `04`).
- **Borrador:** «After the admin connects a Page, Auphere subscribes it to the `messages`, `messaging_postbacks` and `feed` webhook fields with `/{page-id}/subscribed_apps`, so customer messages and comments reach the business's inbox. When the business disconnects the channel, we remove the subscription.»

#### `pages_messaging`

- **Uso permitido** [Oficial]: experiencias que empieza el usuario, avisos de pedido o reserva, y atención al cliente.
- **Dependencias** [Oficial]: `pages_manage_metadata` y `pages_show_list`.
- **Qué mostrar** [Oficial]:
  - Un mensaje enviado desde la app que llega a la bandeja de Messenger: el mensaje del cliente, la bandeja de Auphere, la respuesta y el móvil.
  - También cURL y grabación, no capturas.
  - **También es el permiso de la respuesta privada a un comentario de la Página.**
- **Ojo:** el texto de ejemplo de la referencia está copiado de `pages_manage_ads`.
- **Borrador:** «Customers message the business's Facebook Page. The message reaches Auphere through the webhook, the AI assistant answers with the Send API, and a team member can take over from the inbox at any time. We also use this permission to send one private reply to a person who commented on the Page's post, within 7 days, as Messenger's private replies allow.»

#### `pages_read_engagement`

- **Uso permitido** [Oficial]: leer el contenido de la Página (publicaciones), sus metadatos y nombres, PSID y fotos de los seguidores.
- **Qué mostrar** [Oficial]: el contenido de una publicación mostrado en la app.
  - En Auphere: el nombre y la foto de la Página en la tarjeta, y el texto o la imagen del post al que pertenece un comentario.
  - **Si la consola no enseña el post, este permiso queda flojo:** conviene mostrar el post junto al comentario en la conversación.
- **Borrador:** «We read the connected Page's name and picture to show which Page is connected, and the content of the post a customer commented on, so the team and the assistant answer with the right context.»

#### `pages_read_user_content` (nuevo)

- **Uso permitido** [Oficial]: leer el contenido que crean los usuarios en la Página (publicaciones, comentarios y valoraciones) y borrar comentarios de usuarios.
- **Qué mostrar** [Oficial]: un usuario lee un comentario y **ese comentario se ve en la app**. Es decir:
  1. Alguien comenta en un post de la Página desde el móvil.
  2. El comentario aparece en la consola de Auphere con el autor (si llega) y el texto.
- **Llamada en 30 días:** hay que hacerla antes de enviar, por ejemplo `GET /{comment-id}` o `GET /{post-id}/comments` con el token de la Página de demo (ver §2).
- **Borrador:** «When a customer comments on one of the business's Page posts, Auphere receives the `feed` webhook and reads the comment (message, author and post) so it appears in the business's inbox in the Auphere console, next to the reply the assistant sends.»

#### `pages_manage_engagement` (nuevo)

- **Uso permitido** [Oficial]: publicar, editar y borrar comentarios en las publicaciones de la Página y dar o quitar «me gusta». Su fin es moderar.
- **Dependencias** [Oficial]: `pages_read_user_content` y `pages_show_list`.
- **Qué mostrar** [Oficial]: un comentario publicado en la Página y **visible en Facebook**:
  1. El asistente responde en público (`POST /{comment-id}/comments`).
  2. Se abre el post en Facebook y se ve la respuesta como la Página.
- **Borrador:** «The assistant answers customers' comments on the Page's posts with a public reply published as the Page, so other visitors also see the answer. Replies are visible in the Auphere console, where the team can review them.»

### 3.3 Funciones

#### Human Agent (`HUMAN_AGENT`)

- **Uso permitido** [Oficial]: que una **persona** responda hasta 7 días después del último mensaje del usuario, cuando el problema no se resuelve en la ventana estándar de 24 h. Ejemplo de Meta: un negocio cerrado el fin de semana.
- **Requisitos** [Oficial]: verificación del negocio y revisión.
- **Una sola función para dos canales:** Messenger e Instagram comparten la misma entrada en la referencia.
- **Cuándo pedirla** [Oficial]: solo si hay una bandeja propia para que respondan personas y los agentes necesitan hasta 7 días.
- **Formulario** [Oficial]: explicar por qué las respuestas pueden tardar hasta 7 días y no 24 h.
- **Vídeo** [Oficial]: si se envía junto con `instagram_manage_messages`, vale el vídeo general. Si no, hay que grabar a una persona que responde.
- **Recomendación:** grabar un vídeo propio de todas formas.
  1. Una conversación cuyo último mensaje del cliente tiene **más de 24 h**: la consola muestra que el asistente ya no puede responder.
  2. Una persona con nombre toma el control y responde.
  3. La respuesta llega al móvil.
  4. Rótulo: «Sent by a human agent with the HUMAN_AGENT tag, within 7 days».
  - Chatwoot propone lo mismo [Terceros, [guía](https://developers.chatwoot.com/self-hosted/instagram-app-review)].
- **Política:** nunca usar la etiqueta para mensajes automáticos. Es la causa típica de sanción [Terceros].
- **Preparación:** la conversación de más de 24 h hay que prepararla con un día de antelación (ver `04`).
- **Borrador:** «Auphere's AI assistant only replies inside the 24-hour window. Some requests need a person: a refund, a complaint, a booking change. These often arrive when the business is closed, for example on a Friday night. In those cases a named team member takes over the conversation in the Auphere inbox and replies with the HUMAN_AGENT tag within 7 days. The tag is never used by the assistant or for promotional content.»

#### Business Asset User Profile Access

- **Uso permitido** [Oficial]:
  - Leer `id`, `ids_for_business`, `name` y `picture` de las personas que interactúan con los activos del negocio, para usarlos en la experiencia de la app.
  - Para analítica, solo datos agregados y anónimos.
- **Requisitos** [Oficial]: verificación del negocio y revisión.
- **Vídeo:**
  - **El nombre y la foto de quien escribe tienen que verse en la bandeja.** Hay un rechazo documentado en el foro porque el vídeo no enseñaba el ID y el nombre que se citaban en el texto [Terceros].
  - Grabarlo en un vídeo propio: la guía de terceros desaconseja mezclar usos distintos en un mismo vídeo.
- **Incertidumbre:**
  - La referencia no deja claro si esta función cubre también el perfil de Instagram (`GET /{IGSID}`: `name`, `username`, `profile_pic`) o solo el PSID de Messenger.
  - Recomendación: describir los dos usos en el texto y mostrar los dos en el vídeo, o pedirla solo si se confirma que la consola enseña nombres (decisión pendiente del owner, ver `03`).
- **Borrador:** «When a customer writes to the business's Page or Instagram account, Auphere reads the person's name and profile picture so the team can recognise who they are talking to in the inbox. We don't use these fields for anything else, and we don't share them outside the business's workspace.»

---

## 4. Comentarios: webhooks y cómo demostrarlo

### Lo que dice Meta [Oficial]

- **Instagram** ([webhooks para Instagram](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-instagram)):
  - Las apps de negocio necesitan acceso avanzado; sin él, no reciben webhooks.
  - Para `comments` y `live_comments`, la app tiene que haber pasado la revisión.
  - La cuenta dueña del contenido tiene que ser pública.
  - El negocio tiene que estar verificado.
  - La Página tiene que estar suscrita con `POST /{page-id}/subscribed_apps` (`pages_manage_metadata`).
- **Permisos del campo `comments` con Facebook Login** ([matriz de campos](https://developers.facebook.com/documentation/instagram-platform/webhooks/fields)): `instagram_basic`, `instagram_manage_comments`, `pages_manage_metadata`, `pages_read_engagement` y `pages_show_list`.
- **Webhooks de Graph en general** ([Webhooks](https://developers.facebook.com/docs/graph-api/webhooks)):
  - En modo desarrollo solo llegan las pruebas del Dashboard y los eventos de usuarios con rol en la app.
  - En modo publicado, solo llegan los datos para los que la app tiene el permiso aprobado.
- **Mensajería de Instagram** ([webhook de Instagram Messaging](https://developers.facebook.com/docs/messenger-platform/instagram/features/webhook/)):
  - Mientras no haya aprobación, solo hay webhooks si quien usa la app tiene un rol.
  - La app tiene que estar publicada aunque no haya revisión.
- **Feed de la Página** ([webhooks para Páginas](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-pages)):
  - `feed` necesita `pages_manage_metadata` y `pages_show_list`.
  - El token lo tiene que pedir alguien con la tarea `CREATE_CONTENT`, `MANAGE` o `MODERATE`.
  - La Página tiene que tener instalada la app.
- **Respuestas privadas:**
  - Una sola por comentario, dentro de 7 días. Se puede seguir la conversación solo si el usuario contesta, y entonces rige la ventana de 24 h.
  - En Instagram con Facebook Login, la página oficial pide `instagram_manage_comments` **y** `pages_messaging`, y cita también Human Agent y acceso avanzado ([Instagram private replies](https://developers.facebook.com/docs/messenger-platform/instagram/features/private-replies)).
  - En Facebook solo pide `pages_messaging` ([Messenger private replies](https://developers.facebook.com/docs/messenger-platform/discovery/private-replies)).

### Consecuencias para Auphere

1. **Antes de la aprobación no llegarán comentarios de cuentas sin rol.**
   - Para grabar, la cuenta que comenta (la cuenta personal de prueba) **tiene que tener un rol en la app**: Instagram tester o developer en la app `957213733862330`.
   - La cuenta profesional de demo también tiene que pertenecer a alguien con rol.
   - La app tiene que estar en modo publicado. Ya lo está por WhatsApp, pero hay que confirmarlo.
   - Que con rol lleguen los `comments` de Instagram sin aprobación es **[Sin documentar] y contradictorio**:
     - la página de Instagram dice que `comments` exige haber pasado la revisión;
     - en el foro hay quien los recibe con cuentas con rol y quien no ([hilo](https://developers.secure.facebook.com/community/threads/818907743455411)).
   - **Hay que probarlo en staging antes de reservar el día de grabación.**
2. **Si los `comments` de Instagram no llegan antes de la revisión, hay una alternativa aceptada en la práctica** [Terceros]:
   - Grabar el resto del flujo real: el comentario en el móvil, y la respuesta pública y la privada.
   - Para el paso de recepción, disparar la notificación de prueba del Dashboard (Webhooks → Instagram → `comments` → Test) o reenviar a staging un payload de ejemplo con el ID de un comentario real.
   - Avisarlo con un rótulo («Comment webhooks are only delivered after App Review; this event was sent with the Dashboard test tool») y en las instrucciones al revisor.
   - Un hilo del foro dice que el botón Test de `comments` a veces no llega al callback. Por eso es más fiable reenviar un payload propio firmado.
   - Alternativa para mostrar que Auphere lee comentarios: leerlos con `GET /{media-id}/comments`. Es una llamada con éxito de `instagram_manage_comments` que cuenta para la regla de los 30 días.
3. **Riesgo de configuración** (comprobar en código y Dashboard):
   - Según la matriz oficial, el webhook `comments` de Instagram con Facebook Login necesita `pages_manage_metadata`, `pages_read_engagement` y `pages_show_list`. Además, la referencia pone `pages_read_user_content` y `pages_show_list` como dependencias de `instagram_basic`.
   - La configuración de login de Instagram descrita (`instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, `business_management`) **no los incluye**.
   - Si el login de Instagram es independiente del de Messenger, puede que el token no tenga lo necesario para suscribir la Página ni recibir comentarios.
   - Lo mismo pasa con `pages_messaging` para la respuesta privada en Instagram.
   - **Acción:** revisar la configuración `1157578836735566` antes de grabar, y que todas las dependencias estén en el mismo envío.
4. **Comentarios de la Página de Facebook:**
   - Con la app publicada y sin aprobar `pages_read_user_content`, solo llegarán los comentarios de usuarios con rol.
   - Grabar con una cuenta de Facebook con rol (tester) que comenta en la Página de demo.
   - En el foro y en n8n hay quien dice que en modo desarrollo ya no llegan ni los de usuarios con rol, así que la app tiene que estar publicada [Terceros].

---

## 5. Instrucciones para el revisor (plantilla)

Las credenciales van en el campo del envío, nunca en el vídeo. Se usan credenciales de una cuenta de la consola **sin rol de owner**. En el desplegable de credenciales se elige «does not use Facebook Login for Business», porque el revisor entra en Auphere con correo y contraseña y Facebook Login for Business solo sirve para conectar activos.

```
Auphere is a web console (https://<console-url>) used by agencies to run an AI assistant
and a team inbox for their client businesses on WhatsApp, Instagram and Messenger.

1. Go to https://<console-url>/login and sign in with the test credentials provided
   (email / password). This is an Auphere account, not a Facebook account.
2. Open Clients → "Meta Review Demo" → Agent → Channels.
3. Instagram: click "Connect" next to Instagram. A Facebook Login for Business window opens.
   Log in with your own Facebook account, pick an Instagram professional account you
   manage, and grant the requested permissions. The channel card then shows the
   account's username and picture.
4. Send a DM to that Instagram account from another Instagram account, e.g.
   "What time do you open?". The message appears in Conversations and the assistant
   replies in Instagram within a few seconds.
5. Comment "Price?" on a post of that account. The assistant replies publicly under the
   comment and sends one private reply to the commenter's DMs.
6. To test the human hand-off: open the conversation in Conversations, click "Take over",
   and type a reply. Click "Hand back" to return it to the assistant.
7. Messenger: click "Connect" next to Messenger, select a Page you manage and grant the
   permissions. Message the Page from another Facebook account; the message appears in
   Conversations and the reply arrives in Messenger. Comment on a Page post to see the
   public and private replies.
8. Human Agent: replies sent by a person after 24 h (up to 7 days) use the HUMAN_AGENT
   tag. You can see an example in the conversation "<name>" (last customer message > 24 h).
```

Antes de enviar hay que adaptar las etiquetas a la consola en inglés. Hay que quitar todo paso que no funcione: el revisor lo prueba y un paso roto rechaza todo el envío. Ya existe un borrador en `specs/049-meta-instagram-messenger/app-review-reviewer-instructions.md`, que hay que reconciliar con esta plantilla.

---

## 6. Plan de grabación

### Un vídeo por permiso o vídeos combinados

Las fuentes no coinciden:

- La página de revisión de Instagram pide un vídeo «for that permission only».
- La guía de Instagram Messaging dice que se suba «the general screen recording» para `instagram_basic`, `instagram_manage_messages` y Human Agent.

**Recomendación:**

- **Un vídeo por permiso o función.** Todos empiezan con el mismo **bloque de login de 20 a 30 s**, editado una vez y reutilizado: sesión cerrada → Connect → Facebook Login for Business → elección del activo → pantalla de permisos. Después viene la parte concreta del permiso.
- Así cada campo del formulario lleva su vídeo, el revisor no tiene que buscar dentro de un vídeo largo y se cumplen las dos guías.
- Para `business_management`, `pages_show_list` y `pages_manage_metadata`, donde casi todo es el login, el vídeo puede ser el mismo bloque con su rótulo.

### Lista de vídeos y duración aproximada

| # | Vídeo | Permisos o funciones a los que se sube | Escenas clave | Duración |
|---|---|---|---|---|
| A | Bloque común de login (no se sube solo) | — | Sesión cerrada → login del partner → Channels → Connect → Facebook Login for Business → elegir el activo → aceptar → tarjeta conectada | 30 s |
| IG-1 | Conectar Instagram | `instagram_basic` | A + zoom en @usuario y foto | 45-60 s |
| IG-2 | DM y traspaso | `instagram_manage_messages` | A (corto) + DM desde el móvil → bandeja → respuesta en menos de 30 s en el móvil → Take over → respuesta manual en el móvil → mensaje anulado | 2-3 min |
| IG-3 | Comentarios de Instagram | `instagram_manage_comments` | A (corto) + comentario en el móvil → la consola lo muestra → respuesta pública en el post → respuesta privada en los DM | 1,5-2 min |
| BM | Activos del negocio | `business_management` (en los dos envíos) | A con la elección del portfolio y el aviso «grant explicit access» + lista de catálogos si aplica | 45-60 s |
| MS-1 | Conectar Messenger | `pages_show_list`, `pages_manage_metadata` | A con la lista de Páginas → tarjeta → rótulo de suscripción → mensaje que llega → Disconnect → mensaje que no llega | 1,5 min |
| MS-2 | Mensajes de Messenger | `pages_messaging` | Mensaje desde Messenger → bandeja → respuesta → móvil → Take over | 1,5-2 min |
| MS-3 | Contenido de la Página | `pages_read_engagement` | Tarjeta con el nombre y la foto de la Página + post mostrado junto al comentario en la consola | 45 s |
| MS-4 | Comentarios de la Página | `pages_read_user_content`, `pages_manage_engagement` (dos cortes del mismo rodaje, uno para cada campo) | Comentario en el post desde el móvil → consola (lectura) → respuesta pública visible en Facebook (gestión) → respuesta privada por Messenger | 1,5-2 min cada corte |
| HA | Human Agent | Human Agent | Conversación de más de 24 h → el asistente bloqueado → una persona toma el control → respuesta en el móvil → rótulo de la etiqueta y del límite de 7 días | 1-1,5 min |
| PROF | Perfil de quien escribe | Business Asset User Profile Access | Mensaje entrante → la bandeja muestra el nombre y la foto del cliente (Messenger e Instagram) | 45 s |

### Orden del día de grabación

1. **La víspera:** preparar la conversación de más de 24 h para HA (no se puede falsear).
2. **Comprobar:**
   - la app publicada;
   - los roles de las cuentas que comentan y escriben;
   - la llamada con éxito de cada permiso en los últimos 30 días;
   - los webhooks de comentarios llegando al entorno donde se graba (§4).
3. Grabar A una sola vez con la sesión limpia.
4. Rodar IG-1 → IG-2 → IG-3, después MS-1 → MS-2 → MS-3 → MS-4, y al final BM, HA y PROF.
5. Montar, rotular y revisar cada vídeo entero antes de subirlo.

### Qué tiene que verse en pantalla

- **Pantalla partida o alternada** entre la consola en el portátil y el móvil, sea en el iPhone Mirroring de macOS o en una grabación del móvil insertada.
  - Lo que más valora el revisor es ver **el mismo mensaje** salir del móvil, entrar en Auphere y volver al móvil.
  - Mantener visibles las horas o un contador para que se vea que la respuesta tarda menos de 30 s.
- **El diálogo de Meta entero**, con los nombres de los permisos legibles: zoom en la lista de permisos.
- **El dato de Graph en la consola**, con zoom: @usuario y foto, nombre de la Página, texto del comentario y nombre del cliente. Es la prueba de uso de cada permiso.
- **Una parte visible en Facebook o Instagram** (post con la respuesta pública, DM con la respuesta privada) para los permisos que escriben.

### Consejos

- Facebook, Instagram y la consola en **inglés (EE. UU.)**. El idioma de Facebook se cambia en Settings → Language. El móvil también, para que la app de Instagram salga en inglés.
- Ventana del navegador de 1440 px de ancho o menos, a 100 % de zoom. Exportar a 1080p o más.
- Cursor agrandado. Ratón, no atajos de teclado.
- Rótulos breves en inglés en cada escena (ya están en `04`) y uno inicial con el permiso: «Permission: instagram_manage_comments».
- Sin audio. Sin música.
- **Sin datos sensibles:**
  - nada de tokens `EAA…`, el `code` de OAuth, DevTools ni el correo personal del owner;
  - nada de números de teléfono reales ni datos de clientes reales;
  - ocultar la contraseña al hacer login;
  - difuminar en la edición lo que se escape.
- Cortar las esperas largas, pero no cortar el momento en que se acepta el permiso ni la llegada de la respuesta: el revisor quiere ver que es real.
- No enseñar funciones que no se piden ni que no funcionan (por ejemplo, desconectar el catálogo; ver INC-01).
- Grabar con la **misma app** `957213733862330` y en el entorno que se da al revisor. Si se graba en staging y el revisor prueba en producción, hay que comprobar que los textos y los pasos coinciden.

---

## 7. Motivos de rechazo frecuentes

| Motivo | Marca |
|---|---|
| Falta el vídeo de un permiso o función: se rechaza ese permiso | [Oficial] common mistakes |
| El revisor no puede entrar en la app, o Facebook Login no se encuentra o falla: se rechaza **todo** el envío | [Oficial] common mistakes |
| La app parece inacabada, o se piden permisos que no se usan | [Oficial] common mistakes |
| Se entregan credenciales de una cuenta falsa | [Oficial] common mistakes |
| El vídeo no enseña el permiso en uso, o el texto y el vídeo no cuentan lo mismo («Screencast not aligned with use case details») | [Oficial] la primera parte; [Terceros] la etiqueta |
| El uso no encaja en el uso permitido del permiso (Developer Policy 1.9, «not needed to support core functionality») | [Terceros] (cita de un rechazo en el foro) |
| No hay ninguna llamada con éxito en los 30 días anteriores | [Oficial] guía de envío |
| Textos copiados entre permisos | [Oficial] guía de envío |
| El vídeo empieza con la sesión iniciada, o no se ve la pantalla de permisos | [Oficial] screen recordings |
| Interfaz en otro idioma sin rótulos | [Oficial] screen recordings |
| Se graba una app distinta de la que se envía | [Oficial] apps for other businesses |
| Mensajería con capturas en vez de una grabación del mensaje llegando a Instagram o Messenger | [Oficial] Permissions reference |

---

## 8. Lo que no está claro

- **Tamaño, formato y duración máximos del vídeo:** no están documentados.
- **Si los webhooks `comments` de Instagram llegan antes de la aprobación con cuentas con rol:** las fuentes oficiales se contradicen (§4). Hay que probarlo.
- **Si quick replies, ice breakers y menú persistente son obligatorios en `instagram_manage_messages`** o solo «si aplica».
- **Si Business Asset User Profile Access cubre el perfil de Instagram** o solo el de Messenger.
- **Por qué la página de respuestas privadas de Instagram pide `pages_messaging` y Human Agent:** parece un error de la documentación, pero hay que contar con ello. Si falta `pages_messaging` en el token de Instagram, la respuesta privada puede fallar.
- **Que Human Agent funcione con el login unificado de Instagram:** sigue pendiente, como se dijo en `03` y `04`.
- **Varias entradas de la Permissions reference tienen texto copiado de otros permisos** (`instagram_manage_comments`, `pages_messaging`). No sirven de plantilla literal.

## Fuentes

- Guía de envío (App Review): https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide
- Screen recordings: https://developers.facebook.com/docs/app-review/submission-guide/screen-recordings
- Common mistakes: https://developers.facebook.com/docs/app-review/submission-guide/common-mistakes
- Vídeo oficial «Creating screencasts for Meta App Review» (2024): https://developers.secure.facebook.com/videos/2024/creating-screencasts-for-meta-app-review/
- Permissions reference: https://developers.facebook.com/docs/permissions
- Features reference, Human Agent: https://developers.facebook.com/docs/features-reference/human-agent
- Features reference, Business Asset User Profile Access: https://developers.facebook.com/docs/features-reference/business-asset-user-profile-access
- Instagram Platform, App Review: https://developers.facebook.com/docs/instagram-platform/app-review
- Instagram Messaging, apps for other businesses: https://developers.facebook.com/documentation/business-messaging/instagram-messaging/app-review/apps-for-other-businesses
- Messenger Platform, App Review: https://developers.facebook.com/docs/messenger-platform/app-review
- Messenger Platform, overview (permisos y Facebook Login for Business): https://developers.facebook.com/documentation/business-messaging/messenger-platform/overview
- Access levels: https://developers.facebook.com/docs/graph-api/overview/access-levels
- Webhooks para Instagram: https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-instagram
- Campos de webhooks de Instagram: https://developers.facebook.com/documentation/instagram-platform/webhooks/fields
- Webhooks de Instagram Messaging: https://developers.facebook.com/docs/messenger-platform/instagram/features/webhook/
- Webhooks para Páginas: https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-pages
- Webhooks (general): https://developers.facebook.com/docs/graph-api/webhooks
- Respuestas privadas de Instagram: https://developers.facebook.com/docs/messenger-platform/instagram/features/private-replies
- Respuestas privadas de Messenger: https://developers.facebook.com/docs/messenger-platform/discovery/private-replies
- Callback de borrado de datos: https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback
- Data Use Checkup: https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/data-use-checkup
- Data access renewal, FAQ: https://developers.facebook.com/documentation/resp-plat-initiatives/data-access-renewal/faqs
- [Terceros] Chatwoot, Instagram app review: https://developers.chatwoot.com/self-hosted/instagram-app-review
- [Terceros] Guía de screencast (consultora): https://singhamandeep.com/meta-app-review-screencast-guide/
- [Terceros] Foro de Meta, error al subir el vídeo: https://developers.secure.facebook.com/community/threads/953076756848227
- [Terceros] Foro de Meta, webhook de comentarios con el botón Test: https://developers.secure.facebook.com/community/threads/818907743455411
