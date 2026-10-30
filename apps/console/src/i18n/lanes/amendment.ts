/** ES/EN de la enmienda del 2026-10-29 de la spec 047 (fase 27: T209, T210 y T215).
 *
 *  El sector en «Datos básicos», «Políticas» y «Preguntas frecuentes» con lo
 *  sugerido («Sugerido · confirma»), la tarjeta de lectura por red, los agentes
 *  sugeridos en la pestaña Agentes y «Por qué falló» turno a turno. Lo sugerido
 *  nunca nombra al constructor (Andrés, 2026-10-28): dice de dónde sale. */
export const amendmentMessages = {
  // ── El sector (T209, requisito 57.5) ─────────────────────────────────────
  "business.sector.label": { es: "Sector", en: "Sector" },
  "business.sector.identifying": { es: "Identificando el sector…", en: "Identifying the sector…" },
  "business.sector.guide": { es: "Con guía", en: "With a guide" },
  "business.sector.generated": { es: "Generada", en: "Generated" },
  "business.sector.guide.hint": {
    es: "Sus agentes y sus pruebas siguen la guía de Auphere para este sector.",
    en: "Its agents and tests follow Auphere’s guide for this sector.",
  },
  "business.sector.generated.hint": {
    es: "Auphere no tiene guía para este sector: se generó una solo para este cliente.",
    en: "Auphere has no guide for this sector, so one was generated for this client only.",
  },
  "business.sector.proposal": { es: "Propuesto: {label}", en: "Suggested: {label}" },
  "business.sector.proposal.hint": {
    es: "Sale de volver a leer su información. No cambia hasta que lo aceptes.",
    en: "It comes from reading its information again. Nothing changes until you accept it.",
  },
  "business.sector.accept.label": { es: "Aceptar el sector {label}", en: "Accept the sector {label}" },
  "business.sector.discard.label": { es: "Descartar el sector {label}", en: "Discard the sector {label}" },
  "business.sector.accepted": { es: "Sector cambiado.", en: "Sector changed." },
  "business.sector.choose": { es: "Elige un sector", en: "Pick a sector" },
  "business.sector.other": { es: "Otro", en: "Other" },
  "business.sector.other.label": { es: "Cómo se llama el sector", en: "What the sector is called" },
  "business.sector.other.hint": {
    es: "Hasta 40 caracteres. Sin guía de Auphere, se genera una para este cliente.",
    en: "Up to 40 characters. Without an Auphere guide, one is generated for this client.",
  },
  "business.sector.error.other_required": { es: "Escribe cómo se llama el sector.", en: "Type what the sector is called." },
  "business.sector.error.unknown": { es: "Ese sector ya no está en la lista. Elige otro.", en: "That sector is no longer on the list. Pick another." },
  "business.sector.list.error": {
    es: "No pudimos cargar la lista de sectores. Puedes escribir uno en «Otro».",
    en: "We could not load the list of sectors. You can type one under “Other”.",
  },

  // ── Lo sugerido en una sección (T209, requisito 60.5) ─────────────────────
  "business.suggested.badge": { es: "Sugerido · confirma", en: "Suggested · confirm" },
  "business.suggested.from.builder": { es: "Propuesto a partir de la ficha", en: "Suggested from the profile" },
  "business.suggested.from.web": { es: "Leído de la web", en: "Read from the website" },
  "business.suggested.from.document": { es: "Leído de un documento", en: "Read from a document" },
  "business.suggested.from.social": { es: "Leído de sus redes", en: "Read from its social profiles" },
  "business.suggested.from.import": { es: "Importado", en: "Imported" },
  "business.suggested.from.inbox_correction": { es: "De una corrección en la Bandeja", en: "From a correction in the Inbox" },
  "business.suggested.from.other": { es: "Sugerido", en: "Suggested" },
  "business.suggested.current": { es: "Ahora: {value}", en: "Now: {value}" },
  "business.suggested.accept": { es: "Aceptar", en: "Accept" },
  "business.suggested.accept.label": { es: "Aceptar {item}", en: "Accept {item}" },
  "business.suggested.edit": { es: "Editar", en: "Edit" },
  "business.suggested.edit.label": { es: "Editar {item}", en: "Edit {item}" },
  "business.suggested.discard": { es: "Descartar", en: "Discard" },
  "business.suggested.discard.label": { es: "Descartar {item}", en: "Discard {item}" },
  "business.suggested.value": { es: "Texto", en: "Text" },
  "business.suggested.save": { es: "Guardar en la ficha", en: "Save in the profile" },
  "business.suggested.accepted": { es: "Añadido a la ficha.", en: "Added to the profile." },
  "business.suggested.discarded": { es: "Descartado.", en: "Discarded." },
  "business.suggested.error.decided": { es: "Ya lo decidió otra persona.", en: "Someone else already decided it." },
  "business.suggested.error.invalid": { es: "Ese texto no vale aquí. Cámbialo.", en: "That text does not fit here. Change it." },
  "business.suggested.error.required": { es: "Escribe el texto antes de guardarlo.", en: "Type the text before saving it." },
  "business.suggested.unavailable": {
    es: "No pudimos cargar lo sugerido para esta sección.",
    en: "We could not load the suggestions for this section.",
  },
  "business.proposals.everyAgent": { es: "Todos sus agentes lo usan al responder.", en: "All its agents use this when answering." },

  // ── Un canal pedido con `?canal=` que no se pudo leer (T218) ──────────────
  "builder.channel.page.unavailable": {
    es: "No pudimos abrir la configuración de ese número. Ábrela otra vez desde la lista.",
    en: "We could not open that number’s settings. Open them again from the list.",
  },

  // ── Cargando Negocio (T218: la forma de la página, anunciada) ─────────────
  "business.page.loading": { es: "Cargando Negocio", en: "Loading Business" },

  // ── Políticas (T209, requisito 60.4) ──────────────────────────────────────
  "business.policies.title": { es: "Políticas", en: "Policies" },
  "business.policies.cancellation": { es: "Cancelación", en: "Cancellation" },
  "business.policies.payments": { es: "Pagos", en: "Payments" },
  "business.policies.deposit": { es: "Señal", en: "Deposit" },
  "business.policies.no_show": { es: "No presentarse", en: "No-show" },
  "business.policies.none": { es: "Sin escribir", en: "Not written" },
  "business.policies.save": { es: "Guardar políticas", en: "Save policies" },

  // ── Preguntas frecuentes (T209, requisito 60.4) ───────────────────────────
  "business.faqs.title": { es: "Preguntas frecuentes", en: "Frequent questions" },
  "business.faqs.add": { es: "Añadir pregunta", en: "Add a question" },
  "business.faqs.q": { es: "Pregunta", en: "Question" },
  "business.faqs.a": { es: "Respuesta", en: "Answer" },
  "business.faqs.save": { es: "Guardar pregunta", en: "Save question" },
  "business.faqs.empty": { es: "Todavía no hay preguntas frecuentes.", en: "There are no frequent questions yet." },
  "business.faqs.list": { es: "Preguntas confirmadas", en: "Confirmed questions" },
  "business.faqs.suggested": { es: "Por confirmar", en: "To confirm" },
  "business.faqs.remove": { es: "Quitar", en: "Remove" },
  "business.faqs.remove.label": { es: "Quitar {q}", en: "Remove {q}" },
  "business.faqs.removed": { es: "Pregunta quitada.", en: "Question removed." },
  "business.faqs.saved": { es: "Pregunta guardada.", en: "Question saved." },
  "business.faqs.error.required": { es: "Escribe la pregunta y la respuesta.", en: "Type the question and the answer." },

  // ── La tarjeta de lectura, por red (T210, requisitos 59.4 y 59.7) ─────────
  "business.read.title.done": { es: "Lo que leímos", en: "What we read" },
  "business.read.network.read": { es: "También leímos {networks}.", en: "We also read {networks}." },
  "business.read.network.blocked": {
    es: "{network} no deja leer perfiles sin cuenta.",
    en: "{network} does not let anyone read profiles without an account.",
  },
  "business.read.network.failed": { es: "No pudimos leer {network}: {reason}.", en: "We could not read {network}: {reason}." },
  "business.read.toReview.one": { es: "1 dato por revisar en Negocio.", en: "1 detail to review under Business." },
  "business.read.toReview.other": { es: "{n} datos por revisar en Negocio.", en: "{n} details to review under Business." },
  "business.read.structured": {
    es: "Incluye los datos que su web publica para los buscadores, los más fiables.",
    en: "It includes the data its website publishes for search engines, the most reliable.",
  },

  // ── Los agentes sugeridos (T210, requisito 60.6) ──────────────────────────
  "builder.suggested.list": { es: "Agentes sugeridos", en: "Suggested agents" },
  "builder.suggested.badge": { es: "Sugerido", en: "Suggested" },
  "builder.suggested.hint": {
    es: "Sale de su ficha. No existe hasta que lo crees.",
    en: "It comes from its profile. It does not exist until you create it.",
  },
  "builder.suggested.role.reception": { es: "Para recepción", en: "For reception" },
  "builder.suggested.role.sales": { es: "Para ventas", en: "For sales" },
  "builder.suggested.role.billing": { es: "Para cobros", en: "For billing" },
  "builder.suggested.role.support": { es: "Para soporte", en: "For support" },
  "builder.suggested.create": { es: "Crear este agente", en: "Create this agent" },
  // El nombre accesible empieza por lo que se ve (WCAG 2.5.3, «Label in Name»).
  "builder.suggested.create.label": { es: "Crear este agente: {name}", en: "Create this agent: {name}" },
  "builder.suggested.dismiss": { es: "Descartar", en: "Discard" },
  "builder.suggested.dismiss.label": { es: "Descartar la sugerencia {name}", en: "Discard the suggestion {name}" },
  "builder.suggested.dismissed": { es: "Sugerencia descartada.", en: "Suggestion discarded." },
  "builder.suggested.error": { es: "No se pudo descartar. Inténtalo de nuevo.", en: "It could not be discarded. Try again." },

  // ── «Por qué falló», turno a turno (T215, requisitos 58.4 y 61.6) ─────────
  "builder.suite.conversation": { es: "La conversación de la prueba", en: "The test conversation" },
  "builder.suite.conversation.show": { es: "Ver la conversación", en: "See the conversation" },
  "builder.suite.conversation.customer": { es: "Cliente simulado", en: "Simulated customer" },
  "builder.suite.conversation.agent": { es: "Agente", en: "Agent" },
  "builder.suite.stop.plan_done": {
    es: "Terminó porque el cliente simulado cumplió su plan.",
    en: "It ended because the simulated customer completed its plan.",
  },
  "builder.suite.stop.goodbye": { es: "Terminó porque el cliente simulado se despidió.", en: "It ended because the simulated customer said goodbye." },
  "builder.suite.stop.handoff": {
    es: "Terminó porque el agente pasó la conversación a una persona.",
    en: "It ended because the agent handed the conversation to a person.",
  },
  "builder.suite.stop.turn_limit": {
    es: "Llegó a 8 turnos del cliente sin cumplir el plan.",
    en: "It reached 8 customer turns without completing the plan.",
  },
  "builder.suite.generated": { es: "Generada", en: "Generated" },
  "builder.suite.generated.hint": {
    es: "Auphere no tiene guía para este sector: estas pruebas se generaron para este cliente.",
    en: "Auphere has no guide for this sector, so these tests were generated for this client.",
  },
};
