/** ES/EN del carril `builder-channels` — los canales de un agente, su menú ⋯,
 *  la página de configuración de cada canal y el enlace del dueño por agente
 *  (spec 047, historias 10 y 11; T111, T112, T114 y T115; requisitos 29, 31 a
 *  34). Los textos del estado visible de un canal son los de
 *  `contracts/events.md` §1.2, los mismos en toda la consola (25.5).
 *  Ni «integración» ni punto y coma (`words.test.ts`).
 *
 *  La frase «desde su teléfono» solo sale con la bandera del enlace del dueño
 *  (`lib/env.ts`, 31.3): las claves `.phone` son su variante. */
export const builderChannelsMessages = {
  // ── El estado visible de un canal (events.md §1.2) ──────────────────────
  "builder.channel.state.pending_link": { es: "Pendiente · enlace enviado", en: "Pending · link sent" },
  "builder.channel.state.disconnected": { es: "Desconectado", en: "Disconnected" },
  "builder.channel.state.problem": { es: "Con problemas · {reason}", en: "With problems · {reason}" },
  "builder.channel.state.paused": { es: "En pausa", en: "Paused" },
  "builder.channel.state.unconfigured": { es: "Sin configurar", en: "Not set up" },
  "builder.channel.state.team_only": { es: "Solo mi equipo", en: "Only my team" },
  "builder.channel.state.everyone": { es: "A todos", en: "Everyone" },
  "builder.channel.problem.quality": { es: "calidad baja", en: "low quality" },
  "builder.channel.problem.auth_expired": { es: "hay que volver a autorizar", en: "needs authorising again" },
  "builder.channel.problem.coexistence_inactive": { es: "la app lleva días sin abrirse", en: "the app has not been opened for days" },
  "builder.channel.problem.meta_error": { es: "error de Meta", en: "Meta error" },
  "builder.channel.problem.account_review": { es: "Meta no aprobó la revisión de la cuenta", en: "Meta did not approve the account review" },
  "builder.channel.problem.account_alert": { es: "Meta envió una alerta sobre la cuenta", en: "Meta sent an alert about the account" },
  "builder.channel.problem.unknown": { es: "sin motivo", en: "no reason" },

  // ── La sección Canales del agente (29) ──────────────────────────────────
  "builder.screen.channels": { es: "Canales", en: "Channels" },
  "builder.channels.intro": {
    es: "Los canales por los que responde este agente. Cada uno tiene su propia configuración.",
    en: "The channels this agent answers on. Each one has its own settings.",
  },
  "builder.channels.list": { es: "Canales de este agente", en: "This agent’s channels" },
  "builder.channels.empty": { es: "Este agente aún no tiene ningún canal.", en: "This agent has no channel yet." },
  "builder.channels.error": {
    es: "No pudimos cargar los canales de este agente. Inténtalo de nuevo.",
    en: "We could not load this agent’s channels. Try again.",
  },
  "builder.channels.whatsapp": { es: "WhatsApp", en: "WhatsApp" },
  "builder.channels.instagram": { es: "Instagram", en: "Instagram" },
  "builder.channels.messenger": { es: "Messenger", en: "Messenger" },
  "builder.channels.configure": { es: "Configurar {number}", en: "Set up {number}" },

  // ── El ⋯ de cada canal (34.1) ───────────────────────────────────────────
  "builder.channel.menu": { es: "Más acciones de {number}", en: "More actions for {number}" },
  "builder.channel.action.configure": { es: "Configuración", en: "Settings" },
  "builder.channel.action.move": { es: "Pasar a otro agente", en: "Move to another agent" },
  "builder.channel.action.pause": { es: "Pausar este canal", en: "Pause this channel" },
  "builder.channel.action.resume": { es: "Reanudar este canal", en: "Resume this channel" },
  "builder.channel.action.disconnect": { es: "Desconectar", en: "Disconnect" },
  "builder.channel.cancel": { es: "Cancelar", en: "Cancel" },
  "builder.channel.error": { es: "No se pudo hacer. Inténtalo de nuevo.", en: "It could not be done. Try again." },
  "builder.channel.move.title": { es: "Pasar {number} a otro agente", en: "Move {number} to another agent" },
  "builder.channel.move.body": {
    es: "Desde el siguiente mensaje responde el agente que elijas. El canal conserva su configuración y sus conversaciones.",
    en: "From the next message, the agent you pick answers. The channel keeps its settings and its conversations.",
  },
  "builder.channel.move.field": { es: "Agente que lo atenderá", en: "Agent that will answer it" },
  "builder.channel.move.confirm": { es: "Pasar el número", en: "Move the number" },
  "builder.channel.move.confirm.social": { es: "Pasar el canal", en: "Move the channel" },
  "builder.channel.move.done": { es: "{number} ya lo atiende {name}.", en: "{name} now answers {number}." },
  "builder.channel.move.error.target": { es: "Ese agente ya no puede atender canales. Elige otro.", en: "That agent can no longer answer channels. Pick another one." },
  "builder.channel.paused": {
    es: "{number} está en pausa. Los mensajes se guardan y esperan a una persona.",
    en: "{number} is paused. Messages are kept and wait for a person.",
  },
  "builder.channel.resumed": { es: "{number} vuelve a responder.", en: "{number} answers again." },
  "builder.channel.disconnect.title": { es: "¿Desconectar {number}?", en: "Disconnect {number}?" },
  "builder.channel.disconnect.body": {
    es: "El agente deja de responder por este número. Las conversaciones se conservan y puedes volver a conectarlo cuando quieras.",
    en: "The agent stops answering on this number. Conversations are kept and you can connect it again whenever you want.",
  },
  // Spec 049, requisito 5.3: Instagram y Messenger no conservan lo recibido.
  // El token se borra al desconectar y los mensajes, a los 30 días; volver a
  // conectar antes lo cancela (``connect.py`` limpia ``disconnected_at``).
  "builder.channel.disconnect.body.social": {
    es: "El agente deja de responder por este canal y Auphere borra su acceso ahora. Los mensajes que llegaron por él se borran a los 30 días, salvo que lo vuelvas a conectar antes.",
    en: "The agent stops answering on this channel and Auphere removes its access now. The messages that came through it are deleted after 30 days, unless you connect it again before then.",
  },
  "builder.channel.disconnect.confirm": { es: "Desconectar", en: "Disconnect" },
  "builder.channel.disconnect.done": { es: "{number} desconectado.", en: "{number} disconnected." },
  "builder.channel.pending.title": { es: "Falta terminar en Meta", en: "Still to finish at Meta" },
  "builder.channel.pending.body": {
    es: "{number} ya está desconectado, pero Meta no confirmó la baja. Reinténtalo cuando quieras.",
    en: "{number} is already disconnected, but Meta did not confirm it. Retry whenever you want.",
  },
  "builder.channel.pending.retry": { es: "Reintentar", en: "Retry" },
  "builder.channel.pending.done": { es: "Terminado también en Meta.", en: "Finished at Meta too." },

  // ── El enlace del dueño por agente (31) ─────────────────────────────────
  "builder.ownerLink.title": { es: "Enviar un enlace al dueño", en: "Send a link to the owner" },
  "builder.ownerLink.body": {
    es: "El dueño del negocio abre el enlace en su navegador, entra con su cuenta de Meta y conecta el número él mismo. El número queda en este agente, en «Solo mi equipo». El enlace sirve una vez y caduca a los 7 días.",
    en: "The business owner opens the link in their browser, signs in with their Meta account and connects the number themselves. The number stays with this agent, in “Only my team”. The link works once and expires after 7 days.",
  },
  "builder.ownerLink.body.phone": {
    es: "El dueño del negocio abre el enlace desde su teléfono, entra con su cuenta de Meta y conecta el número él mismo. El número queda en este agente, en «Solo mi equipo». El enlace sirve una vez y caduca a los 7 días.",
    en: "The business owner opens the link from their phone, signs in with their Meta account and connects the number themselves. The number stays with this agent, in “Only my team”. The link works once and expires after 7 days.",
  },
  "builder.ownerLink.mode": { es: "¿Cómo lo conecta?", en: "How will they connect it?" },
  "builder.ownerLink.mode.coexistence": {
    es: "Ya usa la app WhatsApp Business (recomendado)",
    en: "They already use the WhatsApp Business app (recommended)",
  },
  "builder.ownerLink.mode.coexistence.hint": {
    es: "Sigue usando la app y el agente responde a la vez. Meta le pedirá escanear un código desde la app.",
    en: "They keep using the app and the agent answers alongside. Meta will ask them to scan a code from the app.",
  },
  "builder.ownerLink.mode.cloud_api": { es: "Es un número que no usa la app", en: "It is a number that does not use the app" },
  "builder.ownerLink.mode.cloud_api.hint": {
    es: "Meta le pedirá verificar el número con un código.",
    en: "Meta will ask them to verify the number with a code.",
  },
  "builder.ownerLink.mode.whatsapp_login": { es: "WhatsApp login (beta)", en: "WhatsApp login (beta)" },
  "builder.ownerLink.mode.whatsapp_login.hint": {
    es: "Solo en los países donde Meta la abrió. Si no está disponible para este negocio, te lo decimos al crearlo.",
    en: "Only in the countries where Meta opened it. If it is not available for this business, we tell you when you create it.",
  },
  "builder.ownerLink.modeName.coexistence": { es: "app WhatsApp Business", en: "WhatsApp Business app" },
  "builder.ownerLink.modeName.cloud_api": { es: "número sin la app", en: "number without the app" },
  "builder.ownerLink.modeName.whatsapp_login": { es: "WhatsApp login", en: "WhatsApp login" },
  "builder.ownerLink.create": { es: "Crear enlace", en: "Create link" },
  "builder.ownerLink.another": { es: "Crear otro enlace", en: "Create another link" },
  "builder.ownerLink.replaces": {
    es: "Ya hay un enlace pendiente para este agente. Si creas otro, el anterior deja de funcionar.",
    en: "There is already a pending link for this agent. If you create another one, the earlier one stops working.",
  },
  "builder.ownerLink.replace": { es: "Revocar y crear", en: "Revoke and create" },
  "builder.ownerLink.unavailable": {
    es: "WhatsApp login no está disponible para el país de este negocio. Elige otra forma de conectarlo.",
    en: "WhatsApp login is not available for this business’s country. Choose another way to connect it.",
  },
  "builder.ownerLink.ready": {
    es: "Enlace listo. Cópialo ahora: por seguridad no se vuelve a enseñar.",
    en: "Link ready. Copy it now: for security it is not shown again.",
  },
  "builder.ownerLink.url": { es: "Enlace para el dueño", en: "Link for the owner" },
  "builder.ownerLink.copy": { es: "Copiar enlace", en: "Copy link" },
  "builder.ownerLink.copied": { es: "Enlace copiado.", en: "Link copied." },
  "builder.ownerLink.whatsapp": { es: "Enviar por WhatsApp", en: "Send by WhatsApp" },
  "builder.ownerLink.email": { es: "Enviar por correo", en: "Send by email" },
  "builder.ownerLink.subject": { es: "Conecta el WhatsApp de tu negocio", en: "Connect your business WhatsApp" },
  "builder.ownerLink.message": {
    es: "Hola. Para conectar el WhatsApp de tu negocio con tu agente, abre este enlace y sigue los pasos de Meta: {url}",
    en: "Hi. To connect your business WhatsApp to your agent, open this link and follow Meta’s steps: {url}",
  },
  "builder.ownerLink.message.phone": {
    es: "Hola. Para conectar el WhatsApp de tu negocio con tu agente, abre este enlace desde tu teléfono y sigue los pasos de Meta: {url}",
    en: "Hi. To connect your business WhatsApp to your agent, open this link from your phone and follow Meta’s steps: {url}",
  },
  "builder.ownerLink.expires": { es: "Caduca el {date}.", en: "Expires on {date}." },
  "builder.ownerLink.done": { es: "Hecho", en: "Done" },
  "builder.ownerLink.pending": { es: "Enlace pendiente · {mode}", en: "Pending link · {mode}" },
  "builder.ownerLink.pending.expires": {
    es: "Caduca el {date}. El enlace no se puede volver a enseñar: si se perdió, crea otro.",
    en: "Expires on {date}. The link cannot be shown again: if it got lost, create another one.",
  },
  "builder.ownerLink.revoke": { es: "Revocar", en: "Revoke" },
  "builder.ownerLink.revoke.title": { es: "¿Revocar el enlace?", en: "Revoke the link?" },
  "builder.ownerLink.revoke.body": {
    es: "El dueño ya no podrá usarlo. Puedes crear otro cuando quieras.",
    en: "The owner can no longer use it. You can create another one whenever you want.",
  },
  "builder.ownerLink.revoked": { es: "Enlace revocado.", en: "Link revoked." },

  // ── La página del canal (32 y 33) ───────────────────────────────────────
  "builder.channel.page.noAgent": { es: "Lo atiende el agente por defecto", en: "The default agent answers it" },
  "builder.channel.page.sections": { es: "Secciones de la configuración", en: "Sections of the settings" },
  // H5 (63.1): la configuración dentro del agente, como el prototipo (`agente.md` §8).
  "builder.channel.page.note": {
    es: "Todo esto es del canal. Si el agente atiende en otro canal, allí tiene su propia configuración.",
    en: "All of this belongs to the channel. If the agent answers on another channel, it has its own settings there.",
  },
  "builder.channel.head.of": { es: "canal de {name}", en: "channel of {name}" },
  "builder.channel.more": { es: "Más ajustes", en: "More settings" },
  "builder.channel.more.hint": { es: "Mensaje de espera e historial de cambios.", en: "Waiting message and change history." },
  "builder.channel.bar.label": { es: "Guardar configuración", en: "Save settings" },
  "builder.channel.bar.unset": { es: "El canal aún no responde: guarda para activarlo.", en: "The channel does not answer yet: save to turn it on." },
  "builder.channel.bar.later": { es: "Decidir luego", en: "Decide later" },
  "builder.channel.bar.activateTeam": { es: "Activar solo para mi equipo", en: "Turn on for my team only" },
  "builder.channel.bar.activateAll": { es: "Activar para todos", en: "Turn on for everyone" },
  "builder.channel.saved.team": { es: "{agent} responde por {number} solo a tu equipo.", en: "{agent} answers on {number} to your team only." },
  "builder.channel.saved.everyone": { es: "{agent} responde por {number} a todos.", en: "{agent} answers on {number} to everyone." },
  "builder.channel.saved.agent": { es: "El agente", en: "The agent" },
  "builder.channel.page.readonly": {
    es: "Tu rol solo permite ver esta configuración.",
    en: "Your role can only view these settings.",
  },
  "builder.channel.page.disconnected": {
    es: "Este número está desconectado. Su configuración se conserva por si vuelves a conectarlo.",
    en: "This number is disconnected. Its settings are kept in case you connect it again.",
  },
  "builder.channel.page.disconnected.social": {
    es: "Este canal está desconectado. Los mensajes que llegaron por él se borran a los 30 días de desconectarlo, salvo que lo vuelvas a conectar antes. Su configuración se conserva.",
    en: "This channel is disconnected. The messages that came through it are deleted 30 days after disconnecting, unless you connect it again before then. Its settings are kept.",
  },

  "builder.channel.audience.title": { es: "A quién responde", en: "Who it answers" },
  "builder.channel.audience.intro": {
    es: "Prueba con tu equipo antes de abrirlo a todos. Vale solo para este número.",
    en: "Try it with your team before opening it to everyone. It applies to this number only.",
  },
  // Instagram y Messenger escriben con un IGSID o un PSID, no con un teléfono:
  // «Solo mi equipo» y las excepciones no existen ahí (channel-page.tsx).
  "builder.channel.audience.intro.social": {
    es: "Aquí no hay modo de prueba: Instagram y Messenger no tienen teléfonos con los que limitarlo. Prueba el agente en sus pruebas y elige «A todos» cuando esté listo.",
    en: "There is no test mode here: Instagram and Messenger have no phones to limit it to. Try the agent in its tests, and choose “Everyone” when it is ready.",
  },
  "builder.channel.mode.team_only": { es: "Solo mi equipo", en: "Only my team" },
  "builder.channel.mode.team_only.hint": {
    es: "Responde solo a los números de prueba. Los demás mensajes se guardan en Conversaciones, sin respuesta y sin marcarlos como leídos.",
    en: "It answers only the test numbers. Other messages are kept in Conversations, unanswered and not marked as read.",
  },
  "builder.channel.mode.everyone": { es: "A todos", en: "Everyone" },
  "builder.channel.mode.everyone.hint": {
    es: "Responde a todo el mundo, salvo a las excepciones.",
    en: "It answers everyone except the exceptions.",
  },
  "builder.channel.mode.everyone.hint.social": {
    es: "Responde a todas las personas que le escriban.",
    en: "It answers everyone who writes.",
  },
  "builder.channel.mode.unset": { es: "Todavía a nadie", en: "Nobody yet" },
  "builder.channel.mode.unset.hint": {
    es: "Sin configurar: el agente aún no responde por este canal.",
    en: "Not set up: the agent does not answer on this channel yet.",
  },
  "builder.channel.adminOnly": {
    es: "«A todos» no se puede elegir: este agente viene de una plantilla solo para administradores.",
    en: "“Everyone” cannot be chosen: this agent comes from an admins-only template.",
  },
  "builder.channel.tests.title": { es: "Números de prueba", en: "Test numbers" },
  "builder.channel.tests.empty": { es: "Aún no hay números de prueba.", en: "No test numbers yet." },
  "builder.channel.tests.required": {
    es: "«Solo mi equipo» necesita al menos un número de prueba.",
    en: "“Only my team” needs at least one test number.",
  },
  "builder.channel.tests.whatsappOnly": {
    es: "«Solo mi equipo» usa números de teléfono y solo funciona en WhatsApp. Aquí elige «A todos».",
    en: "“Only my team” uses phone numbers and only works on WhatsApp. Choose “Everyone” here.",
  },
  "builder.channel.number.field": { es: "Número nuevo", en: "New number" },
  "builder.channel.number.hint": {
    es: "Con el prefijo del país, por ejemplo +34 611 20 48 93.",
    en: "With the country code, for example +34 611 20 48 93.",
  },
  "builder.channel.number.add": { es: "Añadir", en: "Add" },
  "builder.channel.number.addTo": { es: "Añadir a {list}", en: "Add to {list}" },
  "builder.channel.number.remove": { es: "Quitar {number}", en: "Remove {number}" },
  "builder.channel.number.invalid": {
    es: "«{value}» no es un número válido. Escríbelo con el prefijo del país, por ejemplo +34 611 20 48 93.",
    en: "“{value}” is not a valid number. Type it with the country code, for example +34 611 20 48 93.",
  },
  "builder.channel.number.duplicate": { es: "Ese número ya está en la lista.", en: "That number is already on the list." },

  "builder.channel.exceptions.title": { es: "Excepciones", en: "Exceptions" },
  "builder.channel.exceptions.intro": {
    es: "Números a los que el agente nunca responde, por ejemplo un proveedor. Sus mensajes se guardan sin respuesta automática.",
    en: "Numbers the agent never answers, a supplier for example. Their messages are kept with no automatic reply.",
  },
  "builder.channel.exceptions.empty": { es: "Sin excepciones.", en: "No exceptions." },

  "builder.channel.escalation.title": { es: "Escalado a personas", en: "Hand-over to people" },
  "builder.channel.escalation.intro": {
    es: "A quién avisamos cuando el agente pasa una conversación a una persona. Hasta 10 personas.",
    en: "Who we notify when the agent hands a conversation to a person. Up to 10 people.",
  },
  "builder.channel.recipients": { es: "Personas a las que avisar", en: "People to notify" },
  "builder.channel.recipients.empty": {
    es: "Nadie recibe aviso todavía. La conversación igual queda en la Bandeja como «Necesita humano».",
    en: "Nobody gets notified yet. The conversation still goes to the Inbox as “Needs a human”.",
  },
  "builder.channel.recipients.max": { es: "Como mucho 10 personas.", en: "At most 10 people." },
  "builder.channel.recipient.add": { es: "Añadir persona", en: "Add a person" },
  "builder.channel.recipient.legend": { es: "Persona {n}", en: "Person {n}" },
  "builder.channel.recipient.name": { es: "Nombre", en: "Name" },
  "builder.channel.recipient.via": { es: "Por dónde", en: "How" },
  "builder.channel.via.whatsapp": { es: "WhatsApp", en: "WhatsApp" },
  "builder.channel.via.email": { es: "Correo", en: "Email" },
  "builder.channel.via.inbox": { es: "Bandeja", en: "Inbox" },
  "builder.channel.recipient.phone": { es: "Su WhatsApp", en: "Their WhatsApp" },
  "builder.channel.recipient.email": { es: "Su correo", en: "Their email" },
  "builder.channel.recipient.inbox": {
    es: "Avisa en la Bandeja a todas las personas del cliente.",
    en: "Notifies every person of the client in the Inbox.",
  },
  "builder.channel.recipient.remove": { es: "Quitar a {name}", en: "Remove {name}" },
  "builder.channel.recipient.unnamed": { es: "esta persona", en: "this person" },
  "builder.channel.recipient.nameRequired": { es: "Escribe el nombre de cada persona.", en: "Type each person’s name." },
  "builder.channel.recipient.phoneRequired": { es: "Escribe el WhatsApp de {name}.", en: "Type {name}’s WhatsApp." },
  "builder.channel.recipient.emailInvalid": { es: "El correo de {name} no es válido.", en: "{name}’s email is not valid." },
  "builder.channel.summary": { es: "Incluir un resumen en el aviso", en: "Include a summary in the notice" },
  "builder.channel.summary.hint": {
    es: "Quién es el cliente, qué pedía y por qué se pasó a una persona. Nada más.",
    en: "Who the customer is, what they asked for and why it went to a person. Nothing else.",
  },
  "builder.channel.notify.channel": { es: "Los avisos por WhatsApp saldrán de este número.", en: "WhatsApp notices will come from this number." },
  "builder.channel.notify.auphere": {
    es: "Los avisos por WhatsApp saldrán del número de avisos de Auphere, porque este número aún no tiene aprobada la plantilla de aviso.",
    en: "WhatsApp notices will come from Auphere’s notices number, because this number does not have the notice template approved yet.",
  },
  // Spec 049, 7.1 (enmienda de 047, 33.3): ni plantilla en el canal ni número de
  // avisos de Auphere. La página no promete un aviso que no sale.
  "builder.channel.notify.none": {
    es: "Los avisos por WhatsApp no pueden salir: este número no tiene aprobada la plantilla de aviso y Auphere aún no tiene número de avisos. Avisa a tu equipo por correo o por la Bandeja.",
    en: "WhatsApp notices cannot go out: this number does not have the notice template approved and Auphere has no notices number yet. Notify your team by email or in the Inbox.",
  },
  "builder.channel.notify.none.social": {
    es: "Los avisos por WhatsApp no pueden salir: Auphere aún no tiene número de avisos. Avisa a tu equipo por correo o por la Bandeja.",
    en: "WhatsApp notices cannot go out: Auphere has no notices number yet. Notify your team by email or in the Inbox.",
  },
  // Instagram y Messenger no tienen plantillas: los avisos siempre salen de Auphere.
  "builder.channel.notify.auphere.social": {
    es: "Los avisos por WhatsApp saldrán del número de avisos de Auphere.",
    en: "WhatsApp notices will come from Auphere’s notices number.",
  },
  "builder.channel.triggers.title": { es: "Cuándo pasa a una persona", en: "When it hands over to a person" },
  "builder.channel.triggers.intro": { es: "Lo decide el agente, no el canal.", en: "The agent decides it, not the channel." },
  "builder.channel.triggers.none": { es: "El agente nunca pasa a una persona por su cuenta.", en: "The agent never hands over to a person on its own." },
  "builder.channel.triggers.edit": { es: "Cambiarlo en el agente", en: "Change it in the agent" },

  "builder.channel.wait.title": { es: "Mensaje de espera", en: "Waiting message" },
  "builder.channel.wait.intro": {
    es: "Lo que recibe el cliente mientras su conversación espera a una persona.",
    en: "What the customer gets while their conversation waits for a person.",
  },
  "builder.channel.wait.field": { es: "Mensaje", en: "Message" },
  "builder.channel.wait.hint": { es: "Hasta 500 caracteres.", en: "Up to 500 characters." },
  "builder.channel.wait.tooLong": { es: "Como mucho 500 caracteres.", en: "At most 500 characters." },

  "builder.channel.wizardStep": { es: "Paso {n} de {total} · {title}", en: "Step {n} of {total} · {title}" },
  "builder.channel.catalog.intro": {
    es: "El catálogo de Commerce Manager con el que el agente enseña productos como tarjetas en este número.",
    en: "The Commerce Manager catalogue the agent uses to show products as cards on this number.",
  },
  // Spec 049 (historia 3): los comentarios de una cuenta de Instagram.
  "builder.channel.comments.title": { es: "Comentarios", en: "Comments" },
  "builder.channel.comments.intro": {
    es: "Cuando alguien comenta una publicación, el agente le contesta por mensaje privado.",
    en: "When someone comments on a post, the agent answers them by private message.",
  },
  "builder.channel.comments.answer": { es: "Atender los comentarios", en: "Answer comments" },
  "builder.channel.comments.answer.hint": {
    es: "Un mensaje privado por comentario, dentro de los 7 días.",
    en: "One private message per comment, within 7 days.",
  },
  "builder.channel.comments.on": { es: "Sí", en: "Yes" },
  "builder.channel.comments.off": { es: "No", en: "No" },
  "builder.channel.comments.public": { es: "Respuesta pública bajo el comentario", en: "Public reply under the comment" },
  "builder.channel.comments.public.placeholder": { es: "Te escribimos por privado 📩", en: "We sent you a DM 📩" },
  "builder.channel.comments.public.hint": {
    es: "Se publica a la vez que el mensaje privado. Vacía, no se publica nada. Hasta 300 caracteres.",
    en: "Posted together with the private message. Empty, nothing is posted. Up to 300 characters.",
  },
  "builder.channel.comments.public.tooLong": { es: "Como mucho 300 caracteres.", en: "At most 300 characters." },
  "builder.channel.comments.public.none": { es: "Ninguna", en: "None" },
  "builder.channel.comments.save": { es: "Guardar comentarios", en: "Save comments" },
  "builder.channel.comments.saved": { es: "Comentarios guardados.", en: "Comments saved." },

  // Spec 076 (requisito 4): los resultados del agente, a los anuncios de Meta del cliente.
  "builder.channel.ads.title": { es: "Resultados en anuncios", en: "Results in ads" },
  "builder.channel.ads.intro": {
    es: "Cada reserva o pedido que el agente consigue en este número se le dice a Meta, para que los anuncios del cliente aprendan a quién mostrarse.",
    en: "Every booking or order the agent gets on this number is reported to Meta, so the client’s ads learn who to show up for.",
  },
  "builder.channel.ads.state": { es: "Estado", en: "Status" },
  "builder.channel.ads.state.on": { es: "Activada", en: "On" },
  "builder.channel.ads.state.off": { es: "Desactivada", en: "Off" },
  "builder.channel.ads.state.reauthorize": { es: "Falta un permiso de Meta", en: "A Meta permission is missing" },
  "builder.channel.ads.dataset": { es: "Conjunto de datos de Meta", en: "Meta dataset" },
  "builder.channel.ads.dataset.linked": { es: "Vinculado", en: "Linked" },
  "builder.channel.ads.dataset.none": { es: "Sin vincular", en: "Not linked" },
  "builder.channel.ads.sent7d": { es: "Enviados en los últimos 7 días", en: "Sent in the last 7 days" },
  "builder.channel.ads.on": { es: "Activar", en: "Turn on" },
  "builder.channel.ads.retry": { es: "Activar de nuevo", en: "Turn on again" },
  "builder.channel.ads.off": { es: "Desactivar", en: "Turn off" },
  "builder.channel.ads.off.hint": {
    es: "Al desactivarla, lo que aún no salió hacia Meta no se envía.",
    en: "When you turn it off, what has not reached Meta yet is not sent.",
  },
  "builder.channel.ads.on.done": { es: "Los resultados de este número ya van a Meta.", en: "This number’s results now go to Meta." },
  "builder.channel.ads.off.done": { es: "Este número ya no envía resultados a Meta.", en: "This number no longer sends results to Meta." },
  "builder.channel.ads.confirm.title": { es: "¿Enviar los resultados a Meta?", en: "Send the results to Meta?" },
  "builder.channel.ads.confirm.body": {
    es: "Esto es lo que Meta recibe de cada reserva o pedido que el agente consigue en este número.",
    en: "This is what Meta gets for every booking or order the agent gets on this number.",
  },
  "builder.channel.ads.confirm.what": {
    es: "El tipo de resultado (reserva, pedido o cancelación), su importe y su moneda.",
    en: "The kind of result (booking, order or cancellation), its amount and its currency.",
  },
  "builder.channel.ads.confirm.who": {
    es: "Quién lo consiguió: el clic en el anuncio por el que llegó, o su teléfono cifrado si no llegó por uno.",
    en: "Who it was: the ad click they came from, or their encrypted phone number if they did not come from one.",
  },
  "builder.channel.ads.confirm.never": {
    es: "Nunca los mensajes, el nombre ni el servicio, ni nada de quien se dio de baja en este número.",
    en: "Never the messages, the name or the service, nor anything about people who opted out on this number.",
  },
  "builder.channel.ads.confirm.agree": {
    es: "El negocio puede compartir estos datos con Meta para medir sus anuncios.",
    en: "The business may share this data with Meta to measure its ads.",
  },
  "builder.channel.ads.reauthorize.title": { es: "Hay que volver a conectar el número", en: "The number has to be connected again" },
  "builder.channel.ads.reauthorize.body": {
    es: "La conexión de este número con Meta no incluye el permiso para enviar resultados. Vuelve a conectarlo y acepta el permiso nuevo. El agente sigue atendiendo igual.",
    en: "This number’s connection to Meta does not include the permission to send results. Connect it again and accept the new permission. The agent keeps answering as usual.",
  },
  "builder.channel.ads.reauthorize.readonly": {
    es: "La conexión de este número con Meta no incluye el permiso para enviar resultados. Quien gestiona los canales del cliente tiene que volver a conectarlo.",
    en: "This number’s connection to Meta does not include the permission to send results. Whoever manages the client’s channels has to connect it again.",
  },
  "builder.channel.ads.reauthorize.paused": {
    es: "La conexión de este número con Meta no incluye el permiso para enviar resultados. Reanuda el número y después vuelve a conectarlo.",
    en: "This number’s connection to Meta does not include the permission to send results. Resume the number, then connect it again.",
  },
  "builder.channel.ads.reconnect": { es: "Volver a conectar", en: "Connect again" },
  "builder.channel.ads.reconnect.done": {
    es: "Número conectado de nuevo. Confirma para activar los resultados.",
    en: "Number connected again. Confirm to turn the results on.",
  },
  "builder.channel.ads.error.title": { es: "El último envío a Meta falló", en: "The last send to Meta failed" },
  "builder.channel.ads.error.reauthorize": {
    es: "Falta el permiso para enviar resultados. Vuelve a conectar el número.",
    en: "The permission to send results is missing. Connect the number again.",
  },
  "builder.channel.ads.error.page_required": {
    es: "Meta pide que la cuenta de WhatsApp esté unida a una página de Facebook del negocio. Únela en Meta y los siguientes saldrán solos.",
    en: "Meta asks for the WhatsApp account to be linked to a Facebook Page of the business. Link it at Meta and the next ones go out on their own.",
  },
  "builder.channel.ads.error.too_old": {
    es: "Un resultado no pudo salir en 7 días y Meta ya no lo acepta. Los nuevos siguen saliendo.",
    en: "A result could not go out within 7 days and Meta no longer accepts it. New ones keep going out.",
  },
  "builder.channel.ads.error.no_identity": {
    es: "Un resultado no tenía ni clic ni teléfono con el que decirle a Meta quién era, y no se envió.",
    en: "A result had neither a click nor a phone number to tell Meta who it was, so it was not sent.",
  },
  "builder.channel.ads.error.meta_unavailable": {
    es: "Meta no respondió. Prueba otra vez en unos minutos.",
    en: "Meta did not answer. Try again in a few minutes.",
  },
  "builder.channel.ads.error.other": {
    es: "Meta rechazó un resultado. Los siguientes se siguen intentando. Si se repite, escríbenos.",
    en: "Meta turned down a result. The next ones keep being tried. If it happens again, write to us.",
  },

  "builder.channel.account.title": { es: "La cuenta en Meta", en: "The account at Meta" },
  "builder.channel.account.intro": { es: "Lo que Meta dice de este número. Se actualiza solo cuando Meta avisa.", en: "What Meta says about this number. It updates itself when Meta tells us." },
  "builder.channel.account.name": { es: "Nombre visible", en: "Display name" },
  "builder.channel.account.name.pending": { es: "«{name}», en revisión en Meta", en: "«{name}», under review at Meta" },
  "builder.channel.account.name.rejected": { es: "Meta rechazó «{name}». Motivo: {reason}", en: "Meta rejected «{name}». Reason: {reason}" },
  "builder.channel.account.username": { es: "Nombre de usuario", en: "Username" },
  "builder.channel.account.username.pending": { es: "@{username}, pendiente en Meta", en: "@{username}, pending at Meta" },
  "builder.channel.account.quality": { es: "Calidad", en: "Quality" },
  "builder.channel.account.quality.GREEN": { es: "Alta", en: "High" },
  "builder.channel.account.quality.YELLOW": { es: "Media", en: "Medium" },
  "builder.channel.account.quality.RED": { es: "Baja", en: "Low" },
  "builder.channel.account.limit": { es: "Límite de mensajes", en: "Messaging limit" },
  "builder.channel.account.limit.people": { es: "{n} personas al día en mensajes que inicia el negocio", en: "{n} people a day in business-initiated messages" },
  "builder.channel.account.limit.unlimited": { es: "Sin límite", en: "No limit" },
  "builder.channel.account.review": { es: "Revisión de la cuenta", en: "Account review" },
  "builder.channel.account.review.APPROVED": { es: "Aprobada", en: "Approved" },
  "builder.channel.account.review.PENDING": { es: "En revisión", en: "Under review" },
  "builder.channel.account.review.REJECTED": { es: "Rechazada", en: "Rejected" },
  "builder.channel.account.review.DEFERRED": { es: "Aplazada", en: "Deferred" },
  "builder.channel.account.alerts": { es: "Alertas activas de Meta", en: "Active alerts from Meta" },
  "builder.channel.account.alert.critical": { es: "Crítica", en: "Critical" },
  "builder.channel.account.alert.info": { es: "Informativa", en: "Informative" },
  "builder.channel.checks.title": { es: "Comprobaciones", en: "Checks" },
  "builder.channel.checks.intro": {
    es: "Avisan sin bloquear, salvo lo que necesita «A todos».",
    en: "They warn without blocking, except what “Everyone” needs.",
  },
  "builder.channel.check.ok": { es: "Bien", en: "OK" },
  "builder.channel.check.warn": { es: "Aviso", en: "Warning" },
  "builder.channel.check.block": { es: "Impide «A todos»", en: "Blocks “Everyone”" },
  "builder.channel.check.tests_up_to_date.ok": { es: "Las pruebas del agente están al día.", en: "The agent’s tests are up to date." },
  "builder.channel.check.tests_up_to_date.ko": { es: "Hay pruebas sin pasar o que fallan.", en: "Some tests have not run or are failing." },
  "builder.channel.check.escalation_recipient.ok": { es: "Hay alguien a quien avisar al escalar.", en: "There is someone to notify on hand-over." },
  "builder.channel.check.escalation_recipient.ko": { es: "Nadie recibe aviso cuando el agente escala.", en: "Nobody is notified when the agent hands over." },
  "builder.channel.check.agent_not_published": {
    es: "El agente no está guardado. «A todos» necesita un agente guardado.",
    en: "The agent is not saved. “Everyone” needs a saved agent.",
  },
  "builder.channel.check.bag_empty": {
    es: "La bolsa del cliente no tiene saldo. «A todos» necesita saldo.",
    en: "The client’s balance is empty. “Everyone” needs balance.",
  },
  "builder.channel.check.bag_empty.ask": {
    es: "Pide a quien gestiona el saldo que asigne saldo a este cliente.",
    en: "Ask whoever manages the balance to assign balance to this client.",
  },
  "builder.channel.check.escalation_template_missing": {
    es: "Los avisos por WhatsApp no pueden salir. Este número no tiene aprobada la plantilla de aviso y Auphere aún no tiene número de avisos. Avisa a Auphere. El correo y la Bandeja siguen avisando.",
    en: "WhatsApp notices cannot go out. This number does not have the notice template approved and Auphere has no notices number yet. Let Auphere know. Email and the Inbox still notify.",
  },
  "builder.channel.check.audience_admin_only_template": {
    es: "El agente viene de una plantilla solo para administradores.",
    en: "The agent comes from an admins-only template.",
  },
  "builder.channel.check.unknown": { es: "Comprobación: {code}", en: "Check: {code}" },
  "builder.channel.fix.run_tests": { es: "Ir a las pruebas", en: "Go to the tests" },
  "builder.channel.fix.add_recipient": { es: "Añadir a alguien", en: "Add someone" },
  "builder.channel.fix.publish_agent": { es: "Guardar el agente", en: "Save the agent" },
  "builder.channel.fix.assign_balance": { es: "Asignar saldo", en: "Assign balance" },

  // ── La barra de guardar, deshacer y el conflicto (32.7) ─────────────────
  "builder.channel.bar.dirty": { es: "Los cambios se aplican al guardar.", en: "Changes apply when you save." },
  "builder.channel.bar.clean": { es: "Todo guardado.", en: "Everything saved." },
  "builder.channel.bar.save": { es: "Guardar", en: "Save" },
  "builder.channel.bar.discard": { es: "Descartar", en: "Discard" },
  "builder.channel.saved": { es: "Guardado. Vale desde el siguiente mensaje.", en: "Saved. It applies from the next message." },
  "builder.channel.undo": { es: "Deshacer el último cambio", en: "Undo the last change" },
  "builder.channel.undo.until": { es: "Se puede deshacer hasta las {time}.", en: "It can be undone until {time}." },
  "builder.channel.undone": { es: "Cambio deshecho.", en: "Change undone." },
  "builder.channel.undo.closed": {
    es: "Han pasado más de 10 minutos: ya no se puede deshacer.",
    en: "More than 10 minutes have passed: it can no longer be undone.",
  },
  "builder.channel.conflict.title": { es: "Alguien guardó antes que tú", en: "Someone saved before you" },
  "builder.channel.conflict.body": {
    es: "Mientras editabas cambió {sections}. Tus cambios siguen aquí, sin guardar.",
    en: "While you were editing, {sections} changed. Your changes are still here, unsaved.",
  },
  "builder.channel.conflict.mine": { es: "Guardar los míos encima", en: "Save mine on top" },
  "builder.channel.conflict.theirs": { es: "Ver lo que hay ahora", en: "See what is there now" },
  "builder.channel.section.audience": { es: "a quién responde", en: "who it answers" },
  "builder.channel.section.escalation": { es: "el escalado", en: "the hand-over" },
  "builder.channel.section.wait_message": { es: "el mensaje de espera", en: "the waiting message" },
  "builder.channel.section.unknown": { es: "la configuración", en: "the settings" },
  "builder.channel.section.and": { es: " y ", en: " and " },
  "builder.channel.error.agent_not_published": { es: "«A todos» necesita el agente guardado.", en: "“Everyone” needs the agent saved." },
  "builder.channel.error.bag_empty": { es: "«A todos» necesita saldo en la bolsa del cliente.", en: "“Everyone” needs balance in the client’s bag." },
  "builder.channel.error.audience_admin_only_template": {
    es: "Este agente viene de una plantilla solo para administradores: no puede responder a todos.",
    en: "This agent comes from an admins-only template: it cannot answer everyone.",
  },
  "builder.channel.error.too_many_numbers": { es: "Como mucho {limit} números por lista.", en: "At most {limit} numbers per list." },
  "builder.channel.error.generic": { es: "No se pudo guardar. Inténtalo de nuevo.", en: "It could not be saved. Try again." },

  // ── El historial (32.7) ─────────────────────────────────────────────────
  "builder.channel.history.title": { es: "Historial", en: "History" },
  "builder.channel.history.empty": { es: "Todavía no hay cambios.", en: "No changes yet." },
  "builder.channel.history.error": { es: "No pudimos cargar el historial.", en: "We could not load the history." },
  "builder.channel.history.by": { es: "{actor} · {date}", en: "{actor} · {date}" },
  "builder.channel.history.origin.undo": { es: "Deshecho", en: "Undone" },
  "builder.channel.history.origin.connect": { es: "Al conectar", en: "On connecting" },
  "builder.channel.history.undone": { es: "Se deshizo después", en: "Undone later" },
  "builder.channel.history.nothing": { es: "Sin cambios visibles", en: "No visible changes" },
  "builder.channel.change.mode": { es: "A quién responde: {before} → {after}", en: "Who it answers: {before} → {after}" },
  "builder.channel.change.tests": { es: "Números de prueba: {before} → {after}", en: "Test numbers: {before} → {after}" },
  "builder.channel.change.exceptions": { es: "Excepciones: {before} → {after}", en: "Exceptions: {before} → {after}" },
  "builder.channel.change.recipients": { es: "Personas a las que avisar: {before} → {after}", en: "People to notify: {before} → {after}" },
  "builder.channel.change.summary": { es: "Resumen en el aviso: {before} → {after}", en: "Summary in the notice: {before} → {after}" },
  "builder.channel.change.wait": { es: "Mensaje de espera: {before} → {after}", en: "Waiting message: {before} → {after}" },
  "builder.channel.count.numbers.none": { es: "ninguno", en: "none" },
  "builder.channel.count.numbers.one": { es: "1 número", en: "1 number" },
  "builder.channel.count.numbers.other": { es: "{n} números", en: "{n} numbers" },
  "builder.channel.count.people.none": { es: "nadie", en: "nobody" },
  "builder.channel.count.people.one": { es: "1 persona", en: "1 person" },
  "builder.channel.count.people.other": { es: "{n} personas", en: "{n} people" },
  "builder.channel.yes": { es: "sí", en: "yes" },
  "builder.channel.no": { es: "no", en: "no" },
  "builder.channel.wait.none": { es: "sin mensaje", en: "no message" },
  "builder.channel.wait.some": { es: "con mensaje", en: "with a message" },
} as const;
