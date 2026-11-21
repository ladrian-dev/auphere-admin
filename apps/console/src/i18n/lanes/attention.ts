/** ES/EN de la spec 071: «Lo que te necesita».
 *
 *  Las filas del partner (tope de construcción, saldo de la cuenta, cobro
 *  fallido), sus arreglos, la campana con «Ahora» y «Anteriores», y los avisos
 *  de Consumo. Lo de cada cliente sigue en `clients.v2.attention.*`. */
export const attentionMessages = {
  // ── Filas del partner ────────────────────────────────────────────────────
  "att.title.build": { es: "Construcción y pruebas", en: "Building and testing" },
  "att.title.account": { es: "Saldo de tu cuenta", en: "Your account balance" },
  "att.title.billing": { es: "Facturación", en: "Billing" },
  "att.build_cap_exhausted": {
    es: "Llegaste al tope del mes. Crear agentes, las pruebas y el playground están parados hasta el día 1. Las conversaciones siguen atendidas.",
    en: "You reached this month's cap. Creating agents, tests and the playground are stopped until the 1st. Conversations are still answered.",
  },
  "att.build_cap_warning": {
    es: "Vas por más del 80 % del tope del mes. Al 100 % se paran la creación de agentes, las pruebas y el playground.",
    en: "You are past 80 % of this month's cap. At 100 % creating agents, tests and the playground stop.",
  },
  "att.build_cap_warning.figures": {
    es: "{spent} de {cap} ({pct} %). Al 100 % se paran la creación de agentes, las pruebas y el playground.",
    en: "{spent} of {cap} ({pct} %). At 100 % creating agents, tests and the playground stop.",
  },
  "att.account_empty": {
    es: "No te queda saldo para asignar a tus clientes.",
    en: "You have no balance left to assign to your clients.",
  },
  "att.account_low": { es: "Te queda poco saldo para asignar.", en: "You have little balance left to assign." },
  "att.account_low.days": {
    es: "Te queda saldo para unos {days} días a este ritmo.",
    en: "Your balance lasts about {days} days at this rate.",
  },
  "att.account_low.amount": { es: "Te quedan {amount} para asignar.", en: "You have {amount} left to assign." },
  "att.billing_payment_failed": {
    es: "No se pudo cobrar el último pago. Revisa la tarjeta para no perder el servicio.",
    en: "The last payment could not be charged. Check the card so you don't lose service.",
  },
  // ── Arreglos ─────────────────────────────────────────────────────────────
  "panel.v2.fix.request_build_extension": { es: "Pedir ampliación", en: "Request an increase" },
  "panel.v2.fix.buy_balance": { es: "Comprar saldo", en: "Buy balance" },
  "panel.v2.fix.fix_billing": { es: "Revisar la facturación", en: "Check billing" },
  "att.build.requested": {
    es: "Pedimos la ampliación. Te avisamos cuando Auphere la revise.",
    en: "We requested the increase. We'll let you know when Auphere reviews it.",
  },
  "att.build.already": {
    es: "Ya pediste una ampliación hoy. Auphere la está revisando.",
    en: "You already requested an increase today. Auphere is reviewing it.",
  },
  // ── La lista vacía ───────────────────────────────────────────────────────
  "att.none": { es: "Nada te necesita ahora.", en: "Nothing needs you right now." },
  // ── La campana (D1) ──────────────────────────────────────────────────────
  "att.bell.now": { es: "Ahora", en: "Now" },
  "att.bell.before": { es: "Anteriores", en: "Earlier" },
  "att.bell.resolved": { es: "Resuelto", en: "Resolved" },
  "att.bell.nowError": {
    es: "No se pudo saber qué te necesita ahora.",
    en: "Couldn't tell what needs you right now.",
  },
  // ── El Panel ─────────────────────────────────────────────────────────────
  "att.panel.balance.low": { es: "Saldo bajo", en: "Low balance" },
  "att.panel.balance.empty": { es: "Sin saldo para asignar", en: "No balance to assign" },
  "att.panel.build": {
    es: "Construcción y pruebas: {spent} de {cap} ({pct} %)",
    en: "Building and testing: {spent} of {cap} ({pct} %)",
  },
  // ── Consumo ──────────────────────────────────────────────────────────────
  "att.usage.title": { es: "Avisos", en: "Notices" },
  "att.usage.lowBadge": { es: "Saldo bajo", en: "Low balance" },
} as const;
