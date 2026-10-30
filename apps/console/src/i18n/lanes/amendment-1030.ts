/** ES/EN de la enmienda del 2026-10-30 de la spec 047, «Solo lo que tenemos» (fase 28: T228).
 *
 *  «No tenemos herramienta para: …» con la alternativa del agente (pasar a una
 *  persona), la ficha que no se pudo leer al preparar el borrador, las pruebas
 *  que no aplican y la puerta sin ninguna, y los códigos nuevos de la API en
 *  palabras. Las `label` de lo que falta llegan de la API en español: aquí solo
 *  va lo que las rodea. Nada nombra al constructor. */
export const amendment1030Messages = {
  // ── «No tenemos herramienta para: …» (65.3, 65.4) ────────────────────────
  "builder.missing.title": { es: "No tenemos herramienta para: {label}", en: "We have no tool for: {label}" },
  "builder.missing.title.list": { es: "No tenemos herramienta para:", en: "We have no tool for:" },
  "builder.missing.fallback": {
    es: "Si se lo piden, el agente pasa la conversación a una persona.",
    en: "If someone asks for it, the agent hands the conversation to a person.",
  },
  "builder.missing.promise": { es: "Lo promete su texto.", en: "Its text promises it." },
  "builder.missing.remove": { es: "Quitar la promesa", en: "Remove the promise" },
  // El nombre accesible empieza por lo que se ve (WCAG 2.5.3, «Label in Name»).
  "builder.missing.remove.label": { es: "Quitar la promesa: {label}", en: "Remove the promise: {label}" },
  "builder.missing.loading": { es: "Comprobando qué herramientas faltan…", en: "Checking which tools are missing…" },
  "builder.missing.error": {
    es: "No pudimos comprobar qué herramientas le faltan a este agente.",
    en: "We could not check which tools this agent is missing.",
  },

  // ── El validador, en palabras (`integration_unknown`, 65.3) ──────────────
  "builder.problem.integration_unknown": {
    es: "{name} no es un conector que tengamos para este cliente. Hay que quitar lo que lo pide para poder guardar.",
    en: "{name} is not a connector we have for this client. Remove what asks for it to be able to save.",
  },
  "builder.problem.integration_unknown.generic": {
    es: "Pide un conector que no tenemos para este cliente. Hay que quitarlo para poder guardar.",
    en: "It asks for a connector we do not have for this client. Remove it to be able to save.",
  },

  // ── Sin la ficha no hay borrador (`facts_unavailable`, 65.12) ────────────
  "builder.facts.title": { es: "No pudimos leer la ficha del negocio", en: "We could not read the business profile" },
  "builder.facts.title.named": { es: "No pudimos leer la ficha de {client}", en: "We could not read the profile of {client}" },
  "builder.facts.body": {
    es: "Sin ella no se puede preparar el borrador. Inténtalo de nuevo en unos minutos. Lo que escribiste sigue aquí.",
    en: "Without it the draft cannot be prepared. Try again in a few minutes. What you typed is still here.",
  },

  // ── Pruebas que aplican (65.8, 65.9) ─────────────────────────────────────
  "builder.suite.noneApplies": {
    es: "Ninguna prueba aplica a este agente. Añade una que le aplique: sin ella no se puede guardar.",
    en: "No test applies to this agent. Add one that does: without it, it cannot be saved.",
  },
  "builder.suite.na.undo.error": { es: "No se pudo volver a activar. Inténtalo de nuevo.", en: "It could not be turned back on. Try again." },
  "builder.publish.noApplicableTests": {
    es: "Este agente no tiene ninguna prueba que le aplique. Añade una antes de guardar.",
    en: "This agent has no test that applies to it. Add one before saving.",
  },

  // ── Los códigos nuevos de la API, en palabras (§11 «Códigos nuevos») ─────
  "common.error.structured_agent": {
    es: "Las herramientas de este agente se cambian desde su pantalla, no desde aquí.",
    en: "This agent’s tools are changed from its own screen, not from here.",
  },
  "common.error.seed_template_retired": {
    es: "Las plantillas ya no se aplican así. Crea el agente en «Nuevo agente», donde también puedes empezar desde una plantilla.",
    en: "Templates are no longer applied this way. Create the agent in “New agent”, where you can also start from a template.",
  },
  "common.error.facts_unavailable": {
    es: "No pudimos leer la ficha del negocio. Inténtalo de nuevo en unos minutos.",
    en: "We could not read the business profile. Try again in a few minutes.",
  },
} as const;
