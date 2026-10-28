/** ES/EN del carril `channels-proto` — la pestaña Canales del agente tal como
 *  la pinta el prototipo aprobado «Consola de partners v2» (spec 047,
 *  `evidence/prototipo/agente.md` §7, §10.1, §10.2 y hueco H4): el asistente
 *  de cuatro pasos con la rejilla de canales, la lista de números, el modal
 *  «Conectar WhatsApp», el velo de Meta y la tarjeta del enlace pendiente.
 *
 *  Solo las frases nuevas: el estado de cada número, el ⋯ y el enlace del
 *  dueño siguen en `builder-channels.ts`, y la conexión con Meta en
 *  `channels.ts`. Los nombres de las apps (WhatsApp, Messenger…) son marcas y
 *  viven en el código. Reglas: nunca el constructor, «conector» y no
 *  «integración», sin punto y coma (`words.test.ts`). Meta se abre en una
 *  ventana emergente (`lib/meta-fb-sdk.ts`, `popup=yes`), no en una pestaña:
 *  el texto dice «ventana». */
export const channelsProtoMessages = {
  // ── El asistente: pasos (§7.1) ──
  "channels.proto.steps": { es: "Pasos", en: "Steps" },
  "channels.proto.step.done": { es: "Hecho", en: "Done" },
  "channels.proto.step.choose": { es: "Elegir canal", en: "Choose a channel" },
  "channels.proto.step.choose.hint": { es: "Por dónde escribirán los clientes de este negocio.", en: "Where this business’s customers will write." },
  "channels.proto.step.connect": { es: "Conectar", en: "Connect" },
  "channels.proto.step.connect.hint": { es: "Autoriza la cuenta del proveedor y crea el canal.", en: "Authorise the provider’s account and create the channel." },
  "channels.proto.step.configure": { es: "Configurar el canal", en: "Set up the channel" },
  "channels.proto.step.configure.hint": { es: "A quién responde, excepciones y a quién escala.", en: "Who it answers, exceptions and who it escalates to." },
  "channels.proto.step.ready": { es: "¡Listo!", en: "Done!" },
  "channels.proto.step.ready.hint": { es: "El agente ya responde por aquí.", en: "The agent now answers here." },

  // ── El asistente: la rejilla (§7.1) ──
  "channels.proto.pick.title": { es: "Elige un canal", en: "Choose a channel" },
  "channels.proto.pick.intro": {
    es: "Los de Meta van primero. Un agente puede tener varios números del mismo canal. Los marcados «Próximamente» todavía no se pueden conectar.",
    en: "Meta’s come first. An agent can have several numbers of the same channel. The ones marked “Coming soon” cannot be connected yet.",
  },
  "channels.proto.pick.list": { es: "Canales", en: "Channels" },
  "channels.proto.meta": { es: "Meta", en: "Meta" },
  "channels.proto.soon": { es: "Próximamente", en: "Coming soon" },
  "channels.proto.pending": { es: "Pendiente", en: "Pending" },
  "channels.proto.cta": { es: "Conectar", en: "Connect" },
  "channels.proto.cta.another": { es: "Conectar otro número", en: "Connect another number" },
  "channels.proto.cta.aria": { es: "Conectar {name}", en: "Connect {name}" },
  "channels.proto.connected.one": { es: "1 conectado", en: "1 connected" },
  "channels.proto.connected.other": { es: "{n} conectados", en: "{n} connected" },
  "channels.proto.kind.whatsapp": {
    es: "Atiende a los clientes en su número de WhatsApp Business, por la API de Meta.",
    en: "Serves customers on their WhatsApp Business number, through Meta’s API.",
  },
  "channels.proto.kind.whatsapp.note": {
    es: "Coexistencia o Cloud API. El negocio puede seguir usando su app.",
    en: "Coexistence or Cloud API. The business can keep using its app.",
  },
  "channels.proto.kind.messenger": { es: "Mensajes de la página de Facebook del negocio.", en: "Messages to the business’s Facebook page." },
  "channels.proto.kind.instagram": {
    es: "Mensajes directos y respuestas a comentarios de Instagram.",
    en: "Direct messages and replies to Instagram comments.",
  },
  "channels.proto.kind.threads": { es: "Conversaciones de la cuenta de Threads del negocio.", en: "Conversations of the business’s Threads account." },
  "channels.proto.kind.tiktok": {
    es: "Responde los mensajes directos de la cuenta de empresa de TikTok.",
    en: "Answers the direct messages of the TikTok business account.",
  },
  "channels.proto.kind.tiktok.note": { es: "Pendiente de la aprobación de TikTok.", en: "Waiting for TikTok’s approval." },
  "channels.proto.kind.telegram": { es: "Un bot de Telegram que atiende con el agente del cliente.", en: "A Telegram bot that answers with the client’s agent." },
  "channels.proto.kind.x": { es: "Mensajes directos de la cuenta de X del negocio.", en: "Direct messages of the business’s X account." },
  "channels.proto.linkPending": {
    es: "Ya hay un enlace pendiente para este canal. Revócalo para empezar otra conexión.",
    en: "There is already a pending link for this channel. Revoke it to start another connection.",
  },

  // ── Con canales: la lista (§7.2) ──
  "channels.proto.add": { es: "Añadir otro canal", en: "Add another channel" },
  "channels.proto.row.unset": { es: "sin configurar: todavía no responde", en: "not set up: it does not answer yet" },
  "channels.proto.row.team.one": { es: "responde solo a 1 número de prueba", en: "answers only 1 test number" },
  "channels.proto.row.team.other": { es: "responde solo a {n} números de prueba", en: "answers only {n} test numbers" },
  "channels.proto.row.everyone": { es: "responde a todos", en: "answers everyone" },
  "channels.proto.row.everyone.one": { es: "responde a todos salvo 1 excepción", en: "answers everyone but 1 exception" },
  "channels.proto.row.everyone.other": { es: "responde a todos salvo {n} excepciones", en: "answers everyone but {n} exceptions" },
  "channels.proto.row.escalates": { es: "escala a {names}", en: "escalates to {names}" },

  // ── Enlace pendiente (§7.3) ──
  "channels.proto.linkCard.title": { es: "Enlace enviado al cliente · WhatsApp", en: "Link sent to the client · WhatsApp" },
  "channels.proto.linkCard.note": {
    es: "Caduca el {date}. Cuando el cliente termine en Meta, el canal aparece aquí y te avisamos. Si el enlace se perdió, crea otro: no se puede volver a enseñar.",
    en: "Expires on {date}. When the client finishes at Meta, the channel shows up here and we let you know. If the link got lost, create another one: it cannot be shown again.",
  },

  // ── Conectar WhatsApp (§10.1) ──
  "channels.proto.connect.title": { es: "Conectar WhatsApp", en: "Connect WhatsApp" },
  "channels.proto.connect.body": {
    es: "Elige cómo se conecta el número de {name}. Al continuar se abre la ventana de Meta.",
    en: "Choose how {name}’s number connects. When you continue, Meta’s window opens.",
  },
  "channels.proto.connect.body.noName": {
    es: "Elige cómo se conecta el número del negocio. Al continuar se abre la ventana de Meta.",
    en: "Choose how the business’s number connects. When you continue, Meta’s window opens.",
  },
  "channels.proto.connect.modes": { es: "Modo de conexión", en: "Connection mode" },
  "channels.proto.connect.coexistence": { es: "Coexistencia", en: "Coexistence" },
  "channels.proto.connect.recommended": { es: "Recomendado", en: "Recommended" },
  "channels.proto.connect.coexistence.hint": {
    es: "Mantener la app WhatsApp Business. El equipo sigue respondiendo desde el móvil y el agente atiende a la vez.",
    en: "Keep the WhatsApp Business app. The team keeps answering from the phone and the agent serves at the same time.",
  },
  "channels.proto.connect.cloud_api": { es: "Cloud API", en: "Cloud API" },
  "channels.proto.connect.cloud_api.hint": {
    es: "Número nuevo o migrado. Si el número está en la app WhatsApp Business, deja de funcionar allí.",
    en: "New or migrated number. If the number is on the WhatsApp Business app, it stops working there.",
  },
  "channels.proto.connect.off": { es: "No está activado en esta consola.", en: "Not enabled on this console." },
  "channels.proto.connect.share.lead": { es: "¿No tienes la cuenta de Meta del negocio?", en: "You do not have the business’s Meta account?" },
  "channels.proto.connect.share.body": {
    es: "Comparte un enlace y el dueño conecta desde su dispositivo.",
    en: "Share a link and the owner connects from their own device.",
  },
  "channels.proto.connect.share": { es: "Compartir un enlace", en: "Share a link" },
  "channels.proto.connect.opens": { es: "Se abre una ventana nueva", en: "A new window opens" },
  "channels.proto.connect.go": { es: "Conectar", en: "Connect" },
  "channels.proto.link.title": { es: "Enlace para el cliente", en: "Link for the client" },
  "channels.proto.link.back": { es: "Atrás", en: "Back" },
  "channels.proto.link.done": { es: "Listo, ya lo compartí", en: "Done, I shared it" },

  // ── El velo de Meta (§10.2) ──
  "channels.proto.veil.title": { es: "Continúa en la ventana de Meta", en: "Carry on in Meta’s window" },
  "channels.proto.veil.coexistence": {
    es: "Se abrió una ventana de Facebook. Inicia sesión con la cuenta que administra {name}, elige la cuenta de WhatsApp Business y escanea el código desde la app WhatsApp Business. Al terminar, vuelve aquí.",
    en: "A Facebook window opened. Sign in with the account that manages {name}, pick the WhatsApp Business account and scan the code from the WhatsApp Business app. When you are done, come back here.",
  },
  "channels.proto.veil.cloud_api": {
    es: "Se abrió una ventana de Facebook. Inicia sesión con la cuenta que administra {name}, elige la cuenta de WhatsApp Business y confirma el número con el código. Al terminar, vuelve aquí.",
    en: "A Facebook window opened. Sign in with the account that manages {name}, pick the WhatsApp Business account and confirm the number with the code. When you are done, come back here.",
  },
  "channels.proto.veil.theBusiness": { es: "el negocio", en: "the business" },
  "channels.proto.veil.inUse": { es: "Ese número ya está conectado en otra cuenta", en: "That number is already connected on another account" },
  "channels.proto.veil.closed": { es: "Se cerró la ventana de Meta", en: "Meta’s window was closed" },
  "channels.proto.veil.closed.body": {
    es: "No se conectó nada. Puedes volver a intentarlo cuando quieras.",
    en: "Nothing was connected. You can try again whenever you want.",
  },
  "channels.proto.veil.failed": { es: "No se pudo conectar", en: "It could not be connected" },
  "channels.proto.veil.retry": { es: "Intentar de nuevo", en: "Try again" },

  // ── Al volver de Meta ──
  "channels.proto.done": {
    es: "WhatsApp conectado. Configura el canal para que empiece a responder.",
    en: "WhatsApp connected. Set up the channel so it starts answering.",
  },
  "channels.proto.done.elsewhere": {
    es: "{phone} conectado. Por ahora lo atiende el agente principal. Cuando este agente esté guardado, pásalo aquí desde el ⋯ del número.",
    en: "{phone} connected. For now the main agent answers it. Once this agent is saved, move it here from the number’s ⋯.",
  },
  "channels.proto.error.quota": {
    es: "Este cliente ya tiene conectados todos los números que permite tu cuenta. Desconecta uno o pide a Auphere que amplíe el límite.",
    en: "This client already has all the numbers your account allows. Disconnect one or ask Auphere to raise the limit.",
  },
} as const;
