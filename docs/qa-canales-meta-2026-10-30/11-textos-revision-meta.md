# Textos para el envío a la revisión de Meta

Fecha: 2026-11-02. App `957213733862330`. Los textos que se pegan en Meta están en inglés, dentro de los bloques de código. Cuentan solo lo que la app hace hoy y lo que enseñan los vídeos: si algo cambia, hay que cambiar también el texto.

**Nada de esto se ha enviado.** El envío lo decide y lo hace el owner.

## 1. Antes de enviar

### Bloqueantes

| # | Qué | Por qué | Quién |
|---|---|---|---|
| 1 | **Cuentas del revisor:** una de partner y otra de cliente de «Meta Review Demo», sin 2FA | Conectar se hace con la de partner, y la bandeja solo se ve con la de cliente. Si el revisor no puede entrar, Meta rechaza **todo** el envío | Owner. La contraseña se escribe solo en Meta |
| 2 | **Apagar el aparcamiento de staging** mientras dure la revisión | De 03:00 a 09:00 (Madrid) staging no responde (`staging_parking.tf`), y el revisor puede estar en cualquier huso horario | Decisión del owner. Cambio de infraestructura |
| 3 | **Instagram y Messenger siguen en «Everyone»** durante la revisión. Los webhooks siguen apuntando a staging | Si se pasan a «Sin configurar», Ava no responde al revisor. El coste: puede responder a personas ajenas a la revisión | Owner |
| 4 | **Saldo:** OpenAI con recarga o alerta, y crédito del cliente y del partner | Sin saldo Ava deja de responder (pasó el 2026-11-02) | Owner |
| 5 | **Llamadas con éxito** de cada permiso en los últimos 30 días, vistas en el Dashboard | Requisito de Meta. Las llamadas tardan hasta 2 días en aparecer | Comprobarlo en el Dashboard |

### Decisiones del owner (2026-11-02)

| # | Pregunta | Decisión | Estado |
|---|---|---|---|
| 1 | Cuentas del revisor | Las del owner, de partner y de cliente | Falta poner contraseñas de un solo uso y comprobar que no piden 2FA |
| 2 | Aparcamiento de staging | Apagado | Hecho: `ScheduledScalingSuspended=true` en los 7 servicios. Al terminar la revisión, volver a `false` |
| 3 | Canales durante la revisión | Siguen en «Everyone» | Hecho |
| 6 | `messaging_policy_enforcement` | Suscribirlo | Hecho |
| 7 | DM anulado (INC-56) | Construirlo | En develop |
| 8 | Publicación en la bandeja | Construirla | En develop. Falta probarla con Meta real |
| 9 | IG-3 | Regrabarlo en una sola toma | Pendiente |
| 10 | Human Agent y nombre y foto | Pedirlos | Añadidos al borrador |
| — | `catalog_management` | Se queda en este envío | Falta el número por Cloud API, comprobar el acceso al catálogo, su vídeo y su texto |

**Llamadas en el Dashboard (2026-11-02):** `pages_read_user_content` y `pages_manage_engagement` siguen en 0 de 1, aunque se ejecutaron. Probablemente haya que hacerlas desde Graph API Explorer. Human Agent y Business Asset User Profile Access salen con 0, y no está claro que Meta las exija por ser funciones.

**Catálogo:** «Catálogo_productos» (`1472326088011439`), portfolio «Andres Matos», 4 productos aptos. El número nuevo tiene que ir en ese portfolio. Ava no tiene las habilidades de catálogo en su versión activa, y publicar una versión nueva choca con INC-54.

## 2. Qué vídeo va en cada campo

Carpeta: `~/Desktop/META-VIDEOS/editados/`.

| Campo del formulario | Vídeo |
|---|---|
| `instagram_basic` | `IG-1_instagram_basic.mp4` |
| `instagram_manage_messages` | `IG-2_instagram_manage_messages.mp4` |
| `instagram_manage_comments` | `IG-3_instagram_manage_comments.mp4` |
| `business_management` | `BM_business_management.mp4` |
| `pages_show_list` | `MS-1_pages_show_list_pages_manage_metadata.mp4` |
| `pages_manage_metadata` | `MS-1_pages_show_list_pages_manage_metadata.mp4` |
| `pages_messaging` | `MS-2_pages_messaging.mp4` |
| `pages_read_engagement` | `MS-3_pages_read_engagement.mp4` |
| `pages_read_user_content` | `MS-4a_pages_read_user_content.mp4` |
| `pages_manage_engagement` | `MS-4b_pages_manage_engagement.mp4` |
| Human Agent | `HA_human_agent.mp4` |
| Business Asset User Profile Access | `PROF_business_asset_user_profile_access.mp4` |

## 3. Texto de cada permiso

### `instagram_basic`

```
Auphere is a customer-messaging platform that agencies use to run an AI assistant and a team inbox for their client businesses. When a business connects its Instagram professional account through Facebook Login for Business, we read the account's id and username. The console shows the username on the channel, so the business can confirm that the right account is connected. The id routes each incoming message to the correct client workspace. Without this permission we could not identify which account the business connected.
```

### `instagram_manage_messages`

```
Auphere is both an automated experience and a custom inbox for Instagram Direct.

Automated: an incoming DM reaches Auphere through the messages webhook, and the AI assistant answers with the Send API, usually within seconds.

Custom inbox: every conversation appears in the Auphere inbox of the client console. To read it, open the conversation. To reply by hand, click "Take over", write the message and send it. To return it to the assistant, click "Give back to the agent". To remove a conversation from the inbox, use the "..." menu ("Clear chat" or "Delete chat").

Human handoff: when a customer asks for a person, the assistant says so and the conversation shows as "Needs a human" until a team member takes over. To test it, write "I'd like to talk to a person from the team, please."

Unsent messages: when a customer unsends a message, Auphere receives the webhook, removes its content, and the inbox shows "The contact deleted this message". The assistant no longer takes it into account. To test it, unsend a DM and open the conversation.

Auphere does not use ice breakers, quick replies or a persistent menu on Instagram.

Without this permission a business could not answer its customers' Instagram messages from Auphere.
```

INC-56 quedó construido el 2026-11-02. Si IG-2 no se regraba, el vídeo no enseña esta parte.

### `instagram_manage_comments`

```
Auphere lets a business answer comments on its own Instagram posts. When a customer comments, we receive the comments webhook and the comment appears in the Auphere inbox, below the post it was left on. The assistant then sends one private reply to the commenter within 7 days, and posts a short public reply under the comment if the business has set one on the channel page. The business can turn comment answering on or off for each channel. Auphere does not hide or delete comments. Without this permission, businesses could not answer questions left in comments from Auphere.
```

### `business_management`

```
business_management is requested as a dependency of pages_messaging, pages_show_list and instagram_manage_messages. Agencies connect assets that belong to their clients' business portfolios. During Facebook Login for Business, the admin selects the business portfolio, the Page and the Instagram account and explicitly grants access. The console reminds the admin of this while the Meta window is open: "Whoever manages the account or Page must give Auphere explicit access to the business's assets in that window." Auphere reads only the assets that were shared with it, to find the Page and the Instagram account the admin selected.
```

### `pages_show_list`

```
When a business clicks "Connect Messenger", the admin chooses the Page that Auphere will answer for from the list of Pages they manage, and we verify that the admin manages the selected Page before connecting it. The connected Page then appears by name in the console. Without this permission the admin could not choose a Page.
```

### `pages_manage_metadata`

```
After the admin connects a Page, Auphere subscribes it to webhook fields with POST /{page-id}/subscribed_apps, including messages and feed, so that customer messages and comments reach the business's inbox. When the business disconnects the channel, we remove the subscription. There is no separate switch: the subscription happens when the Page is connected. Without this permission, Auphere would not receive messages or comments for the Page.
```

### `pages_messaging`

```
Customers message the business's Facebook Page. The message reaches Auphere through the webhook, appears in the Auphere inbox, and the AI assistant answers with the Send API. A team member can take over from the inbox at any time and reply by hand. We also use this permission to send one private reply to a person who commented on a Page post, within 7 days, as Messenger's private replies allow. All conversations are started by the customer. Without this permission a business could not answer its customers on Messenger from Auphere.
```

### `pages_read_engagement`

```
We read the connected Page's metadata, including its name, to show the admin which Page is connected to the client's assistant in the Auphere console. We also read the content of the post a customer commented on (its text, picture and link) and show it above the comment in the inbox, so the team knows what the comment refers to. Without this permission the business could not confirm that the right Page is connected or see which post a comment belongs to.
```

La bandeja enseña la publicación desde el 2026-11-02 (`inbox_comment_post`). Hay que confirmarlo en staging con Meta real antes de grabar MS-3.

### `pages_read_user_content`

```
When a customer comments on one of the business's Page posts, Auphere receives the feed webhook. The webhook event does not always carry the comment's text, so we read the comment with GET /{comment-id}?fields=message,from. The comment, with its text and author, appears in the business's Auphere inbox next to the reply, and the assistant uses the text to answer. Without this permission the business could not see or answer comments on its Page from Auphere.
```

### `pages_manage_engagement`

```
If the business sets a public reply on the channel page, Auphere posts that short line under the customer's comment with POST /{comment-id}/comments, published as the Page, so that other visitors can see the customer was answered. The full answer goes to the customer as one private reply. Auphere does not edit or delete comments, and does not like them. Without this permission the business could not acknowledge comments publicly from Auphere.
```

### Human Agent

```
Auphere's AI assistant only replies inside the standard 24-hour window. Some requests need a person: a complaint, a change to a booking, a question the assistant cannot answer. These often arrive while the business is closed, for example on a Friday night, so the team may need up to 7 days to reply. In those cases a team member takes over the conversation in the Auphere inbox and replies by hand, with the HUMAN_AGENT tag. The tag is added only to messages written by a person. It is never used by the assistant or for promotional content.

About the video: Meta refuses this tag before approval ("Cannot tag messages with 'HUMAN_AGENT' without prior approval"), so we cannot show a real reply after 24 hours. The video shows the same flow inside the 24-hour window: a person takes over from the inbox and the reply reaches the customer.
```

### Business Asset User Profile Access

```
When a customer writes to the business's Page or Instagram account, Auphere reads the person's name and profile picture so that the team can recognise who they are talking to in the inbox. The video shows the name and picture in the inbox, for Instagram and for Messenger. We do not use these fields for anything else, and we do not share them outside the business's workspace.
```

## 4. Instrucciones para el revisor

Van en App Dashboard → Configuración de la app → Básica → Sitio web → «Agregar o actualizar instrucciones». **Las contraseñas se escriben solo en el panel de Meta**, nunca aquí ni en el chat.

**Pendiente de comprobar:** hay que seguir estos pasos en una ventana privada con las dos cuentas del revisor antes de enviar. Un paso roto rechaza todo el envío. Tampoco está comprobado qué pasa cuando un revisor sin rol en la app escribe o comenta antes de la aprobación: Meta puede no entregar esos eventos.

### ¿Dónde podemos encontrar la app?

```
https://console.staging.auphere.com/login
```

### Instrucciones de acceso

```
ABOUT AUPHERE
Auphere is a web console that agencies use to run an AI assistant and a team inbox for their client businesses on Instagram and Messenger. Auphere sign-in uses email and password. Facebook Login for Business is only used to connect a business's assets.

TEST ACCOUNTS
Both use the same URL. No payment or download is needed.
1) Agency account, to connect channels. Email: contacto@auphere.com. Password: [ENTERED IN THIS FIELD ONLY].
2) Client account, to read the inbox. Email: andrese.matosm@gmail.com. Password: [ENTERED IN THIS FIELD ONLY].

CONNECT INSTAGRAM OR MESSENGER (agency account)
1. Sign in. Open Clients > "Meta Review Demo" > Agents > "Ava" > Channels > "Add another channel".
2. Choose Instagram or Messenger and click the connect link. A Facebook Login for Business window opens.
3. Log in with your own Facebook account, select a business portfolio and the Page or Instagram professional account you manage, and grant the requested permissions.
4. Back in the console, the channel appears with its username or Page name. Open it and, under "Who it answers", choose "Everyone". Under "Comments", keep "Answer comments" on and, if you want to test the public reply, write a line under "Public reply under the comment" and save.

MESSAGES (client account)
5. From another account, send a DM to the connected account: "What does Auphere do?". The assistant replies within seconds.
6. Sign in with the client account and open Inbox. The conversation shows the customer's name and profile picture, and a logo with its channel. You can filter by channel.
7. Write "I'd like to talk to a person from the team, please." The conversation shows "Needs a human".
8. In the inbox, click "Take over", write a reply and send it. It reaches the customer. Click "Give back to the agent" to return it to the assistant.

COMMENTS
9. From another account, comment "How much does it cost?" on a post of the connected account. The comment appears in the inbox, and the assistant sends one private reply. If you set a public reply in step 4, it appears under the comment.

EXAMPLE ACCOUNTS
The channels @somos.auphere (Instagram) and the Page "Auphere" (Messenger) are already connected to this client and answer everyone, if you prefer to write to them instead of connecting your own.

HUMAN AGENT
Replies written by a person after 24 hours use the HUMAN_AGENT tag. Meta refuses this tag until the feature is approved, so a reply after 24 hours fails with a clear message until then.

WHAT WE DO NOT DO
We do not send unsolicited messages, we do not use Meta data for advertising or profiling, and we do not combine data across businesses. Privacy policy, including how to ask for data deletion: https://www.auphere.com/en/privacy
```

### Pagos

```
N/A. The demo client is provided free of charge for the review. Auphere is invoiced to businesses outside the app; no in-app purchase is needed to complete any step.
```

### Descarga

```
N/A. Auphere is a web application; nothing has to be downloaded.
```

### Restricción geográfica

```
N/A. The app is accessible globally for review purposes.
```

## 5. Formulario de mensajería de Instagram

| Pregunta | Respuesta |
|---|---|
| Tipo de experiencia | Las dos: «automated experience» y «custom inbox» |
| Plataforma | Website, con `https://console.staging.auphere.com/login` |
| Casos de uso | Los del texto de `instagram_manage_messages` |

## 6. Después de enviar

- No tocar «Meta Review Demo»: ni desconectar canales ni cambiar a Ava.
- Vigilar el saldo y la bandeja mientras dure la revisión.
- Cuando Meta responda: quitar el mensaje provisional de Human Agent si se aprueba, y decidir el paso de los webhooks a producción.
