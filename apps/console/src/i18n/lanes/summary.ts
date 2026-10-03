/** ES/EN del carril `summary` — el Resumen del cliente (spec 018, R1/R2).
 *
 *  El Resumen contesta **cuatro preguntas** y no enseña todos los datos: un
 *  resumen que lo enseña todo deja de resumir. El copy es lo que hace que
 *  cada bloque se lea como una respuesta y no como una etiqueta. */
export const summaryMessages = {
  // ── ¿atiende? ─────────────────────────────────────────────────────
  "sum.serving": { es: "Atendiendo", en: "Answering" },
  "sum.notServing": { es: "Sin atender · falta {what}", en: "Not answering · missing {what}" },
  "sum.agentLine": {
    es: "Agente · versión {v} · {channel}",
    en: "Agent · version {v} · {channel}",
  },
  "sum.agentLine.noAgent": { es: "Sin agente publicado", en: "No published agent" },
  "sum.channel.on": { es: "WhatsApp conectado · {phone}", en: "WhatsApp connected · {phone}" },
  "sum.channel.off": { es: "sin canal conectado", en: "no channel connected" },
  "sum.sector": { es: "Sector: {sector}", en: "Sector: {sector}" },
  "sum.seeAgent": { es: "Ver el agente", en: "See the agent" },

  // ── crédito y consumo ─────────────────────────────────────────────
  "sum.credit": { es: "Saldo y consumo", en: "Balance and usage" },
  "sum.credit.help": { es: "Lo que este cliente puede gastar, en dólares. El agente gasta al leer lo que le llega y al responder.", en: "What this client may spend, in dollars. The agent spends when it reads what arrives and replies." },
  "sum.credit.detail": { es: "Ver el detalle", en: "See the detail" },
  "sum.credit.value": { es: "Quedan {remaining} de {cap}", en: "{remaining} of {cap} left" },
  "sum.credit.spent": { es: "{spent} gastados este mes", en: "{spent} spent this month" },
  "sum.credit.none": { es: "Sin saldo asignado. Este cliente no tiene tope, así que no hay nada que medir todavía.", en: "No balance assigned. This client has no cap, so there is nothing to measure yet." },
  "sum.credit.empty": { es: "Sin saldo: el agente no está respondiendo.", en: "No balance left: the agent is not replying." },
  "sum.credit.assign": { es: "Asignar más saldo", en: "Assign more balance" },
  // Un cero aquí se leería como una caída, no como un cliente nuevo.
  "sum.credit.noActivity": {
    es: "Todavía no ha gastado nada: el agente aún no ha atendido ninguna conversación.",
    en: "It has not spent anything yet: the agent has not handled a single conversation.",
  },

  // ── conversaciones ────────────────────────────────────────────────
  "sum.conv": { es: "Conversaciones", en: "Conversations" },
  "sum.conv.window": { es: "Últimos 30 días", en: "Last 30 days" },
  "sum.conv.total": { es: "Conversaciones", en: "Conversations" },
  "sum.conv.escalated": { es: "Escaladas", en: "Escalated" },
  "sum.conv.escalated.share": { es: "{percent} % del total", en: "{percent} % of the total" },
  "sum.conv.failed": { es: "Mensajes fallidos", en: "Failed messages" },
  "sum.conv.noActivity": {
    es: "Todavía no ha habido ninguna conversación.",
    en: "There has not been a single conversation yet.",
  },

  // ── lo conectado ──────────────────────────────────────────────────
  "sum.connected": { es: "Lo que tiene conectado", en: "What it has connected" },
  "sum.connected.all": { es: "Conectores", en: "Connectors" },
  "sum.connected.unlocks": { es: "desbloquea {n} habilidades", en: "unlocks {n} skills" },
  "sum.connected.unlocksOne": { es: "desbloquea 1 habilidad", en: "unlocks 1 skill" },
  "sum.connected.more": { es: "{n} conectores más sin conectar.", en: "{n} more connectors not connected." },
  "sum.connected.fix": { es: "Reconectar", en: "Reconnect" },
  "sum.connected.none": {
    es: "Todavía no tiene nada conectado.",
    en: "Nothing connected yet.",
  },
  "sum.connected.noneYet": {
    es: "Todavía no tiene nada conectado. Hay {n} conectores disponibles.",
    en: "Nothing connected yet. There are {n} connectors available.",
  },

  // ── datos del cliente ─────────────────────────────────────────────
  "sum.data": { es: "Datos del cliente", en: "Client details" },
  // R2.4: se dice en voz alta, porque el partner ha aprendido que en esta
  // ficha casi todo lo que se toca acaba en un borrador. Esto no.
  "sum.data.help": {
    es: "Cambiarlos no toca lo que el agente hace, así que no crea un borrador.",
    en: "Changing these does not touch what the agent does, so it does not create a draft.",
  },

  // ── una lectura que no llegó ──────────────────────────────────────
  "sum.failed": { es: "No se pudo leer {what}.", en: "Could not read {what}." },
  "sum.failed.retry": { es: "Reintentar", en: "Retry" },
  "sum.failed.credit": { es: "el consumo", en: "the usage" },
  "sum.failed.conv": { es: "las conversaciones", en: "the conversations" },
  "sum.failed.connected": { es: "lo que tiene conectado", en: "what it has connected" },
} as const;
