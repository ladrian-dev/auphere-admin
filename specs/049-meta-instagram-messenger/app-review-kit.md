# Kit de App Review de Meta: llamadas de prueba y screencasts

Spec 049, Requisito 6. App de Meta `957213733862330` (negocio Facelad, verificado). Fecha: 2026-10-29.

> **Qué se puede grabar hoy y qué no.** Meta pide ver cada permiso **en uso**. Los vídeos se graban en la **consola de partners** (donde el revisor conectará sus cuentas) cuando exista el round trip de las Historias 1 y 2, en staging o producción. Revisado el 2026-10-29 contra la documentación oficial: ver [auditoria-docs-oficiales.md](auditoria-docs-oficiales.md).

## 1. Reglas de grabación (valen para todos los vídeos)

| Regla | Valor |
|---|---|
| Resolución y duración | 1080p o más; 1 a 3 minutos por permiso |
| Audio | Sin audio. **Rótulos o subtítulos** que expliquen cada paso (Meta los pide) |
| Idioma | Inglés (interfaz de Meta en inglés durante la grabación) |
| Un vídeo por permiso | No reutilizar el mismo vídeo ni copiar descripciones entre permisos |
| Narrativa | Desde el negocio: «a customer writes, the business replies», no técnica |
| Recorrido mínimo | Cuenta sin sesión → login → **botón de inicio de sesión de Meta visible y conforme a su guía de marca** → pantalla de permisos de Meta con el permiso visible → uso del permiso → resultado visible |
| Datos | Solo cuentas de prueba. Sin teléfonos, correos ni nombres reales |
| Secretos | Nunca en pantalla: ni tokens (`EAA…`), ni `META_APP_SECRET`, ni `paging.next` de las respuestas de la API |
| Cómo grabar en Mac | `Cmd + Shift + 5` → «Grabar pantalla seleccionada». Cerrar notificaciones antes |

## 2. Activos de prueba (preparar una vez)

- [ ] Cuenta de Instagram **profesional** (Business o Creator) de prueba, **real** (Unified Login no admite usuarios de prueba de Meta), dentro de un **portfolio de negocio**, con **«Permitir acceso a los mensajes»** activado (Ajustes → Mensajes y respuestas del story → Herramientas conectadas). Sin él la API devuelve `(#200)`.
- [ ] Segunda cuenta de Instagram, personal, que hará de «cliente final».
- [ ] Página de Facebook de prueba, **publicada**, administrada por la persona evaluadora, con las tareas MESSAGING y MODERATE.
- [ ] Roles en la app: evaluador de Facebook para la persona evaluadora y **evaluador de Instagram** para la cuenta profesional (Roles → Evaluadores de Instagram; la cuenta acepta la invitación en Instagram). Con rol, los permisos funcionan sin aprobación.
- [ ] Partner de revisión en la consola de partners con Instagram y Messenger habilitados y un cliente de prueba con un agente simple (saludo + horario), nunca un cliente real.
- [ ] Revisor de Meta: instrucciones de prueba y una cuenta que no exija 2FA ni SMS (App settings → Basic → «Provide testing instructions»).
- [ ] Direcciones de privacidad, condiciones y eliminación de datos abren sin error y mencionan datos de Instagram y Messenger (App settings → Basic). Meta revisa la app entera en cada envío.

## 3. Permisos, descripción y guion

Los nombres con prefijo `instagram_business_` pertenecen a Instagram Login; con **inicio de sesión unificado** (decisión del 2026-10-29) los permisos son los `instagram_*`. Se piden solo los usados.

### 3.1 `instagram_basic`

**Use case description (EN):** Auphere lets small businesses answer their Instagram customers with an assistant. After the business owner connects their professional Instagram account, we read the account's username and profile picture to show the owner which account is connected and to label the conversations in their inbox.

**Screencast:** 1) Open the Auphere partner console, client «Meta Review Demo» → Channels. 2) Connect Instagram → log in with the test account (Instagram or Facebook). 3) Show the permission screen from Meta with basic profile access. 4) Return to Auphere: the connected account appears with username and photo.

**Prueba de llamada:** `GET /me/assigned_instagram_accounts` y `GET /{IG_ID}?fields=username,profile_picture_url` con el token del canal. **No** `GET /me`: con un token de usuario del sistema `/me` devuelve el usuario del sistema, no la cuenta.

### 3.2 `instagram_manage_messages`

**Use case description (EN):** The business's assistant answers direct messages that customers send to the business's Instagram account. A person writes first; Auphere reads the message and replies in the same conversation. We do not send unsolicited messages. A human on the team can take over the conversation at any time.

**Screencast:** 1) Personal account sends «Hi, what time do you open?» to the test business account. 2) Auphere inbox shows the message with the Instagram label. 3) The assistant's reply arrives in Instagram on the personal account. 4) Show the conversation in the inbox with both messages.

**Prueba de llamada:** envío real de la respuesta (`POST /{IG_ID}/messages`) y lectura del mensaje entrante por webhook.

### 3.3 `instagram_manage_comments`

**Use case description (EN):** When a customer comments on a post of the business, the assistant can reply to the comment in public and, if the customer asked for details, send them a private message referring to their comment. The business owner sees every comment and reply in the Auphere inbox.

**Screencast:** 1) Personal account comments «Price?» on a post of the test account. 2) Comment shows up in Auphere. 3) The reply appears under the comment in Instagram. 4) The private message arrives in the personal account's DMs.

**Prueba de llamada:** `POST /{comment-id}/replies` (respuesta pública) y `POST /{IG_ID}/messages` con `recipient.comment_id` (respuesta privada; una por comentario, dentro de 7 días).

### 3.4 Human Agent (función, etiqueta `human_agent`)

**Use case description (EN):** Auphere has an inbox where a real person from the business can take over a conversation. When the customer wrote more than 24 hours ago, only that person can still reply, up to 7 days after the customer's last message. The assistant never uses this tag; it is only available while a named team member has taken the conversation.

**Screencast:** 1) Show a conversation whose last customer message is older than 24 hours. 2) The assistant cannot reply (blocked, clear reason). 3) A team member presses «Take over», writes a reply. 4) The reply is delivered to the customer. 5) The audit log shows who took over.

**Aviso:** Meta revoca el permiso si detecta uso sin persona real. El guion tiene que mostrar a la persona y, si se usa el traspaso de conversación, que **la propiedad del hilo pasa a la bandeja** al escalar.

### 3.4b Business Asset User Profile Access (función)

**Use case description (EN):** When a customer writes to the business on Instagram or Messenger, Auphere reads the customer's name and profile picture so the business team can recognise who they are talking to in the inbox. We read only people who wrote to the business first, and we do not use the data for anything else.

**Screencast:** 1) A customer writes to the test account. 2) The Auphere inbox shows the conversation with the customer's name and photo.

**Prueba de llamada:** `GET /{IGSID}?fields=name,profile_pic` (Instagram) y `GET /{PSID}?fields=first_name,last_name,profile_pic` (Messenger) con el token del canal.

### 3.5 `pages_messaging`

**Use case description (EN):** Same flow as Instagram, for businesses that receive customer messages on their Facebook Page. A person writes to the Page on Messenger and the assistant replies, with a human takeover option.

**Screencast:** 1) Messenger account (tester) writes to the test Page. 2) Auphere inbox shows the message labelled «Messenger». 3) The reply arrives in Messenger.

### 3.6 `pages_manage_metadata`

**Use case description (EN):** We subscribe the connected Page to message events (webhooks) when the owner connects it and remove the subscription when the owner disconnects it.

**Screencast:** 1) Connect the Page from Auphere admin. 2) Show «Connected» status. 3) Disconnect it and show that messages no longer reach Auphere.

### 3.7 `pages_show_list`

**Use case description (EN):** During connection, the owner picks which of their Facebook Pages to connect. We show the list of Pages they manage.

**Screencast:** the page-picker step of the connection flow.

### 3.8 `pages_read_engagement`

**Use case description (EN):** We read the Page name and profile picture to show the business owner which Page is connected to Auphere.

**Screencast:** the connected Page card in the Channels list with the Page name and picture.

### 3.9 `business_management`

**Use case description (EN):** Auphere is a technology provider. We read the business portfolio the owner connects to list their catalogs and linked assets, and to confirm the business is verified before connecting channels.

**Screencast:** 1) Connection flow selecting the business. 2) The business name and verification status appear in the admin.

**Prueba de llamada ya hecha (2026-10-29):** `GET /342042661294231?fields=id,name,verification_status` → Facelad, verified. El contador de Meta tarda en reflejarlo; volver a mirar.

### 3.10 `catalog_management` (borrador ya preparado)

**Use case description (EN):** On a customer's WhatsApp number we show native product cards. We read the business's product catalogs to let the owner choose which one to link to the number and to search products when the assistant answers.

**Screencast:** 1) Admin → client → WhatsApp number → Catalog. 2) List of catalogs from Meta. 3) Link one. 4) A customer asks for a product and the assistant answers with the product card.

**Prueba de llamada ya hecha (2026-10-29):** lista de catálogos de Facelad y lectura de un producto.

## 4. Orden de envío recomendado

1. Esperar a que los contadores de Meta suban (≥ 1 llamada por permiso en 30 días; Meta tarda hasta 2 días en contarla).
2. Grabar los vídeos en orden: 3.2 → 3.3 → 3.4 → 3.1 → Messenger (3.5–3.8) → 3.9 → 3.10.
3. Revisar cada vídeo: sin secretos, sin datos reales, 1–3 min.
4. Pegar cada descripción en su permiso (texto distinto para cada uno) y subir su vídeo.
5. Enviar **una sola vez**. Una solicitud en revisión no se puede editar ni cancelar.

## 5. Antes de pulsar «Enviar»

- [ ] Cada permiso pedido tiene llamada exitosa en los últimos 30 días.
- [ ] Hay un vídeo por permiso y ninguno muestra secretos.
- [ ] Sobran cero permisos: quitar `instagram_content_publish`, `ads_management` y `ads_read` de la configuración de inicio de sesión de Instagram si no se usan.
- [ ] Instrucciones de prueba para el revisor, con cuentas listas.
- [ ] Privacidad, condiciones y eliminación de datos revisados.
- [ ] Los permisos de WhatsApp aprobados no se tocan.
- [ ] Messenger (lista oficial de revisión): Página publicada, webhook que responde 200 en menos de 20 s, tiempo medio de respuesta menor de 1 minuto, `messaging_policy_enforcement` suscrito en Página.
- [ ] La configuración «Auphere Messenger» incluye `pages_read_engagement`.
