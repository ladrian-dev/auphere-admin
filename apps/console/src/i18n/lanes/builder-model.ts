/** ES/EN del carril `builder-model` — Agente › Avanzado › Modelo (spec 065,
 *  requisitos 1.5, 2.4, 2.7, 4.8 y 9.2). Precios, nunca costes internos, y sin
 *  nombrar la unidad interna (`money-words.test.ts`). Sin punto y coma
 *  (`words.test.ts`). Sin decir de dónde sale el modelo (elección del partner,
 *  de Auphere, de la versión o por defecto) ni ofrecer volver al de Auphere
 *  (2.7): el que responde lleva «Ahora». */
export const builderModelMessages = {
  "agentModel.title": { es: "Modelo", en: "Model" },
  "agentModel.intro": {
    es: "Cada modelo cuesta distinto y se paga de la bolsa del cliente. El precio es una estimación por cada 1.000 respuestas, hecha con lo que gastó este agente la última semana.",
    en: "Each model costs differently and is paid from the client’s bag. The price is an estimate per 1,000 responses, based on what this agent spent last week.",
  },
  "agentModel.introNominal": {
    es: "Cada modelo cuesta distinto y se paga de la bolsa del cliente. El precio es una estimación por cada 1.000 respuestas, hecha con una conversación típica, porque este agente aún no tiene consumo.",
    en: "Each model costs differently and is paid from the client’s bag. The price is an estimate per 1,000 responses, based on a typical conversation, because this agent has no usage yet.",
  },
  "agentModel.now": { es: "Ahora", en: "Now" },
  "agentModel.provider.openai": { es: "OpenAI", en: "OpenAI" },
  "agentModel.provider.anthropic": { es: "Anthropic", en: "Anthropic" },
  // La línea de cada gama (1.5).
  "agentModel.line.max": { es: "Para agentes con muchas herramientas o casos difíciles", en: "For agents with many tools or hard cases" },
  "agentModel.line.balanced": { es: "Para la mayoría de agentes de atención y reservas", en: "For most customer service and booking agents" },
  "agentModel.line.economy": { es: "Para preguntas frecuentes y respuestas cortas", en: "For frequent questions and short answers" },
  // `amount` ya va formateado en el idioma de la persona.
  "agentModel.price": { es: "≈ {amount} {currency} por 1.000 respuestas", en: "≈ {amount} {currency} per 1,000 responses" },

  "agentModel.save": { es: "Guardar modelo", en: "Save model" },
  "agentModel.hint": { es: "Vale desde el próximo mensaje. No hace falta publicar.", en: "Applies from the next message. No need to publish." },
  "agentModel.saved": { es: "{agent} responde con {model} desde el próximo mensaje.", en: "{agent} answers with {model} from the next message." },
  "agentModel.readonly": { es: "Solo quien edita agentes puede cambiarlo.", en: "Only people who edit agents can change it." },

  // ── Los estados ────────────────────────────────────────────────────────
  "agentModel.error.title": { es: "No se pudo leer el modelo de este agente", en: "Couldn’t read this agent’s model" },
  "agentModel.error.body": {
    es: "Vuelve a intentarlo en un momento. El agente sigue respondiendo como hasta ahora.",
    en: "Try again in a moment. The agent keeps answering as before.",
  },
  "agentModel.retry": { es: "Reintentar", en: "Retry" },
  "agentModel.partial": {
    es: "Ahora no se puede calcular lo que cuesta cada modelo. Puedes cambiarlo igual.",
    en: "The price of each model can’t be worked out right now. You can change it anyway.",
  },
  "agentModel.empty.now": { es: "Responde con {model} · {price}", en: "Answers with {model} · {price}" },
  "agentModel.empty.nowNoPrice": { es: "Responde con {model}", en: "Answers with {model}" },
  "agentModel.empty.body": {
    es: "Tu cuenta no tiene otros modelos para elegir. Si necesitas otro, escríbenos.",
    en: "Your account has no other models to choose from. If you need another one, write to us.",
  },

  // ── Fuera de la oferta (2.7) y el aviso (4.8) ─────────────────────────
  "agentModel.outside.retired": {
    es: "Este agente responde con {model} ({price}), que ya no se ofrece. Sigue con él hasta que elijas otro. Después no podrás volver a él.",
    en: "This agent answers with {model} ({price}), which is no longer offered. It stays on it until you choose another one. After that you can’t go back to it.",
  },
  "agentModel.outside.retiredNoPrice": {
    es: "Este agente responde con {model}, que ya no se ofrece. Sigue con él hasta que elijas otro. Después no podrás volver a él.",
    en: "This agent answers with {model}, which is no longer offered. It stays on it until you choose another one. After that you can’t go back to it.",
  },
  "agentModel.outside.operator": {
    es: "Auphere eligió {model} para este agente ({price}). No está entre los modelos de tu cuenta: puedes cambiarlo por uno de estos, pero después no podrás volver a él.",
    en: "Auphere chose {model} for this agent ({price}). It isn’t among your account’s models: you can switch to one of these, but after that you can’t go back to it.",
  },
  "agentModel.outside.operatorNoPrice": {
    es: "Auphere eligió {model} para este agente. No está entre los modelos de tu cuenta: puedes cambiarlo por uno de estos, pero después no podrás volver a él.",
    en: "Auphere chose {model} for this agent. It isn’t among your account’s models: you can switch to one of these, but after that you can’t go back to it.",
  },
  "agentModel.notice.title": { es: "{model} no puede usar las Skills de este agente", en: "{model} can’t use this agent’s Skills" },
  "agentModel.notice.body": {
    es: "Mientras las tenga, responde con {fallback}. Elige uno de estos o quita las Skills.",
    en: "While it has them, it answers with {fallback}. Choose one of these or remove the Skills.",
  },

  // ── Quién respondió, en el chat de prueba y en las pruebas (T062; 5.3 y 6.1) ──
  // La API dice el modelo y si fue la reserva, no por qué ni cuál falló: no se nombra.
  "agentModel.answered": { es: "Respondió {model}", en: "Answered by {model}" },
  "agentModel.answeredReserve": {
    es: "Respondió {model}, el modelo de reserva, porque el del agente no contestó.",
    en: "Answered by {model}, the backup model, because the agent’s model didn’t reply.",
  },

  "agentModel.error.unavailable": {
    es: "No se pudo cambiar el modelo: ya no está disponible en tu cuenta. Recarga la página y elige otro.",
    en: "Couldn’t change the model: it’s no longer available in your account. Reload the page and choose another one.",
  },
} as const;
