/**
 * ES/EN messages of lane `reservas-templates` (spec 043, requisito 15): the six
 * WhatsApp templates of Reservas in Ajustes — what each one is for and how it
 * stands in Meta. Spread into `i18n/messages.ts`. Every key is asked for by
 * `components/reservas/settings/reservas-templates.tsx` (`no-orphan-keys.test.ts`).
 *
 * Words: «Aprobada», «En revisión», «Rechazada», «En pausa», «Sin crear». The
 * business never creates or fixes a template here: the system asks Meta for the
 * missing ones, and whoever manages the agents fixes a rejected one.
 */
export const reservasTemplatesMessages = {
  "reservas.templates.title": { es: "Plantillas de WhatsApp", en: "WhatsApp templates" },
  "reservas.templates.body": {
    es: "Con ellas salen los avisos cuando la persona no te ha escrito en las últimas 24 horas. Las pedimos a Meta por ti y Meta las revisa.",
    en: "They carry the notices when the person hasn't written to you in the last 24 hours. We ask Meta for them on your behalf and Meta reviews them.",
  },
  "reservas.templates.loading": { es: "Cargando plantillas", en: "Loading templates" },
  "reservas.templates.loadError": { es: "No pudimos cargar las plantillas.", en: "We couldn't load the templates." },
  "reservas.templates.noWhatsapp": {
    es: "Este negocio no tiene un número de WhatsApp conectado. Cuando quien gestiona tus agentes lo conecte, pediremos las plantillas a Meta.",
    en: "This business has no WhatsApp number connected. Once whoever manages your agents connects one, we'll ask Meta for the templates.",
  },
  "reservas.templates.allApproved": {
    es: "Las seis están aprobadas. Los avisos salen aunque la persona no te haya escrito.",
    en: "All six are approved. Notices go out even if the person hasn't written to you.",
  },
  "reservas.templates.someApproved": {
    es: "{approved} de {total} aprobadas. Mientras una no lo esté, ese aviso solo sale si la persona te escribió en las últimas 24 horas.",
    en: "{approved} of {total} approved. Until one is, that notice only goes out if the person wrote to you in the last 24 hours.",
  },
  "reservas.templates.list": { es: "Plantillas de Reservas", en: "Bookings templates" },

  "reservas.templates.name.reserva_confirmada": { es: "Reserva confirmada", en: "Booking confirmed" },
  "reservas.templates.name.reserva_pide_confirmacion": { es: "Pedir confirmación", en: "Ask to confirm" },
  "reservas.templates.name.reserva_recordatorio": { es: "Recordatorio", en: "Reminder" },
  "reservas.templates.name.reserva_cambiada": { es: "Reserva cambiada", en: "Booking changed" },
  "reservas.templates.name.reserva_cancelada": { es: "Reserva cancelada", en: "Booking cancelled" },
  "reservas.templates.name.reserva_hueco_libre": { es: "Hueco libre de la lista de espera", en: "Waitlist opening" },
  "reservas.templates.name.other": { es: "Plantilla", en: "Template" },

  "reservas.templates.state.approved": { es: "Aprobada", en: "Approved" },
  "reservas.templates.state.in_review": { es: "En revisión", en: "In review" },
  "reservas.templates.state.rejected": { es: "Rechazada", en: "Rejected" },
  "reservas.templates.state.paused": { es: "En pausa", en: "Paused" },
  "reservas.templates.state.not_created": { es: "Sin crear", en: "Not created" },

  "reservas.templates.inReview": {
    es: "Meta suele revisarla en minutos, a veces tarda hasta 72 horas.",
    en: "Meta usually reviews it within minutes, sometimes up to 72 hours.",
  },
  "reservas.templates.inReviewSince": {
    es: "En revisión desde: {when}. Meta suele revisarla en minutos, a veces tarda hasta 72 horas.",
    en: "In review since: {when}. Meta usually reviews it within minutes, sometimes up to 72 hours.",
  },
  "reservas.templates.rejected.invalid_format": {
    es: "Meta dice que el formato no es válido.",
    en: "Meta says the format isn't valid.",
  },
  "reservas.templates.rejected.incorrect_category": {
    es: "Meta dice que no es de la categoría de utilidad.",
    en: "Meta says it doesn't belong to the utility category.",
  },
  "reservas.templates.rejected.promotional": { es: "Meta la ve como publicidad.", en: "Meta sees it as advertising." },
  "reservas.templates.rejected.abusive_content": {
    es: "Meta dice que el contenido no cumple sus normas.",
    en: "Meta says the content breaks its rules.",
  },
  "reservas.templates.rejected.other": { es: "Meta dio otro motivo.", en: "Meta gave another reason." },
  "reservas.templates.rejected.next": {
    es: "No la volvemos a pedir sola. Quien gestiona tus agentes puede corregirla.",
    en: "We won't ask for it again on our own. Whoever manages your agents can fix it.",
  },
  "reservas.templates.paused": {
    es: "Meta la pausó por quejas o bloqueos de quien la recibe. Quien gestiona tus agentes puede revisarla.",
    en: "Meta paused it after complaints or blocks from people who got it. Whoever manages your agents can look into it.",
  },
  "reservas.templates.why.on_its_way": {
    es: "La pediremos a Meta en unos minutos.",
    en: "We'll ask Meta for it in a few minutes.",
  },
  "reservas.templates.why.no_whatsapp": {
    es: "Falta un número de WhatsApp conectado.",
    en: "A connected WhatsApp number is missing.",
  },
  "reservas.templates.why.deleted": {
    es: "Se borró en Meta. No la volvemos a pedir sola. Quien gestiona tus agentes puede crearla de nuevo.",
    en: "It was deleted in Meta. We won't ask for it again on our own. Whoever manages your agents can create it again.",
  },
} as const;
