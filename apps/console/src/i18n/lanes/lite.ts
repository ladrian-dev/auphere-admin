/**
 * ES/EN messages of lane `lite` (spec 030): the client console — shell,
 * Panel and Consumo for a single client. Spread into `i18n/messages.ts`.
 */
export const liteMessages = {
  "lite.panel.greeting": { es: "Hola, {name}", en: "Hi, {name}" },
  // ── Panel (R4) ───────────────────────────────────────────────────
  "lite.panel.partial": {
    es: "Una parte del Panel no se pudo cargar. Recarga para intentarlo de nuevo.",
    en: "Part of the Panel could not load. Reload to try again.",
  },
  "lite.panel.kpis": { es: "Resumen", en: "Summary" },
  "lite.spend.title": { es: "Gasto del mes", en: "This month's spend" },
  "lite.spend.see": { es: "Ver consumo", en: "See usage" },
  "lite.kpi.conversations": { es: "Conversaciones", en: "Conversations" },
  "lite.kpi.waiting": { es: "Esperan a una persona", en: "Waiting for a person" },
  "lite.kpi.waiting.hint": { es: "Tus agentes pidieron ayuda en la bandeja", en: "Your agents asked for help in the inbox" },
  "lite.kpi.balance": { es: "Saldo disponible", en: "Available balance" },
  "lite.kpi.balance.runway": { es: "Cubre {days} de {left} días del mes", en: "Covers {days} of {left} days this month" },
  "lite.kpi.balance.runway.aria": { es: "Días del mes que cubre el saldo", en: "Days of the month the balance covers" },
  "lite.kpi.balance.noSpend": { es: "Sin gasto en los últimos 7 días", en: "No spend in the last 7 days" },
  "lite.kpi.balance.unassigned": { es: "Todavía no tienes un tope asignado", en: "You don't have a spending limit yet" },
  "lite.kpi.balance.out": { es: "Saldo agotado: el agente no responde", en: "Balance used up: the agent is not answering" },
  "lite.attention.title": { es: "Necesita tu atención", en: "Needs your attention" },
  "lite.attention.inbox": { es: "Bandeja de entrada", en: "Inbox" },
  "lite.attention.waiting": { es: "{count} conversaciones esperan a una persona", en: "{count} conversations are waiting for a person" },
  "lite.attention.waiting.one": { es: "1 conversación espera a una persona", en: "1 conversation is waiting for a person" },
  "lite.attention.attend": { es: "Atender", en: "Attend" },
  "lite.attention.balance": { es: "Saldo", en: "Balance" },
  "lite.attention.balance_out": { es: "Tu saldo se agotó y el agente no responde", en: "Your balance is used up and the agent is not answering" },
  "lite.attention.balance_low": { es: "Te quedarás sin saldo en unos {days} días", en: "You will run out of balance in about {days} days" },
  "lite.attention.ask.partner": { es: "Pide más saldo a {name}.", en: "Ask {name} for more balance." },
  "lite.attention.ask.auphere": { es: "Pide más saldo a Auphere.", en: "Ask Auphere for more balance." },
  "lite.ok.withInbox": {
    es: "Todo en orden. Nada espera a una persona y el saldo alcanza para el mes.",
    en: "All good. Nothing is waiting for a person and the balance lasts the month.",
  },
  "lite.ok": { es: "Todo en orden. El saldo alcanza para el mes.", en: "All good. The balance lasts the month." },
  "lite.ok.noBalance.withInbox": { es: "Todo en orden. Nada espera a una persona.", en: "All good. Nothing is waiting for a person." },
  // ── invitación (R1.4) ────────────────────────────────────────────
  "invite.client.body": {
    es: "Te dieron acceso a la consola de {client}. Crea tu contraseña para entrar.",
    en: "You were given access to {client}'s console. Create your password to sign in.",
  },
  // ── sin acceso (R2.7) ────────────────────────────────────────────
  "noAccess.client.title": { es: "No puedes entrar en esta consola", en: "You can't enter this console" },
  "noAccess.client.disabled": {
    es: "La consola de {client} está apagada por ahora. Si crees que es un error, escribe a quien te dio acceso.",
    en: "{client}'s console is switched off for now. If you think this is a mistake, write to whoever gave you access.",
  },
  "noAccess.client.revoked": {
    es: "Ya no tienes acceso a la consola de {client}.",
    en: "You no longer have access to {client}'s console.",
  },
  // ── Consumo (R5) ─────────────────────────────────────────────────
  "lite.usage.intro": { es: "Tu saldo, lo que gastas y lo que se gasta cada día.", en: "Your balance, what you spend and what is spent each day." },
  "lite.usage.intro.agents": {
    es: "Tu saldo, lo que gasta cada agente y lo que se gasta cada día.",
    en: "Your balance, what each agent spends and what is spent each day.",
  },
  "lite.usage.partial": {
    es: "Una parte del Consumo no se pudo cargar. Recarga para intentarlo de nuevo.",
    en: "Part of Usage could not load. Reload to try again.",
  },
  "lite.usage.cards": { es: "Saldo y gasto", en: "Balance and spend" },
  "lite.usage.balance.runway": { es: "Cubre unos {days} días al ritmo de esta semana", en: "Lasts about {days} days at this week's pace" },
  "lite.usage.unreadable": { es: "No se pudo leer ahora", en: "Could not be read right now" },
  "lite.usage.month.projection": { es: "A este ritmo, {amount} a fin de mes", en: "At this pace, {amount} by the end of the month" },
  "lite.usage.month.none": { es: "Sin gasto este mes", en: "No spend this month" },
  "lite.usage.conversations": { es: "Conversaciones del mes", en: "Conversations this month" },
  "lite.usage.conversations.avg": { es: "{amount} de media cada una", en: "{amount} on average each" },
  "lite.usage.byAgent.title": { es: "Gasto por agente", en: "Spend per agent" },
  "lite.usage.agent": { es: "Agente", en: "Agent" },
  "lite.usage.agent.all": { es: "Todos los agentes", en: "All agents" },
  "lite.usage.byAgent.agent": { es: "Agente", en: "Agent" },
  "lite.usage.byAgent.spent": { es: "Gastado este mes", en: "Spent this month" },
  "lite.usage.byAgent.share": { es: "Parte del gasto", en: "Share of spend" },
  "lite.usage.detail.hint": {
    es: "Lo que mide la plataforma por dentro, por medidor. Para revisar con detalle o exportar.",
    en: "What the platform measures inside, per meter. To review in detail or export.",
  },
  // ── campana (R15) ────────────────────────────────────────────────
  "lite.bell.title": { es: "Avisos", en: "Notifications" },
  "lite.bell.readAll": { es: "Marcar todo como leído", en: "Mark all as read" },
  "lite.bell.loading": { es: "Cargando avisos…", en: "Loading notifications…" },
  "lite.bell.empty": { es: "No tienes avisos.", en: "You have no notifications." },
  "lite.bell.error": { es: "No se pudieron cargar los avisos. Vuelve a abrir la campana.", en: "Notifications could not load. Open the bell again." },
  "lite.notif.inbox.waiting": { es: "{contact} espera a una persona", en: "{contact} is waiting for a person" },
  "lite.notif.client.balance_low": { es: "Tu saldo alcanza para unos {days} días", en: "Your balance lasts about {days} more days" },
  "lite.notif.client.balance_out": { es: "Tu saldo se agotó: el agente no responde", en: "Your balance is used up: the agent is not answering" },
  "lite.notif.someone": { es: "Un contacto", en: "A contact" },
} as const;
