/** ES/EN del carril `notices` — lo que dice la campana de los avisos de la
 *  spec 047 (`contracts/events.md` §3, requisito 49.6). Cada aviso lleva su
 *  enlace (`href`) a donde se arregla: el texto dice qué pasó, no adónde ir.
 *
 *  `{client}` es el nombre del cliente (o su referencia). Los avisos que traen
 *  el nombre del agente (`agent`) usan la variante `.agent`. Nunca importes:
 *  el aviso no los formatea (los ve Consumo). Sin punto y coma. «Conector»,
 *  nunca «integración». */
export const noticesMessages = {
  "notif.by.someone": { es: "Alguien del negocio", en: "Someone at the business" },

  // ── la bolsa de cada cliente (45) ──
  "notif.kind.client.wallet.low": { es: "{client}: queda poco saldo en su bolsa.", en: "{client}: its bag is running low." },
  "notif.kind.client.wallet.not_enough": {
    es: "{client}: el saldo de su bolsa no llega a fin de mes.",
    en: "{client}: its bag will not last until the end of the month.",
  },
  "notif.kind.client.wallet.empty": {
    es: "{client}: su bolsa se quedó sin saldo. Sus agentes no responden.",
    en: "{client}: its bag is empty. Its agents are not answering.",
  },
  "notif.kind.client.wallet.refill_short": {
    es: "{client}: el relleno de este mes no se completó, no había saldo suficiente en tu cuenta.",
    en: "{client}: this month’s refill was not completed, your account did not have enough balance.",
  },

  // ── el tope de cada agente (44) ──
  "notif.kind.agent.cap.warning": {
    es: "{client}: un agente va por el 80 % de su tope del mes.",
    en: "{client}: an agent has used 80% of its monthly cap.",
  },
  "notif.kind.agent.cap.reached": {
    es: "{client}: un agente llegó a su tope del mes y está en pausa.",
    en: "{client}: an agent reached its monthly cap and is paused.",
  },

  // ── pausas y canales (27, 29, 31) ──
  "notif.kind.agent.paused": { es: "{client}: pausaron un agente.", en: "{client}: an agent was paused." },
  "notif.kind.agent.paused.agent": { es: "{by} pausó {agent} ({client}).", en: "{by} paused {agent} ({client})." },
  "notif.kind.agent.resumed": { es: "{client}: un agente vuelve a atender.", en: "{client}: an agent is answering again." },
  "notif.kind.agent.resumed.agent": { es: "{by} reanudó {agent} ({client}).", en: "{by} resumed {agent} ({client})." },
  "notif.kind.channel.paused": { es: "{client}: pausaron un número.", en: "{client}: a number was paused." },
  "notif.kind.channel.resumed": { es: "{client}: un número vuelve a atender.", en: "{client}: a number is answering again." },
  "notif.kind.channel.problem": {
    es: "{client}: un número tiene un problema y no atiende.",
    en: "{client}: a number has a problem and is not answering.",
  },
  "notif.kind.channel.connected": { es: "{client}: conectaron un número nuevo.", en: "{client}: a new number was connected." },

  // ── conectores (36) ──
  "notif.kind.integration.reauth_required": {
    es: "{client}: un conector necesita que vuelvan a dar permiso.",
    en: "{client}: a connector needs permission again.",
  },

  // ── pruebas, sugerencias y correcciones (13.7, 51, 52) ──
  "notif.kind.agent.tests.failing": {
    es: "{client}: tras un cambio en Negocio fallan pruebas de un agente.",
    en: "{client}: after a change in Business, an agent’s tests are failing.",
  },
  "notif.kind.agent.suggestions.ready": {
    es: "{client}: hay sugerencias nuevas para un agente.",
    en: "{client}: there are new suggestions for an agent.",
  },
  "notif.kind.agent.correction.proposed": {
    es: "{client}: corrigieron una respuesta de un agente. Revisa la mejora.",
    en: "{client}: someone corrected an agent’s reply. Review the improvement.",
  },

  // ── la partida «Construcción y pruebas» (46.5) ──
  "notif.kind.build.budget.warning": {
    es: "Construcción y pruebas va por el 80 % de su tope del mes.",
    en: "Building and testing has used 80% of its monthly cap.",
  },
  "notif.kind.build.budget.exhausted": {
    es: "Construcción y pruebas llegó a su tope del mes. El constructor se detiene, la edición a mano sigue.",
    en: "Building and testing reached its monthly cap. The builder stops, editing by hand still works.",
  },

  // ── los modelos (41.7, 41.8) ──
  "notif.kind.model.retirement": {
    es: "El modelo {deployment} se retira en {days_left} días. Revisa los agentes que lo usan.",
    en: "The model {deployment} retires in {days_left} days. Check the agents that use it.",
  },
  "notif.kind.model.price_change": {
    es: "El precio del modelo {deployment} sube un {increase_pct} % desde el {valid_from}.",
    en: "The price of the model {deployment} goes up {increase_pct}% from {valid_from}.",
  },
} as const;
