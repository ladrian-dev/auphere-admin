/** ES/EN del carril `builder-knowledge` — la pestaña Conocimiento de un agente
 *  y «Enseñar» con su alcance (spec 047, historia 22; T134, requisitos 37.3 y
 *  12.1). El estado de cada fuente («Pendiente», «Indexado», «Fallido») y sus
 *  motivos son los de `knowledge.*`, los mismos que en Negocio.
 *  Ni «integración» ni punto y coma (`words.test.ts`). */
export const builderKnowledgeMessages = {
  // ── La sección en la pantalla del agente ────────────────────────────────
  "builder.screen.knowledge": { es: "Conocimiento", en: "Knowledge" },
  "builder.knowledge.intro": {
    es: "Lo que sabe solo este agente. Ningún otro agente del cliente lo ve.",
    en: "What only this agent knows. No other agent of the client sees it.",
  },
  "builder.knowledge.business.none": {
    es: "El negocio aún no tiene fuentes para todos sus agentes.",
    en: "The business has no sources for all its agents yet.",
  },
  "builder.knowledge.business.one": {
    es: "Además sabe 1 fuente del negocio, que ven todos sus agentes.",
    en: "It also knows 1 business source, which all its agents see.",
  },
  "builder.knowledge.business.other": {
    es: "Además sabe {n} fuentes del negocio, que ven todos sus agentes.",
    en: "It also knows {n} business sources, which all its agents see.",
  },
  "builder.knowledge.business.link": { es: "Verlas en Negocio", en: "See them in Business" },
  "builder.knowledge.list": { es: "Fuentes de este agente", en: "This agent’s sources" },
  "builder.knowledge.empty.title": { es: "Este agente aún no tiene fuentes propias", en: "This agent has no sources of its own yet" },
  "builder.knowledge.empty.body": {
    es: "Sube un archivo o añade una web solo para él, o enséñale algo con tus palabras.",
    en: "Upload a file or add a website just for it, or teach it something in your own words.",
  },
  "builder.knowledge.empty.readonly": {
    es: "Cuando alguien le dé fuentes propias, aparecerán aquí.",
    en: "When someone gives it sources of its own, they will show up here.",
  },
  "builder.knowledge.error.load": {
    es: "No pudimos cargar el conocimiento de este agente. Inténtalo de nuevo.",
    en: "We could not load this agent’s knowledge. Try again.",
  },
  "builder.knowledge.error.generic": { es: "No se pudo hacer. Inténtalo de nuevo.", en: "It could not be done. Try again." },
  "builder.knowledge.kind.file": { es: "Archivo", en: "File" },
  "builder.knowledge.kind.url": { es: "Web", en: "Website" },
  "builder.knowledge.kind.note": { es: "Enseñado", en: "Taught" },
  "builder.knowledge.read": { es: "Leída el {date}", en: "Read on {date}" },
  "builder.knowledge.notRead": { es: "Sin leer todavía", en: "Not read yet" },
  "builder.knowledge.actions": { es: "Acciones de {title}", en: "Actions for {title}" },
  "builder.knowledge.retry": { es: "Reintentar", en: "Retry" },
  "builder.knowledge.cancel": { es: "Cancelar", en: "Cancel" },
  "builder.knowledge.restorable": { es: "Quitadas hace poco", en: "Recently removed" },

  // ── Añadir una fuente solo para este agente ─────────────────────────────
  "builder.knowledge.add.file": { es: "Subir un archivo", en: "Upload a file" },
  "builder.knowledge.add.url": { es: "Añadir una web", en: "Add a website" },
  "builder.knowledge.file.field": { es: "Archivo (PDF, TXT, MD o HTML, hasta 10 MB)", en: "File (PDF, TXT, MD or HTML, up to 10 MB)" },
  "builder.knowledge.url.field": { es: "Dirección de la web", en: "Website address" },
  "builder.knowledge.title.field": { es: "Título (opcional)", en: "Title (optional)" },
  "builder.knowledge.file.submit": { es: "Subir para este agente", en: "Upload for this agent" },
  "builder.knowledge.url.submit": { es: "Añadir para este agente", en: "Add for this agent" },
  "builder.knowledge.file.required": { es: "Elige un archivo.", en: "Choose a file." },
  "builder.knowledge.file.tooLarge": { es: "El archivo pasa de 10 MB.", en: "The file is over 10 MB." },
  "builder.knowledge.url.invalid": {
    es: "Escribe una dirección que empiece por http:// o https://.",
    en: "Type an address that starts with http:// or https://.",
  },
  "builder.knowledge.added": { es: "«{title}» ya es una fuente de este agente.", en: "“{title}” is now a source of this agent." },
  "builder.knowledge.addedFailed": {
    es: "«{title}» se añadió, pero no se pudo leer. Mira el motivo en la lista.",
    en: "“{title}” was added, but it could not be read. See why in the list.",
  },

  // ── Quitar y deshacer (12.2: 10 minutos) ────────────────────────────────
  "builder.knowledge.remove": { es: "Quitar", en: "Remove" },
  "builder.knowledge.remove.label": { es: "Quitar {title}", en: "Remove {title}" },
  "builder.knowledge.removed": {
    es: "«{title}» ya no se usa desde el siguiente mensaje. Puedes deshacerlo durante 10 minutos.",
    en: "“{title}” is no longer used from the next message. You can undo it for 10 minutes.",
  },
  "builder.knowledge.removed.row": { es: "Quitada · se puede deshacer hasta las {time}", en: "Removed · can be undone until {time}" },
  "builder.knowledge.undo": { es: "Deshacer", en: "Undo" },
  "builder.knowledge.undo.label": { es: "Deshacer quitar {title}", en: "Undo removing {title}" },
  "builder.knowledge.restored": { es: "«{title}» vuelve a usarse.", en: "“{title}” is used again." },
  "builder.knowledge.undo.closed": {
    es: "Han pasado más de 10 minutos: ya no se puede deshacer.",
    en: "More than 10 minutes have passed: it can no longer be undone.",
  },

  // ── «Enseñar» (37.3) ────────────────────────────────────────────────────
  "builder.teach.open": { es: "Enseñar", en: "Teach" },
  "builder.teach.title": { es: "Enseñar algo a {name}", en: "Teach {name} something" },
  "builder.teach.body": {
    es: "Escribe lo que debe saber, con tus palabras. Se aplica al momento y se puede deshacer.",
    en: "Write what it should know, in your own words. It applies at once and can be undone.",
  },
  "builder.teach.text": { es: "Lo que debe saber", en: "What it should know" },
  "builder.teach.text.hint": { es: "Hasta 5.000 caracteres.", en: "Up to 5,000 characters." },
  "builder.teach.scope": { es: "¿Quién debe saberlo?", en: "Who should know it?" },
  "builder.teach.scope.agent": { es: "Solo este agente", en: "Only this agent" },
  "builder.teach.scope.agent.hint": { es: "Ningún otro agente del cliente lo verá.", en: "No other agent of the client will see it." },
  "builder.teach.scope.business": { es: "Todo el negocio (todos los agentes)", en: "The whole business (all agents)" },
  "builder.teach.scope.business.hint": {
    es: "Lo sabrán todos los agentes de este cliente, también los que crees después.",
    en: "Every agent of this client will know it, including the ones you create later.",
  },
  "builder.teach.retest.none": {
    es: "Después se vuelven a pasar las pruebas de los agentes que lo sepan.",
    en: "Afterwards, the tests of the agents that know it run again.",
  },
  "builder.teach.retest.agent": {
    es: "Después se vuelven a pasar las pruebas de este agente.",
    en: "Afterwards, this agent’s tests run again.",
  },
  "builder.teach.retest.business": {
    es: "Después se vuelven a pasar las pruebas de todos los agentes del cliente.",
    en: "Afterwards, the tests of every agent of the client run again.",
  },
  "builder.teach.required.scope": { es: "Elige quién debe saberlo.", en: "Choose who should know it." },
  "builder.teach.required.text": { es: "Escribe lo que debe saber.", en: "Write what it should know." },
  "builder.teach.tooLong": { es: "Como mucho 5.000 caracteres.", en: "At most 5,000 characters." },
  "builder.teach.submit": { es: "Enseñar", en: "Teach" },
  "builder.teach.cancel": { es: "Cancelar", en: "Cancel" },
  "builder.teach.done.agent": { es: "Aprendido. Solo lo sabe {name}.", en: "Learned. Only {name} knows it." },
  "builder.teach.done.business": { es: "Aprendido. Lo saben todos los agentes del negocio.", en: "Learned. Every agent of the business knows it." },
  "builder.teach.business.notice": {
    es: "Todos los agentes saben ya «{title}». Está con las fuentes del negocio.",
    en: "Every agent now knows “{title}”. It is with the business sources.",
  },
  "builder.teach.undo": { es: "Deshacer", en: "Undo" },
  "builder.teach.undone": { es: "Olvidado. Puedes recuperarlo durante 10 minutos.", en: "Forgotten. You can bring it back for 10 minutes." },
  "builder.teach.dismiss": { es: "Cerrar el aviso", en: "Close the notice" },
} as const;
