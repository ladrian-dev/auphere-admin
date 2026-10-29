# Instrucciones para el revisor de Meta: Instagram y Messenger

Se pegan en App Dashboard → Configuración de la app → Básica → «Agregar o actualizar instrucciones». Van en el mismo envío que el kit ([app-review-kit.md](app-review-kit.md)). Si el envío también lleva `catalog_management` y `business_management`, se añaden detrás de las de [app-review-reviewer-instructions.md](app-review-reviewer-instructions.md).

## Antes de pegarlas

Lo compruebas o lo creas tú:

| # | Requisito | Por qué |
|---|---|---|
| 1 | Partner de revisión en la consola de partners con **Instagram y Messenger encendidos** (panel → Partners → Módulos → Canales en beta) y un cliente «Meta Review Demo» con el agente publicado | El revisor conecta sus propias cuentas; si el partner no tiene el canal, no hay botón |
| 2 | Cuenta de revisor en `console.auphere.com`, sin 2FA ni SMS, que solo ve ese partner | Meta usa sus propias cuentas de Meta, pero necesita entrar en la app |
| 3 | La app de Meta con la configuración «Auphere Messenger» incluyendo `pages_read_engagement`, y `messaging_policy_enforcement` suscrito en Página | Lista oficial de revisión de Messenger |
| 4 | Una llamada exitosa por permiso en los últimos 30 días, con 2 días de margen | Regla oficial: el botón de solicitar sale gris hasta que Meta cuenta la llamada |
| 5 | El webhook de Instagram y de Página apuntando al entorno donde está el partner de revisión (producción) | Una sola URL por app para estos objetos |

> **La contraseña no se pega aquí ni en el chat.** Se escribe directamente en el campo de Meta.

## Campo «¿Dónde podemos encontrar la app?»

```
https://console.auphere.com/login
```

## Campo «Instrucciones»

```
ABOUT AUPHERE
Auphere is a multi-tenant SaaS registered with Meta as a Tech Provider (business portfolio: Facelad, verified). Small businesses connect their Instagram professional account and their Facebook Page to Auphere; an assistant answers the messages their customers send, and a person of the business can take over any conversation. Partners (agencies) manage their clients from the Auphere partner console.

TEST CREDENTIALS
URL:      https://console.auphere.com/login
Email:    meta-reviewer@auphere.com
Password: (entered in this field only)
The account only sees one demo client, "Meta Review Demo". No payment or download is needed.

HOW TO CONNECT (both channels)
1. Sign in. Open Clients > "Meta Review Demo" > Channels.
2. Click "Connect Instagram" (or "Connect Messenger"). Meta's login window opens (Facebook Login for Business). Log in with your Instagram professional test account or with Facebook, select the account / Page and accept the permissions.
3. Back in Auphere, the card shows the account (@username) or the Page as "Active".
To stop, the "..." menu on the card > "Disconnect": Auphere unsubscribes the account, deletes its access token at once and erases the messages received through it within 30 days.

PERMISSIONS AND WHERE TO SEE THEM

instagram_basic — step 3: we read the account's username and picture to show which account is connected.

instagram_manage_messages — from another Instagram account, send a DM to the connected account (e.g. "What time do you open?"). The assistant answers in the same conversation within a minute. The conversation appears in Auphere's inbox with the label "Instagram". Auphere never starts a conversation: the person writes first.

instagram_manage_comments — comment on a post of the connected account (e.g. "Price?"). The assistant sends ONE private reply to that comment (a DM referring to it) and, if configured, a short public reply under the comment.

pages_show_list, pages_manage_metadata, business_management — step 2-3 of "Connect Messenger": we list the Pages you manage, subscribe the selected one to message webhooks (and unsubscribe it on Disconnect), and read the business portfolio the asset belongs to.

pages_messaging — send a Messenger message to the connected Page from a tester account. The assistant answers in the same conversation.

pages_read_engagement — step 3 of "Connect Messenger": we read the Page's name and picture for the card.

Human Agent — in Auphere's inbox, open a conversation whose last customer message is older than 24 hours. The assistant cannot answer it. Press "Take over" and write a reply: it is delivered with the HUMAN_AGENT tag, up to 7 days after the customer's last message. The audit log shows who took over. The tag is never used by the assistant.

Business Asset User Profile Access — in the inbox, conversations show the customer's name and picture as returned by the platform, only for people who wrote to the business.
```

## Comprobación antes de enviar

- [ ] Hecho el recorrido completo en ventana privada, como revisor, en producción.
- [ ] El texto coincide con lo que se ve: botones, nombres de menú y estados.
- [ ] La política de privacidad (`auphere.com/en/privacy`) menciona Instagram y Messenger y el borrado en 30 días.
