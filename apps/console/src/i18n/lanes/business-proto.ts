/** ES/EN del carril `business-proto` — Negocio como el prototipo aprobado
 *  («Consola de partners v2», `specs/047-…/evidence/prototipo/clientes.md` §6):
 *  cada sección en lectura con su «Editar», las dos marcas («Leído de la web ·
 *  revísalo» con «Es correcto», y «Falta»), el índice con sus círculos y las
 *  secciones «Documentos y webs» y «Redes sociales». Sin nombrar al
 *  constructor y sin punto y coma (`words.test.ts`). */
export const businessProtoMessages = {
  "business.section.edit.label": { es: "Editar {section}", en: "Edit {section}" },
  "business.section.mark.web": { es: "Leído de la web · revísalo", en: "Read from the web · review it" },
  "business.section.mark.missing": { es: "Falta", en: "Missing" },
  "business.section.confirm": { es: "Es correcto", en: "It’s right" },
  "business.section.confirmed": {
    es: "Confirmado. Ya no aparece como pendiente de revisar.",
    en: "Confirmed. It no longer shows as waiting for review.",
  },
  // D6 de `clientes.md`: el prototipo dice que se vuelven a pasar las pruebas al
  // guardar la ficha. La API no lo hace, así que se dice lo que sí pasa.
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
