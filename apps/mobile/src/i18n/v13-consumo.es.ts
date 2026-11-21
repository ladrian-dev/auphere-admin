/** Spec 069 — Consumo y Ajustes: the app's own words, Spanish. Spread into `app.es.ts`. */
export const v13ConsumoEs = {
  // ── Consumo (R18) ────────────────────────────────────────────────
  // How long the balance lasts, at the 7-day pace (R18.1): from `days_left`, never a fixed figure.
  "v13.usage.lasts.months": "Para unos {n} meses, al ritmo de los últimos 7 días.",
  "v13.usage.lasts.days": "Para unos {n} días, al ritmo de los últimos 7 días.",
  "v13.usage.lasts.day": "Para 1 día, al ritmo de los últimos 7 días.",
  "v13.usage.lasts.lessThanDay": "Para menos de un día, al ritmo de los últimos 7 días.",
  // Whom to ask, as text and nothing to press (R18.2).
  "v13.usage.ask": "¿Necesitas más saldo? Pídeselo a {partner}.",
  // The chart (R18.1, R18.3): its amounts say their currency, so the label does not name one.
  "v13.usage.chart.aria": "Gasto por día",
  "v13.usage.chart.aria.week": "Gasto por semana",
  "v13.usage.chart.unit.day": "Por día",
  "v13.usage.chart.unit.week": "Por semana",
  "v13.usage.chart.week": "{from} – {to}",

  // ── Ajustes (R19, R17.2) ─────────────────────────────────────────
  "v13.settings.channels": "Canales conectados",
  "v13.settings.channels.agent": "{agent} atiende en todos",
  "v13.settings.channels.none": "Todavía no hay canales conectados. Se conectan desde la consola web.",
  "v13.settings.channel.whatsapp": "WhatsApp",
  "v13.settings.channel.instagram": "Instagram",
  "v13.settings.channel.messenger": "Messenger",
  "v13.settings.channel.on": "Conectado",
  "v13.settings.channel.off": "Sin conectar",
  "v13.settings.channel.some": "{n} de {total} conectados",
  "v13.settings.urgent.title": "¿Apagar el aviso urgente?",
  "v13.settings.urgent.body": "No sabrás en este teléfono cuándo alguien espera a una persona.",
  "v13.settings.urgent.off": "Apagar",
  "v13.settings.urgent.keep": "Mantenerlo",
  "v13.settings.help": "Privacidad y ayuda",
  "v13.settings.privacy": "Política de privacidad",
  "v13.settings.support": "Soporte",
  "v13.settings.support.hint": "Abre tu correo para escribir a Auphere",
  "v13.settings.session": "Sesión",
  "v13.settings.signOut.title": "¿Cerrar sesión?",
  "v13.settings.signOut.body.agent": "{agent} sigue atendiendo. Dejas de recibir avisos en este teléfono. Tus otros teléfonos siguen como están.",
  "v13.settings.signOut.body.agents": "Tus agentes siguen atendiendo. Dejas de recibir avisos en este teléfono. Tus otros teléfonos siguen como están.",
  "v13.settings.signOut.body": "Dejas de recibir avisos en este teléfono. Tus otros teléfonos siguen como están.",
  "v13.settings.version": "Auphere Customers {version}",
} as const;
