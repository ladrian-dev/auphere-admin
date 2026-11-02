# Kit de grabación de los vídeos de Meta (2026-11-01)

Es el guion práctico para grabar hoy en **staging**. Los requisitos y los textos de uso están en `08-videos-revision-meta.md`. Aquí va solo lo que hay que hacer, en orden, con lo que la consola hace hoy.

## 0. Antes de la primera toma (15 min)

**Estado comprobado el 2026-11-01:**

| Qué | Estado |
|---|---|
| Instagram @somos.auphere | Conectado, «A todos». DM, traspaso, comentario con respuesta privada y pública: OK |
| Messenger, Página «Auphere» | Conectado, «A todos». DM, traspaso, comentario con respuesta privada y pública: OK |
| Ava | v1, sin borradores. Responde en el idioma de quien escribe: en inglés si se le escribe en inglés |
| Cuentas que escriben | Instagram `andresmatos.ux` y tu Facebook personal. Las dos tienen rol en la app: sus comentarios llegan |

**Preparar:**

1. **Todo en inglés (EE. UU.):**
   - Facebook: Settings → Language.
   - Instagram web: Más → Configuración → Idioma.
   - La app de Instagram del móvil.
   - La consola ya sale en inglés.
2. **Textos en español que se ven en la consola:**
   - Bajo «Meta Review Demo» ya pone «AI assistant agency»: el «Niche» se cambió el 2026-11-01.
   - Quedan en español y **no hay que enseñarlos**:
     - en Settings de Ava, «Agente Ava configurado antes de la fábrica de agentes.». Es parte de la versión de Ava: cambiarlo exige publicar una versión nueva, y la puerta la bloquea (INC-54);
     - en Business, el «Sector» y la sede «CEDE PRINCIPAL».
   - Ningún vídeo pasa por esas pantallas.
3. **Navegador:**
   - Ventana de 1440 px de ancho o menos, zoom al 100 %.
   - Una ventana sin pestañas personales a la vista y sin la barra de marcadores.
4. **Cursor grande:** Ajustes del Sistema → Accesibilidad → Pantalla → Tamaño del puntero.
5. **Grabación:** QuickTime (Archivo → Nueva grabación de pantalla) u OBS, a 1080p o más, sin audio. Móvil: iPhone Mirroring en el Mac, para que el móvil y la consola salgan en la misma toma.
6. **Dos sesiones de la consola:**
   - Socio (`contacto@auphere.com`), para conectar canales.
   - **Cliente de «Meta Review Demo»** (consola del cliente), para la bandeja. La de socio no enseña el texto de los mensajes: Clients → Conversations solo da métricas («Message content never leaves the system»).
   - Las dos empiezan **con la sesión cerrada** en cada vídeo que lleva login.
7. **Nada sensible en pantalla:**
   - nada de DevTools, tokens, el `code` de la URL de Meta ni teléfonos;
   - la contraseña tecleada sale tapada: que no se vea el gestor de contraseñas;
   - cuidado con la barra de direcciones al volver de la ventana de Meta.

## 1. Orden de grabación

Se graba el **bloque A** (login y conexión) una vez por canal y se reutiliza al montar.

| # | Vídeo | Para el campo | Cuándo |
|---|---|---|---|
| 1 | IG-1 Conectar Instagram | `instagram_basic` | Ahora |
| 2 | IG-2 DM y traspaso | `instagram_manage_messages` | Ahora |
| 3 | IG-3 Comentarios | `instagram_manage_comments` | Ahora |
| 4 | BM Activos del negocio | `business_management` | Sale del bloque A de IG-1 y MS-1 |
| 5 | MS-1 Conectar Messenger | `pages_show_list`, `pages_manage_metadata` | Ahora |
| 6 | MS-2 Mensajes de Messenger | `pages_messaging` | Ahora, pero **con otra cuenta o en otra conversación**: el hilo de tu Facebook personal se guarda para HA |
| 7 | MS-4 Comentarios de la Página | `pages_read_user_content`, `pages_manage_engagement` | Ahora |
| 8 | MS-3 Contenido de la Página | `pages_read_engagement` | Ahora (ver §3) |
| 9 | PROF Nombre y foto de quien escribe | Business Asset User Profile Access | Sale de las tomas de IG-2 y MS-2 |
| 10 | HA Human Agent | Human Agent | Sin toma propia: sale de IG-2 |

**Sobre HA:** ya no hay que reservar ningún hilo de más de 24 h (ver su apartado). MS-2 y MS-4 pueden usar la cuenta personal.

## 2. Guion por vídeo

Cada vídeo empieza con un rótulo de 2 s: `Permission: <nombre>`. Los rótulos de las escenas van en inglés y son cortos.

### IG-1 · `instagram_basic` (45-60 s)

1. Consola de socio con la sesión cerrada → login. Rótulo: «Agency signs in to Auphere».
2. Clients → Meta Review Demo → **Connect Instagram**. Que se lea el aviso «Whoever manages the account or Page must give Auphere explicit access…»: es el que pide `business_management`.
3. En la ventana de Meta:
   - elegir **@somos.auphere**;
   - pantalla de permisos: **zoom** en la lista;
   - aceptar.
4. Vuelta a la consola: tarjeta **@somos.auphere** «Active». **Zoom** en el usuario y la foto.
   - Rótulo: «We read the account id, username and profile picture to show which account is connected».

### IG-2 · `instagram_manage_messages` (2-3 min)

1. Móvil (Instagram de `andresmatos.ux`): DM a @somos.auphere: «Hi! What do you do?».
2. La respuesta de Ava llega al móvil en unos 5 s. Rótulo: «Automated reply in under 30 s». Que se vea la hora.
3. Consola del cliente → bandeja: la conversación con el nombre y la foto de quien escribe, y los dos mensajes.
4. Móvil: «Can I talk to a person, please?». Ava responde «I'm passing you to someone on the team…».
5. Bandeja: la conversación sale en «Waiting for a person». La persona toma el control y escribe una respuesta, que llega al móvil.
   - Rótulo: «A team member takes over and replies from the Auphere inbox».
6. Devolver la conversación al agente.
7. **No grabar «mensaje anulado».** Hoy la consola no lo refleja (INC-56). El texto del formulario no puede decir que lo hace.

### IG-3 · `instagram_manage_comments` (1,5-2 min)

1. Móvil o web, cuenta `andresmatos.ux`: comentar en una publicación de @somos.auphere «How much does it cost?».
2. A los pocos segundos:
   - debajo del comentario sale «We sent you a private message 📩» de @somos.auphere (respuesta pública);
   - en los DM llega la respuesta privada, con la línea de Instagram «somos.auphere messaged you about a comment you made on their post».
3. Bandeja: la conversación que abrió el comentario, con el texto del comentario.
4. Rótulo: «Comment received via webhook → public reply under the comment + one private reply».
5. **Después de grabar, borra ese comentario** (y la respuesta de Auphere).

### BM · `business_management` (45-60 s)

- Montaje con los bloques A de IG-1 y MS-1:
  - el aviso de acceso explícito en la consola;
  - la elección del activo del negocio en la ventana de Meta;
  - la concesión.
- Rótulo: «The admin explicitly grants Auphere access to the business's Page and Instagram account».

### MS-1 · `pages_show_list` y `pages_manage_metadata` (1,5 min)

1. Consola de socio → **Connect Messenger** → ventana de Meta:
   - la **lista de Páginas** (zoom);
   - elegir «Auphere»;
   - aceptar.
2. La tarjeta «Auphere · Messenger · Active». Rótulo: «Auphere subscribes the Page to the messages and feed webhooks».
3. Un mensaje de Messenger que llega a la bandeja. Usa **otra cuenta** (ver HA) o deja esta escena para MS-2.
4. Opcional, al final del día: «Disconnect» y un mensaje que ya no llega. Después hay que volver a conectar la Página y comprobar «A todos» y la línea pública de comentarios.

### MS-2 · `pages_messaging` (1,5-2 min)

- Igual que IG-2, pero en Messenger con la Página «Auphere».
- Usa una cuenta distinta de tu Facebook personal, o un hilo que no sea el que se guarda para HA.

### MS-4 · `pages_read_user_content` y `pages_manage_engagement` (dos cortes del mismo rodaje)

1. Facebook (tu cuenta personal, que tiene rol): comentar en una publicación de la Página «Auphere» «Do you work with dental clinics?».
2. Corte para `pages_read_user_content`:
   - la conversación en la bandeja con el texto del comentario y el nombre de quien comenta;
   - rótulo: «Auphere reads the comment (text and author) from the feed webhook».
3. Corte para `pages_manage_engagement`:
   - recargar la publicación en Facebook: debajo sale «We sent you a private message 📩» publicado **como la Página**;
   - rótulo: «Public reply published as the Page».
4. En Messenger llega la respuesta privada.
5. Borrar el comentario y la respuesta después.
6. **Ojo con HA:** la respuesta privada abre un hilo nuevo en Messenger con tu cuenta. Si es el mismo hilo que se guarda para HA, le quita la antigüedad. Para no arriesgar, este comentario lo hace otra cuenta con rol, o se graba MS-4 **después** de HA.

### MS-3 · `pages_read_engagement` (45 s)

- La tarjeta del canal con el nombre de la Página.
- La conversación del comentario en la bandeja.
- **Comprobar en la primera toma si la bandeja enseña la publicación junto al comentario** (ver §3). Si no la enseña, el vídeo se apoya en el nombre de la Página y en el comentario, y el texto de uso dice solo eso.

### PROF · Business Asset User Profile Access (45 s)

- Montaje de IG-2 y MS-2: en la bandeja se ven **el nombre y la foto** de quien escribe, con zoom.
- Rótulo: «We show the customer's name and profile picture so the team knows who they are talking to».

### HA · Human Agent (1-1,5 min): sin toma propia

**Cambio del 2026-11-02.** Meta rechaza la etiqueta antes de aprobarla: «(#100) Cannot tag messages with 'HUMAN_AGENT' without prior approval» (INC-59). No se puede grabar una respuesta real pasadas 24 h. Según `08`, §3.3, con `instagram_manage_messages` en el mismo envío vale el vídeo general.

- Se saca de la parte de IG-2 en que una persona toma el control y responde.
- Rótulo: «A named team member takes over and replies. After approval, replies between 24 h and 7 days use the HUMAN_AGENT tag».
- El texto del formulario explica que la etiqueta aún no puede enseñarse porque Meta la bloquea hasta aprobarla.

## 3. Huecos que afectan a los vídeos

| Hueco | Vídeo | Qué hacer hoy |
|---|---|---|
| Un DM anulado no se refleja: el evento `is_deleted` se lee y se descarta (INC-56) | IG-2 | No grabarlo ni prometerlo en el texto. Construirlo antes de enviar si Meta lo pide |
| La consola de socio no enseña el contenido de las conversaciones | IG-2, IG-3, MS-2, MS-4, PROF, HA | Grabar la bandeja con la sesión del cliente. Las instrucciones al revisor tienen que darle esa entrada |
| No está comprobado que la bandeja enseñe la publicación junto al comentario | MS-3, IG-3 | Mirarlo en la primera toma |
| Ice breakers, quick replies y menú persistente no existen | IG-2 | Decirlo en el texto, o construirlos si Meta los exige (ver `08` §8) |

## 4. Llamadas con éxito (regla de los 30 días)

| Permiso | Llamada | Fecha |
|---|---|---|
| `instagram_basic` | Lectura de la cuenta al conectar | 2026-11-01 |
| `instagram_manage_messages` | Respuestas de Ava por DM | 2026-11-01 |
| `instagram_manage_comments` | Respuesta pública `/{comment-id}/replies` | 2026-11-01 |
| `pages_show_list`, `pages_manage_metadata` | Conexión de Messenger y `subscribed_apps` | 2026-10-31 |
| `pages_messaging` | Respuestas de Ava por Messenger y respuesta privada a comentarios | 2026-11-01 |
| `pages_read_engagement` | Lectura de la Página al conectar | 2026-10-31 |
| `pages_read_user_content` | `GET /{comment-id}` | 2026-11-01 03:19 UTC |
| `pages_manage_engagement` | `POST /{comment-id}/comments` | 2026-11-01 03:19 UTC |
| `business_management` | Lectura de los activos del portfolio al conectar | 2026-11-01 |

Meta tarda hasta 2 días en mostrarlas en el Dashboard (Revisión de la app → Permisos y funciones).

## 5. Después de grabar

1. Borrar los comentarios de prueba de las tomas.
2. Pasar Instagram y Messenger a «Sin configurar». WhatsApp, si se quiere, también. Lo hago cuando me digas.
3. Montar con un vídeo por campo del formulario y revisar cada uno entero. Exportar en MP4 (H.264), de menos de 100 MB.
