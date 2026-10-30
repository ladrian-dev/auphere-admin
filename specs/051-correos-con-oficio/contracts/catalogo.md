# Contrato: el catálogo de correos

Qué correos envía la plataforma, de qué plantilla sale cada uno y qué dice. **La versión inicial del texto vive aquí; la vigente, en Resend** (D1). Si alguien cambia una plantilla en el panel, este documento no se actualiza: la red es la comprobación de plantillas (R7.1), que verifica variables y reglas, no palabras.

Inventario de partida: 21 correos en `develop@c99aed95`, recogido el 2026-10-30 (ver «Origen» en `../spec.md`). Quedan en **20 plantillas**: 19 para clientes y partners, en español y en inglés, y una interna solo en español. En total, **39 alias**.

**Revisión del owner del 2026-10-30** (segunda pasada):

- los alias empiezan por `auphere-`;
- cada correo sale en el idioma de la cuenta de quien lo recibe, cuando se sabe;
- las direcciones de Auphere van en inglés;
- no hay línea de «por qué lo recibes»;
- no se habla de «dar de baja las máquinas»;
- el texto lo escribe un profesional para un usuario común.

## Convenciones

- **Alias**: `auphere-<plantilla>-<es|en>`. El código envía por alias.
- **Idioma**: el de la cuenta de consola del destinatario (`console_auth.principals.locale`). Si no tiene cuenta, el que se sepa por otra vía (el alta lo trae en la petición; la invitación de equipo usa el de quien invita). Si no se sabe nada, español. Un correo a varias personas sale **una vez por idioma**.
- **Variables**: en mayúsculas. ★ = enlace de acción: es lo único que el modo de registro de staging escribe además de los metadatos (R1.1).
- **Asunto**: lo construye el código en el idioma del envío (R2 de `research.md`). La plantilla guarda el mismo como valor por defecto.
- **Remitente**: `billing` = `Auphere <billing@auphere.com>` (recibos y cobros); `notifications` = `Auphere <notifications@auphere.com>` (todo lo demás). **Respuestas** a `support@auphere.com`, salvo la petición interna de borrado.
- **Estructura de todos los correos externos**:
  1. Logo.
  2. Titular corto.
  3. «Hola,» / «Hi,».
  4. Uno o dos párrafos.
  5. Un botón, si hay algo que hacer.
  6. Los detalles prácticos (plazo, qué pasa si no haces nada).
  7. En los correos con enlace de un solo uso, el enlace en texto: «Si el botón no funciona, copia y pega este enlace en tu navegador:» / «If the button doesn't work, copy and paste this link into your browser:».
  8. La firma «Un saludo, / El equipo de Auphere» o «Best regards, / The Auphere team».
  9. Un pie mínimo: «Auphere · auphere.com».
- **Fechas**: «6 de noviembre de 2026» / «November 6, 2026». **Meses**: «octubre de 2026» / «October 2026». **Importes**: `US$1,234.56`.

---

## Cuentas y accesos

### 1 · `team_invite` → `auphere-team-invite-{es,en}`

Sustituye a los correos 1 (script de alta de pilotos) y 4 (invitación desde Equipo). **Arregla** que el 4 no llevaba enlace pulsable.

| | |
|---|---|
| Para · idioma | la persona invitada · el de su cuenta si ya tiene una; si no, el de quien invita |
| Negocio · remitente | partner · notifications |
| Variables | `INVITER` · `PARTNER_NAME` · `ROLE_LABEL` (es: Propietario, Administrador, Constructor, Analista, Facturación; en: Owner, Admin, Builder, Analyst, Billing) · `EXPIRES_ON` · `ACCEPT_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `{quien invita} te ha invitado a unirte a {partner} en Auphere` | `{inviter} invited you to join {partner} on Auphere` |
| Previsualización | Acepta la invitación antes del {{{EXPIRES_ON}}}. | Accept the invitation before {{{EXPIRES_ON}}}. |
| Titular | Te han invitado a {{{PARTNER_NAME}}} | You're invited to join {{{PARTNER_NAME}}} |
| Cuerpo | {{{INVITER}}} te ha invitado a formar parte del equipo de {{{PARTNER_NAME}}} en Auphere con el rol de {{{ROLE_LABEL}}}.<br><br>Para unirte, solo tienes que aceptar la invitación. | {{{INVITER}}} has invited you to join the {{{PARTNER_NAME}}} team on Auphere with the {{{ROLE_LABEL}}} role.<br><br>To join, just accept the invitation. |
| Botón | Aceptar la invitación | Accept invitation |
| Detalle | La invitación es válida hasta el {{{EXPIRES_ON}}}. Si no conoces a quien te ha invitado o no esperabas este mensaje, puedes ignorarlo. | The invitation is valid until {{{EXPIRES_ON}}}. If you don't know who sent it or weren't expecting it, you can ignore this email. |

### 2 · `client_invite` → `auphere-client-invite-{es,en}`

Sustituye al correo 6. Como hoy, **no nombra al partner** (spec 030).

| | |
|---|---|
| Para · idioma | una persona del negocio cliente · el de su cuenta si ya tiene una |
| Negocio · remitente | cliente · notifications |
| Variables | `CLIENT_NAME` · `EXPIRES_ON` · `ACCEPT_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Ya puedes acceder a la consola de {cliente}` | `Your access to the {client} console is ready` |
| Previsualización | Crea tu contraseña para entrar por primera vez. | Create your password to sign in for the first time. |
| Titular | Tu acceso a la consola de {{{CLIENT_NAME}}} | Your access to the {{{CLIENT_NAME}}} console |
| Cuerpo | Te hemos dado acceso a la consola de {{{CLIENT_NAME}}} en Auphere. Desde ella puedes ver cómo atiende tu agente, cuánto consume y, si la tienes activada, la bandeja con tus conversaciones.<br><br>Para entrar por primera vez, crea tu contraseña. | You now have access to the {{{CLIENT_NAME}}} console on Auphere. There you can see how your agent is handling conversations, how much it uses and, if it's turned on, the inbox with your conversations.<br><br>To sign in for the first time, create your password. |
| Botón | Crear mi contraseña | Create my password |
| Detalle | Este enlace solo se puede usar una vez y es válido hasta el {{{EXPIRES_ON}}}. Si no esperabas este correo, puedes ignorarlo. | This link can only be used once and is valid until {{{EXPIRES_ON}}}. If you weren't expecting this email, you can ignore it. |

### 3 · `signup_link` → `auphere-signup-link-{es,en}`

Sustituye al correo 7, que solo era el enlace, sin una frase.

| | |
|---|---|
| Para · idioma | quien pide el alta como partner · el que se eligió en el formulario |
| Negocio · remitente | ninguno · notifications (el mismo que el 4, R5.3) |
| Variables | `EXPIRES_IN` («24 horas» / «24 hours») · `SIGNUP_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Confirma tu correo para crear tu cuenta en Auphere` | `Confirm your email to create your Auphere account` |
| Previsualización | El enlace es válido durante {{{EXPIRES_IN}}}. | The link is valid for {{{EXPIRES_IN}}}. |
| Titular | Confirma tu correo | Confirm your email |
| Cuerpo | Gracias por registrarte en Auphere. Para terminar de crear tu cuenta, confirma que esta dirección de correo es tuya. | Thanks for signing up for Auphere. To finish creating your account, please confirm that this email address is yours. |
| Botón | Confirmar mi correo | Confirm my email |
| Detalle | El enlace es válido durante {{{EXPIRES_IN}}} y solo se puede usar una vez. Si no te has registrado tú, ignora este mensaje y no se creará ninguna cuenta. | The link is valid for {{{EXPIRES_IN}}} and can only be used once. If you didn't sign up, ignore this email and no account will be created. |

### 4 · `signup_existing` → `auphere-signup-existing-{es,en}`

Sustituye al correo 8. Misma estructura y remitente que el 3: solo quien abre el buzón sabe cuál le llegó (CE-004 de la spec 006).

| | |
|---|---|
| Para · idioma | el dueño de una dirección que ya tiene cuenta · el del formulario, igual que el 3 |
| Negocio · remitente | ninguno · notifications |
| Variables | `LOGIN_URL` ★ · `FORGOT_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Ya tienes una cuenta en Auphere` | `You already have an Auphere account` |
| Previsualización | Inicia sesión con tu correo y tu contraseña. | Sign in with your email and password. |
| Titular | Ya tienes una cuenta | You already have an account |
| Cuerpo | Hemos recibido una solicitud para crear una cuenta en Auphere con esta dirección de correo, pero ya hay una cuenta asociada a ella.<br><br>Puedes iniciar sesión con tu contraseña de siempre. | We received a request to create an Auphere account with this email address, but there's already an account linked to it.<br><br>You can sign in with your usual password. |
| Botón | Iniciar sesión | Sign in |
| Detalle | Si no recuerdas tu contraseña, [solicita una nueva] (→ `FORGOT_URL`). Si no has hecho tú esta solicitud, ignora este mensaje. Tu cuenta no ha cambiado. | If you've forgotten your password, [request a new one] (→ `FORGOT_URL`). If you didn't make this request, you can ignore this email. Your account hasn't changed. |

### 5 · `password_reset` → `auphere-password-reset-{es,en}`

Sustituye al correo 14. Conserva lo que exige la spec 011: un solo uso, una hora y el aviso de que se cierran las sesiones. **Sin «dar de baja las máquinas»**, que no se entendía: se dice que la sesión se cierra en todos los dispositivos.

| | |
|---|---|
| Para · idioma | la persona dueña de la cuenta · el de su cuenta |
| Negocio · remitente | ninguno · notifications |
| Variables | `RESET_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Restablece tu contraseña de Auphere` | `Reset your Auphere password` |
| Previsualización | El enlace caduca en una hora. | The link expires in one hour. |
| Titular | Restablece tu contraseña | Reset your password |
| Cuerpo | Hemos recibido una solicitud para restablecer la contraseña de tu cuenta de Auphere. Para crear una nueva, pulsa el botón. | We received a request to reset the password for your Auphere account. To create a new one, click the button below. |
| Botón | Crear una contraseña nueva | Create a new password |
| Detalle | El enlace caduca en una hora y solo se puede usar una vez. Cuando cambies la contraseña, se cerrará tu sesión en todos tus dispositivos y tendrás que volver a iniciarla.<br><br>Si no has pedido este cambio, ignora este mensaje. Tu contraseña seguirá siendo la misma. | The link expires in one hour and can only be used once. Once you change your password, you'll be signed out on all your devices and will need to sign in again.<br><br>If you didn't ask for this, you can ignore this email. Your password will stay the same. |

### 6 · `password_changed` → `auphere-password-changed-{es,en}`

Sustituye al correo 15. **Sin ningún enlace** salvo el `mailto:` del contacto de seguridad (R6.1, spec 011 R4.3). Eso incluye el logo, el pie y la palabra «auphere.com», que los clientes de correo convierten en enlace solos.

| | |
|---|---|
| Para · idioma | la persona dueña de la cuenta · el de su cuenta |
| Negocio · remitente | ninguno · notifications |
| Variables | `CHANGED_AT` (es: «30/10/2026 a las 16:20 UTC»; en: «October 30, 2026 at 16:20 UTC») · `SECURITY_CONTACT` (en local, si falta: `support@auphere.com`) |

| | es | en |
|---|---|---|
| Asunto | `Se ha cambiado la contraseña de tu cuenta de Auphere` | `Your Auphere password has been changed` |
| Previsualización | Si no has sido tú, escríbenos cuanto antes. | If this wasn't you, contact us right away. |
| Titular | Tu contraseña se ha cambiado | Your password has been changed |
| Cuerpo | La contraseña de tu cuenta de Auphere se cambió el {{{CHANGED_AT}}}. Por seguridad, hemos cerrado la sesión en todos tus dispositivos, así que tendrás que volver a iniciarla con la contraseña nueva.<br><br>Si has hecho tú el cambio, no tienes que hacer nada más.<br><br>**Si no has sido tú, escríbenos cuanto antes a {{{SECURITY_CONTACT}}}** (`mailto:`) **para que podamos proteger tu cuenta.** | The password for your Auphere account was changed on {{{CHANGED_AT}}}. For your security, we've signed you out on all your devices, so you'll need to sign in again with your new password.<br><br>If you made this change, there's nothing else you need to do.<br><br>**If you didn't, please email us right away at {{{SECURITY_CONTACT}}}** (`mailto:`) **so we can secure your account.** |
| Botón | — | — |
| Detalle | Por seguridad, este correo no incluye enlaces para iniciar sesión. Entra en Auphere como lo haces normalmente. | For your security, this email doesn't include any sign-in links. Open Auphere the way you usually do. |
| Pie | solo la firma, sin «auphere.com» | the signature only, without "auphere.com" |

---

## Cobros

### 7 · `receipt` → `auphere-receipt-{es,en}`

Sustituye al correo 2. Los conceptos pasan a líneas de texto (las plantillas no tienen bucles, R8 de `research.md`).

| | |
|---|---|
| Para · idioma | `partners.billing_email` · el de su cuenta si la tiene |
| Negocio · remitente | partner · billing |
| Variables | `PARTNER_NAME` · `PERIOD` · `TOTAL` · `DUE_ON` · `LINES` (una por concepto, «Concepto · US$X», hasta que quepan en 2 000 caracteres; si no caben, la última dice «y N conceptos más») · `FX_NOTE` (vacía si no hay conversión) · `BILLING_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Tu recibo de {mes} ({partner})` | `Your Auphere receipt for {month} ({partner})` |
| Previsualización | Importe total de {{{TOTAL}}}, con vencimiento el {{{DUE_ON}}}. | Total {{{TOTAL}}}, due {{{DUE_ON}}}. |
| Titular | Recibo de {{{PERIOD}}} | Receipt for {{{PERIOD}}} |
| Cuerpo | Te enviamos el recibo de {{{PARTNER_NAME}}} correspondiente a {{{PERIOD}}}.<br><br>**Importe total:** {{{TOTAL}}}<br>**Fecha de vencimiento:** {{{DUE_ON}}}<br><br>**Detalle**<br>{{{LINES}}}<br><br>{{{FX_NOTE}}} | Here is the {{{PARTNER_NAME}}} receipt for {{{PERIOD}}}.<br><br>**Total amount:** {{{TOTAL}}}<br>**Due date:** {{{DUE_ON}}}<br><br>**Details**<br>{{{LINES}}}<br><br>{{{FX_NOTE}}} |
| Botón | Ver el recibo | View receipt |
| Detalle | Puedes descargar el recibo en PDF desde la sección Facturación de la consola. Si tienes alguna duda sobre los importes, responde a este correo y te ayudaremos. | You can download the receipt as a PDF from the Billing section of the console. If you have any questions about the charges, just reply to this email and we'll help. |

`FX_NOTE`: «Los importes en pesos chilenos se han convertido a dólares al tipo de cambio observado el día de emisión ({tasa} CLP por USD).» / «Amounts in Chilean pesos were converted to US dollars at the observed exchange rate on the issue date ({rate} CLP per USD).»

### 8 · `charge_confirm` → `auphere-charge-confirm-{es,en}`

Sustituye al correo 18.

| | |
|---|---|
| Para · idioma | `billing_email`, o `contact_email` si falta · el de su cuenta si la tiene |
| Negocio · remitente | partner · billing |
| Variables | `PARTNER_NAME` · `AMOUNT` · `CONCEPT` (es: «el consumo del mes» / «la recarga automática de saldo»; en: «this month's usage» / «your automatic balance top-up») · `CONFIRM_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Confirma el pago de {importe} con tu banco` | `Confirm your payment of {amount}` |
| Previsualización | El cobro queda pendiente hasta que lo confirmes. | The charge stays on hold until you confirm it. |
| Titular | Tu banco necesita que confirmes un pago | Your bank needs you to confirm a payment |
| Cuerpo | Hemos intentado cobrar {{{AMOUNT}}} en la tarjeta de {{{PARTNER_NAME}}} por {{{CONCEPT}}}, pero tu banco pide que confirmes el pago antes de autorizarlo. Es una comprobación de seguridad habitual.<br><br>El cobro quedará pendiente hasta que lo confirmes. | We tried to charge {{{AMOUNT}}} to the {{{PARTNER_NAME}}} card for {{{CONCEPT}}}, but your bank needs you to confirm the payment before approving it. This is a standard security check.<br><br>The charge will stay pending until you confirm it. |
| Botón | Confirmar el pago | Confirm payment |
| Detalle | El botón te lleva a la página de pago segura de Stripe, nuestro proveedor de pagos. | The button takes you to Stripe's secure payment page. Stripe is our payment provider. |

---

## Saldo y consumo (al partner)

Para: `usage_alert_recipients` · idioma: el de la cuenta de cada destinatario · remitente: notifications.

### 9 · `client_out_of_quota` → `auphere-client-out-of-quota-{es,en}`

Sustituye al correo 9. Cuando el partner no tiene lista de alertas, el mismo hecho llega a sus dueños por el aviso genérico (fila `client.out_of_quota` de la tabla 18).

| | |
|---|---|
| Negocio | partner (y el cliente, en el registro) |
| Variables | `CLIENT_NAME` (el nombre que le puso el partner; si no, el de su negocio; si no, su referencia) · `USAGE_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `{cliente} se ha quedado sin saldo` | `{client} has run out of balance` |
| Previsualización | Su agente no responderá hasta que le asignes más saldo. | Its agent won't reply until you assign more balance. |
| Titular | {{{CLIENT_NAME}}} se ha quedado sin saldo | {{{CLIENT_NAME}}} has run out of balance |
| Cuerpo | Tu cliente {{{CLIENT_NAME}}} ha agotado su saldo, así que su agente ha dejado de responder a los mensajes que recibe.<br><br>Para que vuelva a atender, asígnale más saldo desde la sección Consumo de la consola. El agente volverá a responder en cuanto tenga saldo disponible. | Your client {{{CLIENT_NAME}}} has used up its balance, so its agent has stopped replying to incoming messages.<br><br>To get it working again, assign more balance from the Usage section of the console. The agent will start replying again as soon as it has balance available. |
| Botón | Asignar saldo | Assign balance |

### 10 · `wallet_low` → `auphere-wallet-low-{es,en}`

Sustituye al correo 10 (80 % del saldo del mes).

| | |
|---|---|
| Negocio | partner |
| Variables | `PARTNER_NAME` · `PERCENT_USED` · `PERIOD` · `CLIENTS_OUT_NOTE` (vacía, o la frase de abajo) · `BILLING_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Has usado el {porcentaje} % del saldo de este mes` | `You've used {percent}% of this month's balance` |
| Previsualización | Compra más saldo antes de que se agote para que tus agentes sigan respondiendo. | Top up before it runs out so your agents keep replying. |
| Titular | Te queda poco saldo este mes | Your balance is running low |
| Cuerpo | {{{PARTNER_NAME}}} ha usado el {{{PERCENT_USED}}} % del saldo de {{{PERIOD}}}. Cuando se agote, tus agentes dejarán de responder a tus clientes.<br><br>Te recomendamos comprar más saldo antes de que eso ocurra.<br><br>{{{CLIENTS_OUT_NOTE}}} | {{{PARTNER_NAME}}} has used {{{PERCENT_USED}}}% of its balance for {{{PERIOD}}}. Once it runs out, your agents will stop replying to your clients.<br><br>We recommend buying more balance before that happens.<br><br>{{{CLIENTS_OUT_NOTE}}} |
| Botón | Comprar saldo | Buy balance |

`CLIENTS_OUT_NOTE`:
- es, 1 cliente: «Además, uno de tus clientes ya ha llegado a su propio límite y no está respondiendo, aunque todavía te quede saldo.»
- es, n clientes: «Además, {n} de tus clientes ya han llegado a su propio límite y no están respondiendo, aunque todavía te quede saldo.»
- en, 1 cliente: «Also, one of your clients has already reached its own limit and isn't replying, even though you still have balance left.»
- en, n clientes: «Also, {n} of your clients have already reached their own limit and aren't replying, even though you still have balance left.»

### 11 · `wallet_empty` → `auphere-wallet-empty-{es,en}`

Sustituye al correo 11 (100 %).

| | |
|---|---|
| Negocio | partner |
| Variables | `PARTNER_NAME` · `PERIOD` · `BILLING_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Tu saldo se ha agotado y tus agentes no responden` | `Your balance has run out and your agents have stopped replying` |
| Previsualización | Compra más saldo para que vuelvan a atender. | Buy more balance to get them replying again. |
| Titular | Te has quedado sin saldo | You've run out of balance |
| Cuerpo | {{{PARTNER_NAME}}} ha agotado el saldo de {{{PERIOD}}} y tus agentes han dejado de responder. Los mensajes que lleguen a partir de ahora no recibirán respuesta.<br><br>Compra más saldo para que vuelvan a atender. Volverán a responder en cuanto el saldo esté disponible. | {{{PARTNER_NAME}}} has used up its balance for {{{PERIOD}}} and your agents have stopped replying. Messages that arrive from now on won't get a reply.<br><br>Buy more balance to get them working again. They'll start replying as soon as the balance is available. |
| Botón | Comprar saldo | Buy balance |

### 12 · `usage_cap_threshold` → `auphere-usage-cap-threshold-{es,en}`

Sustituye al correo 12. Solo informa: este límite no corta el servicio.

| | |
|---|---|
| Negocio | partner |
| Variables | `PARTNER_NAME` · `PERCENT` · `USED` · `CAP` · `PERIOD` · `USAGE_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Llevas el {porcentaje} % de tu límite mensual de mensajes` | `You've used {percent}% of your monthly message limit` |
| Previsualización | Es solo un aviso. Tu servicio sigue funcionando con normalidad. | This is only a notice. Your service is running as normal. |
| Titular | Llevas el {{{PERCENT}}} % de tu límite de mensajes | You've used {{{PERCENT}}}% of your message limit |
| Cuerpo | {{{PARTNER_NAME}}} lleva {{{USED}}} de los {{{CAP}}} mensajes que fijaste como límite para {{{PERIOD}}}.<br><br>Este límite solo sirve para avisarte, así que tu servicio sigue funcionando con normalidad. Te escribiremos de nuevo si llegas al 100 %. | {{{PARTNER_NAME}}} has used {{{USED}}} of the {{{CAP}}} messages you set as your limit for {{{PERIOD}}}.<br><br>This limit is only used to notify you, so your service keeps running as normal. We'll email you again if you reach 100%. |
| Botón | Ver el consumo | View usage |

### 13 · `usage_cap_reached` → `auphere-usage-cap-reached-{es,en}`

Sustituye al correo 13.

| | |
|---|---|
| Negocio | partner |
| Variables | `PARTNER_NAME` · `CAP` · `PERIOD` · `ALERTS_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Has alcanzado tu límite mensual de mensajes` | `You've reached your monthly message limit` |
| Previsualización | Tu servicio sigue activo. Puedes cambiar el límite cuando quieras. | Your service is still active. You can change the limit at any time. |
| Titular | Has alcanzado tu límite de mensajes | You've reached your message limit |
| Cuerpo | {{{PARTNER_NAME}}} ha llegado a los {{{CAP}}} mensajes que fijaste como límite para {{{PERIOD}}}.<br><br>Tu servicio sigue funcionando, porque este límite solo sirve para avisarte. Si quieres ajustarlo, puedes hacerlo desde la configuración de alertas de consumo. | {{{PARTNER_NAME}}} has reached the {{{CAP}}} messages you set as your limit for {{{PERIOD}}}.<br><br>Your service is still running, since this limit is only used to notify you. If you'd like to adjust it, you can do so in your usage alert settings. |
| Botón | Cambiar el límite | Change limit |

---

## Bandeja y avisos

### 14 · `inbox_waiting` → `auphere-inbox-waiting-{es,en}`

Sustituye al correo 16 en su variante `inbox.waiting`. Como hoy: el nombre del contacto y **nunca** el texto de un mensaje (spec 030). `CONTACT` siempre abre la frase, para que su valor por defecto («Un cliente» / «A customer») se lea bien.

| | |
|---|---|
| Para · idioma | las personas activas del cliente · el de la cuenta de cada una |
| Negocio · remitente | cliente · notifications |
| Variables | `CONTACT` · `CONVERSATION_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `{contacto} está esperando una respuesta` | `{contact} is waiting for a reply` |
| Previsualización | Tu agente ha dejado la conversación en tu bandeja. | Your agent has passed the conversation to your inbox. |
| Titular | {{{CONTACT}}} está esperando una respuesta | {{{CONTACT}}} is waiting for a reply |
| Cuerpo | {{{CONTACT}}} necesita la atención de alguien de tu equipo, así que tu agente ha dejado la conversación en tu bandeja.<br><br>Puedes responder directamente desde la consola. | {{{CONTACT}}} needs someone from your team to step in, so your agent has passed the conversation to your inbox.<br><br>You can reply directly from the console. |
| Botón | Abrir la conversación | Open conversation |

### 15 · `client_balance_low` → `auphere-client-balance-low-{es,en}`

Sustituye al correo 16, variante `client.balance_low`.

| | |
|---|---|
| Negocio · remitente | cliente · notifications |
| Variables | `CLIENT_NAME` · `CONSOLE_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Tu saldo no llegará a fin de mes` | `Your balance won't last until the end of the month` |
| Previsualización | Pide más saldo para que tu agente siga respondiendo. | Request more balance so your agent keeps replying. |
| Titular | Tu saldo no llegará a fin de mes | Your balance won't last the month |
| Cuerpo | Al ritmo de uso de este mes, el saldo de {{{CLIENT_NAME}}} se agotará antes de que termine. Cuando eso ocurra, tu agente dejará de responder.<br><br>Para evitarlo, puedes pedir más saldo desde la consola. | At this month's rate, the {{{CLIENT_NAME}}} balance will run out before the month ends. When that happens, your agent will stop replying.<br><br>To avoid this, you can request more balance from the console. |
| Botón | Abrir la consola | Open the console |

### 16 · `client_balance_out` → `auphere-client-balance-out-{es,en}`

Sustituye al correo 16, variante `client.balance_out`.

| | |
|---|---|
| Negocio · remitente | cliente · notifications |
| Variables | `CLIENT_NAME` · `CONSOLE_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Tu saldo se ha agotado y tu agente ha dejado de responder` | `Your balance has run out and your agent has stopped replying` |
| Previsualización | Pide más saldo para que vuelva a atender. | Request more balance to get it replying again. |
| Titular | Tu saldo se ha agotado | Your balance has run out |
| Cuerpo | El saldo de {{{CLIENT_NAME}}} se ha agotado y tu agente ha dejado de responder. Los mensajes que lleguen a partir de ahora no recibirán respuesta.<br><br>Pide más saldo desde la consola y tu agente volverá a atender en cuanto esté disponible. | The {{{CLIENT_NAME}}} balance has run out and your agent has stopped replying. Messages that arrive from now on won't get a reply.<br><br>Request more balance from the console and your agent will start replying again as soon as it's available. |
| Botón | Abrir la consola | Open the console |

### 17 · `conversation_escalated` → `auphere-conversation-escalated-{es,en}`

Sustituye al correo 20. Su asunto deja de ser idéntico al del 14, que puede salir por la misma conversación. Si quien lo recibe es del partner, no lleva el resumen (spec 040).

| | |
|---|---|
| Para · idioma | los destinatarios de escalado del canal · el de la cuenta de cada uno |
| Negocio · remitente | cliente · notifications |
| Variables | `CONTACT` (en minúscula a media frase; por defecto «un cliente» / «a customer») · `REASON_LINE` · `INBOX_URL` ★ |

| | es | en |
|---|---|---|
| Asunto | `Una conversación con {contacto} necesita tu atención` | `A conversation with {contact} needs your attention` |
| Previsualización | Tu agente la ha pasado a una persona. | Your agent has handed it over to a person. |
| Titular | Una conversación necesita tu atención | A conversation needs your attention |
| Cuerpo | Tu agente ha pasado a una persona una conversación con {{{CONTACT}}}.<br><br>{{{REASON_LINE}}}<br><br>Puedes atenderla desde la bandeja de la consola. | Your agent has handed a conversation with {{{CONTACT}}} over to a person.<br><br>{{{REASON_LINE}}}<br><br>You can pick it up from the inbox in the console. |
| Botón | Abrir la bandeja | Open inbox |

`REASON_LINE`, con resumen: «El motivo que ha indicado el agente es: «{motivo}».» / «The reason the agent gave: "{reason}".». Sin resumen: «Abre la conversación para ver los detalles.» / «Open the conversation to see the details.».

### 18 · `partner_notice` → `auphere-partner-notice-{es,en}`

Sustituye al correo 17, que volcaba las claves del aviso (`[Auphere] model.retirement (warning)` y una lista `clave: valor`). **Plantilla genérica**: el texto de cada tipo de aviso va en el código (tabla de abajo, R6 bis de `research.md`). La plantilla pone la forma.

| | |
|---|---|
| Para · idioma | dueños y administradores del partner, o la persona del aviso · el de la cuenta de cada uno |
| Negocio · remitente | partner (y el cliente, si el aviso lo trae) · notifications |
| Variables | `HEADING` · `MESSAGE` · `ACTION_LABEL` · `ACTION_URL` ★ |
| Asunto · Previsualización | el `HEADING` · el `MESSAGE` |

**Plantilla**: titular {{{HEADING}}} · «Hola,» · {{{MESSAGE}}} · botón [{{{ACTION_LABEL}}}] → `{{{ACTION_URL}}}` · firma.

`{cliente}` es el nombre del cliente o, si no lo tiene, su referencia.

| Tipo | `HEADING` es · en | `MESSAGE` es · en | Botón es · en | Ruta |
|---|---|---|---|---|
| `support.ticket_opened` | Hemos recibido tu consulta {ticket} · We've received your request {ticket} | Nuestro equipo de soporte ya la está revisando y te responderá lo antes posible. · Our support team is already looking into it and will get back to you as soon as possible. | Ver tus avisos · View your notifications | `/notifications` |
| `support.capability_requested` | Hemos recibido tu solicitud {ticket} · We've received your request {ticket} | Nuestro equipo ya la está revisando y te responderá lo antes posible. · Our team is already looking into it and will get back to you as soon as possible. | Ver tus avisos · View your notifications | `/notifications` |
| `client.activated`, sin saldo | {cliente} está activo, pero todavía no puede atender · {client} is active but can't reply yet | El agente ya está publicado, pero el cliente no tiene saldo asignado. Asígnale saldo para que empiece a responder. · The agent is published, but the client has no balance assigned. Assign balance so it can start replying. | Asignar saldo · Assign balance | `/usage` |
| `client.activated`, sin WhatsApp | {cliente} está activo, pero todavía no puede atender · {client} is active but can't reply yet | El agente ya está publicado, pero falta conectar su número de WhatsApp. · The agent is published, but its WhatsApp number isn't connected yet. | Conectar WhatsApp · Connect WhatsApp | `/clients/{ref}/channels` |
| `client.activated`, sin los dos | {cliente} está activo, pero todavía no puede atender · {client} is active but can't reply yet | El agente ya está publicado, pero faltan el número de WhatsApp y el saldo. · The agent is published, but it still needs a WhatsApp number and balance. | Abrir el cliente · Open client | `/clients/{ref}` |
| `model.retirement` | El modelo {modelo} dejará de estar disponible en {días} días · The {model} model will be retired in {days} days | Los agentes que lo usan tienen que pasar a otro modelo antes de esa fecha para seguir funcionando. · Agents that use it need to switch to another model before then to keep working. | Revisar los agentes · Review agents | `/agentes` |
| `model.price_change` | El precio del modelo {modelo} sube un {porcentaje} % · The price of the {model} model is going up {percent}% | El cambio se aplica desde el {fecha} y afecta al consumo de los agentes que lo usan. · The change applies from {date} and affects the usage of the agents that use it. | Revisar los agentes · Review agents | `/agentes` |
| `integration.reauth_required` | Una conexión de {cliente} necesita permiso de nuevo · A {client} connection needs permission again | Una de las herramientas conectadas de {cliente} ha perdido el permiso de acceso. Hasta que alguien lo vuelva a conceder, el agente no podrá usarla. · One of {client}'s connected tools has lost its access permission. Until someone grants it again, the agent won't be able to use it. | Revisar las conexiones · Review connections | `/clients/{ref}/integrations` |
| `agent.tests.failing` | Algunas pruebas de un agente de {cliente} han dejado de pasar · Some tests for a {client} agent are failing | Ha ocurrido después de un cambio en los datos del negocio. Revisa las pruebas para ver qué respuestas han cambiado. · This happened after a change to the business details. Check the tests to see which replies have changed. | Ver las pruebas · View tests | `/clients/{ref}/agents` |
| `client.out_of_quota` | {cliente} se ha quedado sin saldo · {client} has run out of balance | Su agente ha dejado de responder a los mensajes que recibe. Asígnale más saldo para que vuelva a atender. · Its agent has stopped replying to incoming messages. Assign more balance to get it working again. | Asignar saldo · Assign balance | `/usage` |
| `client.wallet.refill_short` | No se ha podido recargar el saldo de {cliente} · {client}'s balance couldn't be topped up | No había saldo suficiente en tu cuenta para la recarga de este mes. · There wasn't enough balance in your account for this month's top-up. | Comprar saldo · Buy balance | `/billing` |
| `client.wallet.low` | A {cliente} le queda poco saldo · {client} is running low on balance | Cuando se agote, sus agentes dejarán de responder. · When it runs out, its agents will stop replying. | Asignar saldo · Assign balance | `/usage` |
| `client.wallet.not_enough` | El saldo de {cliente} no llegará a fin de mes · {client}'s balance won't last the month | Al ritmo de uso de este mes, se agotará antes de que termine. · At this month's rate, it will run out before the month ends. | Asignar saldo · Assign balance | `/usage` |
| `client.wallet.empty` | {cliente} se ha quedado sin saldo · {client} has run out of balance | Sus agentes han dejado de responder. Asígnale más saldo para que vuelvan a atender. · Its agents have stopped replying. Assign more balance to get them working again. | Asignar saldo · Assign balance | `/usage` |
| `agent.cap.warning` | Un agente de {cliente} ha usado el 80 % de su límite del mes · A {client} agent has used 80% of its monthly limit | Cuando llegue al límite, el agente se pausará hasta el mes que viene. · When it reaches the limit, the agent will be paused until next month. | Revisar el límite · Review limit | `/usage` |
| `agent.cap.reached` | Un agente de {cliente} ha llegado a su límite del mes · A {client} agent has reached its monthly limit | El agente está en pausa y no responderá hasta el mes que viene, salvo que amplíes su límite. · The agent is paused and won't reply until next month unless you raise its limit. | Revisar el límite · Review limit | `/usage` |
| `build.budget.warning` | Has usado el 80 % del límite de creación de agentes · You've used 80% of your agent-building limit | Cuando llegues al límite, no se podrán crear agentes nuevos hasta el mes que viene. Editar los que ya tienes seguirá funcionando. · Once you reach it, you won't be able to create new agents until next month. Editing your existing agents will still work. | Ver el consumo · View usage | `/usage` |
| `build.budget.exhausted` | Has alcanzado el límite de creación de agentes · You've reached your agent-building limit | No se podrán crear agentes nuevos hasta el mes que viene. Puedes seguir editando los que ya tienes. · You won't be able to create new agents until next month. You can still edit your existing agents. | Ver el consumo · View usage | `/usage` |
| `template.rejected` | Meta ha rechazado la plantilla {plantilla} de {cliente} · Meta has rejected {client}'s {template} template | No se podrá enviar hasta que Meta la apruebe. En la página del canal encontrarás el motivo. · It can't be sent until Meta approves it. You'll find the reason on the channel page. | Revisar las plantillas · Review templates | `/clients/{ref}/channels` |
| `template.paused` | Meta ha pausado la plantilla {plantilla} de {cliente} · Meta has paused {client}'s {template} template | Meta la ha pausado por baja calidad y no se podrá enviar hasta que se reactive. · Meta paused it for low quality, and it can't be sent until it's reactivated. | Revisar las plantillas · Review templates | `/clients/{ref}/channels` |
| `template.disabled` | Meta ha desactivado la plantilla {plantilla} de {cliente} · Meta has disabled {client}'s {template} template | Ya no se puede enviar. Si la necesitas, tendrás que crear una nueva. · It can no longer be sent. If you need it, you'll have to create a new one. | Revisar las plantillas · Review templates | `/clients/{ref}/channels` |
| `template.quality_dropped` | Ha bajado la calidad de la plantilla {plantilla} de {cliente} · The quality of {client}'s {template} template has dropped | Si sigue bajando, Meta podría pausarla. Te recomendamos revisar su texto y a quién se envía. · If it keeps dropping, Meta may pause it. We recommend reviewing its wording and who it's sent to. | Revisar las plantillas · Review templates | `/clients/{ref}/channels` |
| `channel.problem` | El WhatsApp de {cliente} no está respondiendo · {client}'s WhatsApp isn't replying | Hay un problema con uno de sus números y el agente no puede atender por él. En la página del canal encontrarás el detalle. · There's a problem with one of its numbers and the agent can't reply through it. You'll find the details on the channel page. | Abrir el canal · Open channel | `/clients/{ref}/channels` |
| `channel.account_alert` | Meta ha enviado un aviso sobre el WhatsApp de {cliente} · Meta has sent an alert about {client}'s WhatsApp | En la página del canal puedes ver el aviso y si hace falta hacer algo. · On the channel page you can see the alert and whether any action is needed. | Abrir el canal · Open channel | `/clients/{ref}/channels` |
| `channel.account_review` | Meta no ha aprobado la cuenta de WhatsApp de {cliente} · Meta hasn't approved {client}'s WhatsApp account | En la página del canal encontrarás el motivo y los pasos para solicitar una nueva revisión. · On the channel page you'll find the reason and the steps to request a new review. | Abrir el canal · Open channel | `/clients/{ref}/channels` |
| `channel.name_rejected` | Meta ha rechazado el nombre del WhatsApp de {cliente} · Meta has rejected the name for {client}'s WhatsApp | Puedes proponer otro nombre desde la página del canal. · You can suggest a different name from the channel page. | Abrir el canal · Open channel | `/clients/{ref}/channels` |
| *(cualquier otro)* | Tienes un aviso nuevo en la consola · You have a new notification in the console | Entra en la consola para ver el detalle. · Sign in to the console to see the details. | Ver tus avisos · View your notifications | `/notifications` |

Un tipo que llega sin texto propio cae en la última fila **y deja un `email.notice_without_copy` en el registro**. La prueba de barrido falla si un tipo de `NotificationKind` que puede salir por correo no tiene fila.

### 19 · `client_notice` → `auphere-client-notice-{es,en}`

Sustituye al correo 16 en sus variantes sin asunto propio («Tienes un aviso en tu consola»). Genérica por la misma razón que la 18. Misma forma, con el botón «Abrir la consola» / «Open the console».

| | |
|---|---|
| Para · idioma | las personas activas del cliente · el de la cuenta de cada una |
| Negocio · remitente | cliente · notifications |
| Variables | `HEADING` · `MESSAGE` · `CONSOLE_URL` ★ |

| Tipo | `HEADING` es · en | `MESSAGE` es · en |
|---|---|---|
| `client.wallet.low` | Te queda poco saldo · Your balance is running low | Cuando se agote, tu agente dejará de responder. Puedes pedir más saldo desde la consola. · When it runs out, your agent will stop replying. You can request more balance from the console. |
| `client.wallet.not_enough` | Tu saldo no llegará a fin de mes · Your balance won't last the month | Al ritmo de uso de este mes, se agotará antes de que termine. Puedes pedir más saldo desde la consola. · At this month's rate, it will run out before the month ends. You can request more balance from the console. |
| `client.wallet.empty` | Tu saldo se ha agotado · Your balance has run out | Tu agente ha dejado de responder. Pide más saldo desde la consola para que vuelva a atender. · Your agent has stopped replying. Request more balance from the console to get it working again. |
| `agent.cap.warning` | Tu agente ha usado el 80 % de su límite del mes · Your agent has used 80% of its monthly limit | Cuando llegue al límite, se pausará hasta el mes que viene. · When it reaches the limit, it will be paused until next month. |
| `agent.cap.reached` | Tu agente ha llegado a su límite del mes · Your agent has reached its monthly limit | Está en pausa y no responderá hasta el mes que viene, salvo que se amplíe su límite. · It's paused and won't reply until next month unless its limit is raised. |
| `channel.problem` | Tu WhatsApp no está respondiendo · Your WhatsApp isn't replying | Hay un problema con tu número y el agente no puede atender por él. La persona que gestiona tu agente ya ha recibido el aviso. · There's a problem with your number and the agent can't reply through it. The person who manages your agent has already been notified. |
| *(cualquier otro)* | Tienes un aviso nuevo en la consola · You have a new notification in the console | Entra en la consola para ver el detalle. · Sign in to the console to see the details. |

---

## Internos (para el equipo de Auphere)

### 20 · `internal_alert` → `auphere-internal-alert-es`

Sustituye a los correos 3 (consulta de soporte) y 5 (petición de borrado). **Los correos 19 (conciliación con Meta) y 21 (alertas de plataforma) se retiran** (Requisito 9, tercera revisión del owner): son monitorización, quedan en el registro con nivel de error y los recogerá Datadog. Solo en español: lo lee el equipo. Misma marca, sin botón ni saludo. Quien lo lee sabe dónde mirar, y el detalle se lo dice.

| | |
|---|---|
| Para | `support_alert_email` o `security_contact_email`, como hoy |
| Negocio | el del caso cuando lo hay (partner en el 3); ninguno en el resto |
| Remitente · respuestas | notifications · support, **salvo el 5**: la petición de borrado responde a la persona que la pidió, como hoy |
| Variables | `HEADING` · `DETAIL` (líneas, cada valor escapado) · `KIND` (el identificador de la alerta) |
| Asunto | `[Auphere] {qué pasa}`. Las alertas de plataforma dejan el prefijo `[Nexus]` y usan `[Auphere]`, como las demás |

**Plantilla**: cabecera «Aviso interno» · titular {{{HEADING}}} · {{{DETAIL}}} · `{{{KIND}}}` en monoespaciada · pie «Aviso interno de la plataforma Auphere.»

| Origen | Asunto | `HEADING` | `DETAIL` |
|---|---|---|---|
| 3 · consulta de soporte | `[Auphere] Consulta {AU-n} · {categoría} · {tema}` | {partner} ha abierto la consulta {AU-n} | Partner, cliente, qué necesita, qué ha comprobado ya (una línea por punto), alternativa propuesta y SLA |
| 5 · petición de borrado | `[Auphere] Petición de borrado de cuenta: {email}` | Una persona pide borrar su cuenta de Auphere Customers | Cuenta, cliente, dónde revisarlo (admin → Acceso del cliente) y la acción de auditoría `client_account.deletion_requested` |
