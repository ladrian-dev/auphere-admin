/** ES/EN del carril `business-proto` — Negocio como el prototipo aprobado
 *  («Consola de partners v2», `specs/047-…/evidence/prototipo/clientes.md` §6):
 *  cada sección en lectura con su «Editar», las dos marcas («Leído de la web ·
 *  revísalo» con «Es correcto», y «Falta»), el índice con sus círculos y las
 *  secciones «Documentos y webs» y «Redes sociales». Sin nombrar al
 *  constructor y sin punto y coma (`words.test.ts`). */
export const businessProtoMessages = {
  "business.section.edit.label": { es: "Editar {section}", en: "Edit {section}" },
  "business.section.mark.web": { es: "Leído de la web · revísalo", en: "Read from the web · review it" },
  // Spec 073 (4.1, 4.5, 4.6): Negocio que se lee.
  "business.section.toReview": { es: "{n} por revisar", en: "{n} to review" },
  "business.section.readIn": { es: "Leído en {language}", en: "Read in {language}" },
  "business.search.label": { es: "Buscar en Negocio", en: "Search Business" },
  "business.search.placeholder": { es: "Buscar un servicio o una pregunta", en: "Search a service or a question" },
  "business.search.services.one": { es: "1 servicio", en: "1 service" },
  "business.search.services.other": { es: "{n} servicios", en: "{n} services" },
  "business.search.faqs.one": { es: "1 pregunta", en: "1 question" },
  "business.search.faqs.other": { es: "{n} preguntas", en: "{n} questions" },
  "business.search.and": { es: "y", en: "and" },
  "business.search.results": { es: "Resultados de la búsqueda", en: "Search results" },
  "business.review.label": { es: "Revisión de lo leído", en: "Review of what was read" },
  "business.review.progress": { es: "{reviewed} de {total} datos revisados", en: "{reviewed} of {total} facts reviewed" },
  "business.review.markAll": { es: "Marcar todo como correcto", en: "Mark everything as correct" },
  "business.review.markAll.body.one": {
    es: "Lo leído en 1 sección pasa a ser tuyo y deja de salir como «Leído de la web».",
    en: "What was read in 1 section becomes yours and stops showing as “Read from the web”.",
  },
  "business.review.markAll.body.other": {
    es: "Lo leído en {n} secciones pasa a ser tuyo y deja de salir como «Leído de la web».",
    en: "What was read in {n} sections becomes yours and stops showing as “Read from the web”.",
  },
  "business.review.markAll.confirm": { es: "Marcar como correcto", en: "Mark as correct" },
  "business.review.done": { es: "Revisado: ya es tuyo.", en: "Reviewed: it is yours now." },
  "business.section.mark.missing": { es: "Falta", en: "Missing" },
  "business.section.confirm": { es: "Es correcto", en: "It’s right" },
  "business.section.confirmed": {
    es: "Confirmado. Ya no aparece como pendiente de revisar.",
    en: "Confirmed. It no longer shows as waiting for review.",
  },
  // D6 de `clientes.md`: el prototipo dice que se vuelven a pasar las pruebas al
  // guardar la ficha. La API solo las marca (68.9), así que se dice lo que sí pasa.
  "business.page.note": {
    es: "Lo heredan todos sus agentes. Los cambios se aplican desde el siguiente mensaje.",
    en: "All its agents inherit it. Changes apply from the next message.",
  },
  "business.basics.read.no_info": { es: "Sin información", en: "No information" },
  "business.basics.read.no_web": { es: "Sin web", en: "No website" },
  "business.hours.read.range": { es: "{from} a {to}", en: "{from} to {to}" },
  "business.hours.read.next_day": { es: "(día siguiente)", en: "(next day)" },
  "business.hours.read.says": { es: "Así lo dirá el agente: «{phrase}»", en: "This is how the agent will say it: “{phrase}”" },
  "business.locations.empty.read": {
    es: "Sin sedes. Si atiende solo online, déjalo vacío.",
    en: "No locations. If it only works online, leave it empty.",
  },
  "business.docs.title": { es: "Documentos y webs", en: "Documents and websites" },
  "business.socials.section": { es: "Redes sociales", en: "Social media" },
  "business.socials.error.handle": { es: "Solo letras, números, puntos y guiones bajos.", en: "Only letters, numbers, dots and underscores." },
} as const;
