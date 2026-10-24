/**
 * ES/EN messages of the «Añadir canal» wizard (spec 046). The same four steps
 * as the operator panel's (spec 035), in the partner's words. Spread into
 * `i18n/messages.ts`.
 */
export const channelWizardMessages = {
  "chw.add": { es: "Añadir canal", en: "Add channel" },
  "chw.steps": { es: "Pasos", en: "Steps" },
  "chw.step.choose": { es: "Elegir canal", en: "Choose a channel" },
  "chw.step.choose.body": { es: "Por dónde le escribirán a tu cliente.", en: "Where people will write to your client." },
  "chw.step.connect": { es: "Conectar", en: "Connect" },
  "chw.step.connect.body": { es: "El dueño del negocio autoriza su cuenta.", en: "The business owner authorises their account." },
  "chw.step.agent": { es: "Asignar agente", en: "Assign the agent" },
  "chw.step.agent.body": { es: "Para qué es el número y quién contesta.", en: "What the number is for and who answers." },
  "chw.step.done": { es: "¡Listo!", en: "Done!" },
  "chw.step.done.body": { es: "Pruébalo desde tu teléfono.", en: "Try it from your phone." },

  // ── step 1 · the catalog ──────────────────────────────────────────
  "chw.choose.title": { es: "Elige un canal", en: "Choose a channel" },
  "chw.choose.body": {
    es: "Por ahora se conecta WhatsApp. Los demás canales enseñan su estado.",
    en: "For now WhatsApp connects. The other channels show their state.",
  },
  "chw.choose.error.title": { es: "No se pudo leer la lista de canales", en: "The channel list could not be read" },
  "chw.choose.error.body": { es: "Vuelve a intentarlo en un momento.", en: "Try again in a moment." },
  "chw.tile.start": { es: "Conectar", en: "Connect" },
  "chw.availability.pending": { es: "Pendiente", en: "Pending" },
  "chw.availability.coming_soon": { es: "Próximamente", en: "Coming soon" },

  // ── step 2 · connect ──────────────────────────────────────────────
  "chw.connect.title": { es: "Conectar {name}", en: "Connect {name}" },
  "chw.connect.body": {
    es: "El número tiene que ser del negocio y tener una cuenta de WhatsApp Business. Elige cómo lo conectas.",
    en: "The number must be the business's own, with a WhatsApp Business account. Choose how to connect it.",
  },
  "chw.connect.link.title": { es: "Enviar un enlace al dueño del negocio", en: "Send a link to the business owner" },
  "chw.connect.link.badge": { es: "Recomendado", en: "Recommended" },
  "chw.connect.link.body": {
    es: "Lo abre en su teléfono, donde ya tiene su cuenta de Meta, y conecta él mismo su número. Es lo más seguro y lo que mejor funciona si sigue usando la app WhatsApp Business.",
    en: "They open it on their phone, where they already have their Meta account, and connect the number themselves. It is the safest way and the one that works best if they keep using the WhatsApp Business app.",
  },
  "chw.connect.link.after": {
    es: "Cuando el dueño termine, el número aparece aquí y puedes seguir.",
    en: "When the owner finishes, the number shows up here and you can go on.",
  },
  "chw.connect.here.title": { es: "Conectarlo desde aquí", en: "Connect it from here" },
  "chw.connect.here.body": {
    es: "Si tienes delante la cuenta de Meta del negocio, se abre la ventana de Meta y eliges el número.",
    en: "If you have the business's Meta account at hand, Meta's window opens and you choose the number.",
  },
  "chw.connect.desktop.body": {
    es: "La ventana de Meta no funciona dentro de la aplicación. Ábrelo en el navegador o envía el enlace al dueño.",
    en: "Meta's window does not work inside the app. Open it in the browser or send the link to the owner.",
  },
  "chw.connect.connected": { es: "Ya hay {count} números conectados.", en: "{count} numbers are already connected." },
  "chw.connect.connected.one": { es: "Ya hay 1 número conectado.", en: "1 number is already connected." },
  "chw.connect.next": { es: "Seguir con el número conectado", en: "Go on with the connected number" },
  "chw.back": { es: "Elegir otro canal", en: "Choose another channel" },

  // ── step 3 · the number's job and its agent ───────────────────────
  "chw.agent.title": { es: "Asignar agente", en: "Assign the agent" },
  "chw.agent.body": {
    es: "Elige para qué es este número y qué agente contesta en él.",
    en: "Choose what this number is for and which agent answers on it.",
  },
  "chw.agent.number": { es: "Número", en: "Number" },
  "chw.agent.purpose": { es: "¿Para qué es este número?", en: "What is this number for?" },
  "chw.agent.purpose.agent": { es: "Atiende a los clientes", en: "It serves customers" },
  "chw.agent.purpose.agent.body": {
    es: "El agente contesta los mensajes que lleguen.",
    en: "The agent answers the messages that come in.",
  },
  "chw.agent.purpose.notifications": { es: "Solo envía avisos", en: "It only sends notices" },
  "chw.agent.purpose.notifications.body": {
    es: "Manda confirmaciones y recordatorios. No contesta a nadie.",
    en: "It sends confirmations and reminders. It answers nobody.",
  },
  "chw.agent.who": { es: "Agente que contesta", en: "Agent that answers" },
  "chw.agent.unpublished": {
    es: "Este agente todavía no está publicado, así que no contestaría. Publícalo y vuelve aquí.",
    en: "This agent is not published yet, so it would not answer. Publish it and come back.",
  },
  "chw.agent.toAgent": { es: "Ir al agente", en: "Go to the agent" },
  "chw.agent.sendOnly": {
    es: "Este número solo envía avisos: ningún agente contesta en él.",
    en: "This number only sends notices: no agent answers on it.",
  },
  "chw.agent.submit": { es: "Guardar y terminar", en: "Save and finish" },
  "chw.agent.saving": { es: "Guardando…", en: "Saving…" },
  "chw.agent.empty.title": { es: "Todavía no hay ningún número conectado", en: "No number is connected yet" },
  "chw.agent.empty.body": {
    es: "Vuelve al paso anterior y termina la conexión. Si enviaste el enlace, espera a que el dueño lo use.",
    en: "Go back to the previous step and finish connecting. If you sent the link, wait for the owner to use it.",
  },
  "chw.agent.empty.action": { es: "Volver a Conectar", en: "Back to Connect" },
  "chw.agent.noAgents.title": { es: "Este cliente no tiene agente", en: "This client has no agent" },
  "chw.agent.noAgents.body": { es: "Crea su agente y vuelve aquí.", en: "Create their agent and come back." },

  // ── step 4 · done, and the truth about whether it answers ─────────
  "chw.done.title": { es: "¡El WhatsApp de {client} está conectado!", en: "{client}'s WhatsApp is connected!" },
  "chw.done.ready": {
    es: "Ya responde. Escríbele desde tu teléfono al {phone} para probarlo.",
    en: "It answers now. Write to {phone} from your phone to try it.",
  },
  "chw.done.readyNoPhone": {
    es: "Ya responde. Escríbele desde tu teléfono para probarlo.",
    en: "It answers now. Write to it from your phone to try it.",
  },
  "chw.done.notReady": {
    es: "El número está conectado, pero el agente todavía no contesta. Falta esto:",
    en: "The number is connected, but the agent does not answer yet. This is missing:",
  },
  "chw.done.audience": {
    es: "Ahora contesta solo a {count} números. Si escribes desde otro, no te contestará.",
    en: "It now answers only {count} numbers. Write from another one and it will not answer.",
  },
  "chw.done.audience.one": {
    es: "Ahora contesta solo a 1 número. Si escribes desde otro, no te contestará.",
    en: "It now answers only 1 number. Write from another one and it will not answer.",
  },
  "chw.done.audience.action": { es: "Cambiar a quién contesta", en: "Change who it answers" },
  "chw.done.notifications": {
    es: "Este número enviará avisos. Quien le escriba no recibirá respuesta por él.",
    en: "This number will send notices. Whoever writes to it gets no answer on it.",
  },
  "chw.done.channels": { es: "Ver canales", en: "See channels" },
  "chw.done.test": { es: "Probar un envío", en: "Try a send" },
  "chw.done.toClient": { es: "Ir a la ficha del cliente", en: "Go to the client's page" },
} as const;
