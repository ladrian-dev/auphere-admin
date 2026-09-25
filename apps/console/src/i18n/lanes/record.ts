/** ES/EN messages of lane `record` — la ficha de cliente (spec 017).
 *  Se esparce en `i18n/messages.ts`. Una clave sin consumidor es huérfana
 *  y la caza `__tests__/no-orphan-keys.test.ts`, así que aquí solo entra
 *  lo que la iteración en curso usa. */
export const recordMessages = {
  // ── navegación de la ficha (R2) ───────────────────────────────────
  "clients.nav.label": { es: "Sección de la ficha", en: "Record section" },
  "clients.nav.group.observe": { es: "Observar", en: "Observe" },
  "clients.nav.group.configure": { es: "Configurar", en: "Configure" },
  "clients.nav.group.connect": { es: "Conectar", en: "Connect" },
  "clients.nav.capabilities": { es: "Capacidades", en: "Capabilities" },
  "clients.nav.integrations": { es: "Integraciones", en: "Integrations" },
  "clients.nav.mark.draft": { es: "cambios sin publicar", en: "unpublished changes" },
  "clients.nav.mark.incident": { es: "incidencia", en: "incident" },
  "clients.nav.suffix.draft": { es: "sin publicar", en: "unpublished" },
  "clients.nav.suffix.incident": { es: "incidencia", en: "incident" },

  // ── puesta en marcha (R1) ─────────────────────────────────────────
  "clients.setup.title": { es: "Puesta en marcha", en: "Getting started" },
  "clients.setup.description": {
    es: "Lo que falta para que el agente atienda. Los cuatro pasos se pueden hacer en cualquier orden.",
    en: "What stands between this client and a working agent. The four steps can be done in any order.",
  },
  "clients.setup.done": { es: "{done} de {total} pasos hechos", en: "{done} of {total} steps done" },
  "clients.setup.agent": { es: "Agente", en: "Agent" },
  "clients.setup.channel": { es: "Canal", en: "Channel" },
  "clients.setup.quota": { es: "Crédito", en: "Credit" },
  "clients.setup.activation": { es: "Activación", en: "Activation" },
  "clients.setup.next": { es: "Siguiente paso", en: "Next step" },
  "clients.setup.next.agent": { es: "Preparar el agente", en: "Prepare the agent" },
  "clients.setup.next.channel": { es: "Conectar un canal", en: "Connect a channel" },
  "clients.setup.next.quota": { es: "Asignar crédito", en: "Assign credit" },
  "clients.setup.next.activation": { es: "Empezar a atender", en: "Start serving" },
  "clients.setup.why.agent": { es: "Sin una versión publicada, el agente no sabe qué decir.", en: "Without a published version the agent does not know what to say." },
  "clients.setup.why.channel": { es: "Un canal es por donde llegan los mensajes: hoy WhatsApp.", en: "A channel is how messages arrive: today, WhatsApp." },
  "clients.setup.why.quota": { es: "Los créditos son lo que el agente gasta al responder.", en: "Credits are what the agent spends when it answers." },
  "clients.setup.why.activation": { es: "El último clic: a partir de ahí el agente atiende.", en: "The last click: from then on the agent serves." },
  "clients.setup.who.agents": { es: "Lo hace el propietario, un administrador o un editor.", en: "The owner, an admin or a builder does this." },
  "clients.setup.who.channels": { es: "Lo hace el propietario, un administrador o un editor.", en: "The owner, an admin or a builder does this." },
  "clients.setup.who.usage": { es: "Lo hace el propietario o un administrador.", en: "The owner or an admin does this." },
  "clients.setup.who.clients": { es: "Lo hace el propietario, un administrador o un editor.", en: "The owner, an admin or a builder does this." },

  // ── crédito del cliente (R1.2) ────────────────────────────────────
  "clients.quota.title": { es: "Crédito", en: "Credit" },
  "clients.quota.label": { es: "Crédito restante", en: "Credit left" },
  "clients.quota.value": { es: "Quedan {remaining} de {cap} créditos", en: "{remaining} of {cap} credits left" },
  "clients.quota.spent": { es: "{spent} gastados este mes.", en: "{spent} spent this month." },
  "clients.quota.none": { es: "Sin crédito asignado. El agente no puede atender hasta que se le asigne.", en: "No credit assigned. The agent cannot serve until it has some." },
  "clients.quota.help": {
    es: "Lo que este cliente puede gastar cada mes. Se renueva el día 1; lo que sobra no se acumula.",
    en: "What this client may spend each month. It renews on the 1st; what is left does not carry over.",
  },
  "clients.quota.manage": { es: "Cambiar crédito", en: "Change credit" },

  // ── borrador sin publicar (R3) ────────────────────────────────────
  "draft.bar.unpublishedIn": { es: "Cambios sin publicar en", en: "Unpublished changes in" },
  "draft.bar.and": { es: "y", en: "and" },
  "draft.bar.diff": { es: "Ver los cambios", en: "See the changes" },
  "draft.bar.publish": { es: "Revisar y publicar", en: "Review and publish" },
  "draft.bar.publishing": { es: "Publicando…", en: "Publishing…" },
  "draft.bar.retry": { es: "Reintentar", en: "Try again" },
  "draft.bar.who": { es: "Puede publicar: el propietario, un administrador o un editor", en: "Can publish: the owner, an admin or a builder" },
  "draft.bar.announce": { es: "Hay cambios sin publicar en este cliente.", en: "This client has unpublished changes." },
  "draft.bar.failureAnnounce": { es: "No se pudo publicar. La versión activa no ha cambiado.", en: "Could not publish. The active version has not changed." },
  "draft.bar.failure": {
    es: "La versión que atiende no ha cambiado y el borrador no se ha perdido. Suele resolverse al reintentar.",
    en: "The serving version has not changed and the draft is not lost. Trying again usually resolves it.",
  },
  "draft.bar.published": { es: "Publicado. El agente ya responde con los cambios.", en: "Published. The agent now answers with the changes." },

  // ── la hoja que revisa antes de publicar (R3.2) ───────────────────
  "draft.diff.title": { es: "Publicar la versión {version}", en: "Publish version {version}" },
  "draft.diff.description": {
    es: "Lo que cambia respecto a la versión {active}, la que atiende ahora. Al publicar, el agente lo aplica al instante.",
    en: "What changes against version {active}, the one serving now. On publishing, the agent applies it at once.",
  },
  "draft.diff.descriptionFirst": {
    es: "Este cliente aún no tiene ninguna versión atendiendo: al publicar, esta será la primera.",
    en: "This client has no serving version yet: publishing makes this the first one.",
  },
  "draft.diff.loading": { es: "Leyendo los cambios…", en: "Reading the changes…" },
  "draft.diff.what": { es: "Qué", en: "What" },
  "draft.diff.before": { es: "Antes", en: "Before" },
  "draft.diff.after": { es: "Ahora", en: "Now" },
  "draft.diff.empty": { es: "El borrador no cambia nada respecto a la versión activa.", en: "The draft changes nothing against the active version." },
  "draft.diff.cancel": { es: "Cancelar", en: "Cancel" },
  "draft.diff.publish": { es: "Publicar la versión {version}", en: "Publish version {version}" },
  "draft.diff.enabled": { es: "activada", en: "on" },
  "draft.diff.disabled": { es: "apagada", en: "off" },
  "draft.diff.added": { es: "añadido", en: "added" },
  "draft.diff.removed": { es: "quitado", en: "removed" },
  "draft.diff.promptChanged": { es: "Las instrucciones del agente cambian.", en: "The agent's instructions change." },
  "draft.screen.settings": { es: "Ajustes", en: "Settings" },
  "draft.screen.capabilities": { es: "Capacidades", en: "Capabilities" },
  "draft.screen.knowledge": { es: "Conocimiento", en: "Knowledge" },
  "draft.screen.prompt": { es: "Instrucciones", en: "Instructions" },
  "draft.field.identity": { es: "Identidad", en: "Identity" },
  "draft.field.tone": { es: "Tono", en: "Tone" },
  "draft.field.objective": { es: "Objetivo", en: "Objective" },
  "draft.field.schedule": { es: "Horario", en: "Schedule" },
  "draft.field.languages": { es: "Idiomas", en: "Languages" },
  "draft.field.escalation": { es: "Escalado a una persona", en: "Escalation to a human" },
  "draft.field.ai_disclosure": { es: "Aviso de que es una IA", en: "Disclosure that it is an AI" },
} as const;
