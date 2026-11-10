/** ES/EN del carril `clients-proto` — la lista de clientes y el Panel del
 *  cliente tal como los pinta el prototipo aprobado «Consola de partners v2»
 *  (spec 047, `evidence/prototipo/clientes.md` §2 y §4, huecos H4 y H6).
 *
 *  Solo las frases nuevas: las que ya existían siguen en `business.ts`
 *  (`clients.v2.*`, `panel.*`). Reglas de las palabras: «Saldo», nunca
 *  «Bolsa», en estas dos pantallas (D1). «Al día» para el cliente sin nada que
 *  arreglar (D2). Sin punto y coma (`words.test.ts`): donde el prototipo lo
 *  lleva, dos frases. */
export const clientsProtoMessages = {
  // ── Lista de clientes (§2) ──
  "clients.proto.agents.one": { es: "1 agente", en: "1 agent" },
  "clients.proto.agents.other": { es: "{n} agentes", en: "{n} agents" },
  "clients.proto.agents.testing": { es: "{n} en prueba", en: "{n} testing" },
  "clients.proto.agents.paused.one": { es: "1 pausado", en: "1 paused" },
  "clients.proto.agents.paused.other": { es: "{n} pausados", en: "{n} paused" },
  "clients.proto.agents.draft.one": { es: "1 borrador", en: "1 draft" },
  "clients.proto.agents.draft.other": { es: "{n} borradores", en: "{n} drafts" },
  "clients.proto.footer": {
    es: "Cada cliente tiene su moneda. El saldo se compara por porcentaje disponible.",
    en: "Each client has its own currency. Balances are compared by the percentage left.",
  },

  // ── Panel del cliente (§4) ──
  "panel.proto.left": { es: "Quedan", en: "Left" },
  "panel.proto.spent": { es: "Consumido {spent} de {assigned}", en: "{spent} used of {assigned}" },
  "panel.proto.available": { es: "{pct} % disponible · saldo compartido por sus agentes", en: "{pct}% available · balance shared by its agents" },
  "panel.proto.shared": { es: "Saldo compartido por sus agentes", en: "Balance shared by its agents" },
  "panel.proto.legend.available": { es: "Disponible", en: "Available" },
  "panel.proto.legend.availablePct": { es: "Disponible: {pct} %", en: "Available: {pct}%" },
  "panel.proto.unassigned.lead": { es: "Sin saldo asignado.", en: "No balance assigned." },
  "panel.proto.unassigned.body": {
    es: "Sus agentes pueden crearse y probarse, pero no responderán a clientes reales.",
    en: "Its agents can be created and tested, but they will not answer real customers.",
  },
  "panel.proto.warn.lead": { es: "Queda menos del 20 % del saldo.", en: "Less than 20% of the balance is left." },
  "panel.proto.warn.body": {
    es: "Al llegar a cero, las conversaciones pasan a la Bandeja en lugar de quedarse sin respuesta.",
    en: "At zero, conversations go to the Inbox instead of going unanswered.",
  },
  "panel.proto.viewAll": { es: "Ver todos", en: "View all" },
  "panel.proto.conversations.one": { es: "1 conversación", en: "1 conversation" },
  "panel.proto.conversations.other": { es: "{n} conversaciones", en: "{n} conversations" },
  "panel.proto.perConversation": { es: "{amount} por conversación", en: "{amount} per conversation" },
  "panel.proto.cap": { es: "tope {amount} ({pct} %)", en: "cap {amount} ({pct}%)" },
} as const;
