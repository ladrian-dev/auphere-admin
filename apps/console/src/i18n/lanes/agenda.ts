/** ES/EN del carril `agenda` — la agenda desde el agente (spec 057): «Gestiona citas»
 *  en «Nuevo agente», la fila «Agenda (Reservas)» de Conectores con su confirmación,
 *  «La agenda aún no está lista» con un texto por cada motivo de
 *  `passing.NOT_READY_REASONS`, «Gestionar citas» del aviso de lo que falta, la
 *  propuesta de texto y el aviso «agenda preparada» de la ficha y de la lista. Los
 *  modos de Reservas («Servicios», «Aforo» y el tipo de negocio) son los de Acceso
 *  (`clientAccess.reservas.*`, en `reservas-fields.tsx`): un solo nombre para lo mismo.
 *  Ni «capacidad», ni el constructor, ni punto y coma (`words.test.ts`). */
export const agendaMessages = {
  // ── «Gestiona citas» en «Nuevo agente» (requisito 1) ──────────────────────
  "agenda.switch": { es: "Gestiona citas", en: "Handles appointments" },
  "agenda.switch.hint": {
    es: "Da, mueve y cancela citas en la agenda de Reservas.",
    en: "Books, moves and cancels appointments in the Bookings calendar.",
  },
  "agenda.switch.why.description": { es: "Encendido porque la descripción habla de citas.", en: "On because the description talks about appointments." },
  "agenda.switch.why.template": { es: "Encendido porque la plantilla da citas.", en: "On because the template books appointments." },
  "agenda.template.on": { es: "Esta plantilla da citas, así que «Gestiona citas» está encendido.", en: "This template books appointments, so “Handles appointments” is on." },
  "agenda.template.turnsOn": {
    es: "Crear el agente encenderá Reservas para este cliente: elige arriba cómo reserva el negocio.",
    en: "Creating the agent will switch Bookings on for this client: choose above how the business takes bookings.",
  },
  "agenda.turnOn.notice": {
    es: "Generarlo encenderá Reservas para este cliente. Elige cómo reserva el negocio.",
    en: "Generating it will switch Bookings on for this client. Choose how the business takes bookings.",
  },
  "agenda.turnOn.notice.named": {
    es: "Generarlo encenderá Reservas para {client}. Elige cómo reserva el negocio.",
    en: "Generating it will switch Bookings on for {client}. Choose how the business takes bookings.",
  },

  // ── La fila «Agenda (Reservas)» de Conectores (requisito 2) ───────────────
  "agenda.row.name": { es: "Agenda (Reservas)", en: "Agenda (Bookings)" },
  "agenda.row.on": { es: "Activa", en: "On" },
  "agenda.row.off": { es: "Sin activar en este agente", en: "Not on for this agent" },
  "agenda.row.moduleOff": { es: "Reservas está apagado para este cliente.", en: "Bookings is off for this client." },
  "agenda.row.prepared": { es: "Activa en el borrador. Rige al publicar.", en: "On in the draft. It applies when you publish." },
  "agenda.row.leaving": {
    es: "Quitada del borrador. Deja de reservar al publicar. Las citas ya dadas siguen en Reservas.",
    en: "Removed from the draft. It stops booking when you publish. Appointments already booked stay in Bookings.",
  },
  "agenda.row.tools": { es: "{n} de 9 herramientas encendidas", en: "{n} of 9 tools on" },
  "agenda.row.activate": { es: "Activar", en: "Turn on" },
  "agenda.row.activate.named": { es: "Activar la agenda en este agente", en: "Turn on the agenda for this agent" },
  "agenda.row.deactivate": { es: "Desactivar", en: "Turn off" },
  "agenda.row.deactivate.named": { es: "Desactivar la agenda en este agente", en: "Turn off the agenda for this agent" },
  "agenda.row.more": { es: "Más acciones de la agenda", en: "More agenda actions" },
  "agenda.row.whatItDoes": { es: "Qué puede hacer", en: "What it can do" },
  "agenda.row.loading": { es: "Cargando la agenda…", en: "Loading the agenda…" },
  "agenda.row.error": {
    es: "No se pudo leer la agenda de este agente. Lo que ya hace sigue funcionando.",
    en: "Could not read this agent’s agenda. Whatever it already does keeps working.",
  },
  "agenda.row.retry": { es: "Reintentar", en: "Retry" },
  "agenda.row.saved.on": {
    es: "Agenda activada en el borrador. Rige al publicar.",
    en: "Agenda turned on in the draft. It applies when you publish.",
  },
  "agenda.row.saved.off": {
    es: "Agenda quitada del borrador. Las citas ya dadas siguen en Reservas. Rige al publicar.",
    en: "Agenda removed from the draft. Appointments already booked stay in Bookings. It applies when you publish.",
  },

  // ── Encender Reservas desde la fila (requisito 2.3) ────────────────────────
  "agenda.confirm.title": { es: "¿Encender Reservas para este cliente?", en: "Switch Bookings on for this client?" },
  "agenda.confirm.title.named": { es: "¿Encender Reservas para {client}?", en: "Switch Bookings on for {client}?" },
  "agenda.confirm.body": {
    es: "Reservas se enciende para todo el cliente, no solo para este agente. Los demás agentes que dan citas tendrán la agenda preparada en su borrador.",
    en: "Bookings is switched on for the whole client, not just this agent. Its other agents that book appointments will get the agenda ready in their draft.",
  },
  "agenda.confirm.action": { es: "Encender y activar", en: "Switch on and activate" },

  // ── La propuesta de texto (requisito 3) ───────────────────────────────────
  "agenda.proposal.running": { es: "Preparando cómo cambia su texto de citas…", en: "Working out how its appointment text changes…" },
  "agenda.proposal.open": { es: "Hay una propuesta para su texto de citas.", en: "There is a proposal for its appointment text." },
  "agenda.proposal.see": { es: "Ver la propuesta", en: "See the proposal" },
  "agenda.proposal.ask": {
    es: "Si su texto de citas aún dice que el equipo confirma o que la agenda no está activa, pide una propuesta para reescribirlo.",
    en: "If its appointment text still says the team confirms or that the agenda is off, ask for a proposal to rewrite it.",
  },
  "agenda.proposal.failed": {
    es: "No se pudo proponer cómo cambia su texto de citas. Las herramientas sí cambiaron.",
    en: "Could not propose how its appointment text changes. The tools did change.",
  },
  "agenda.proposal.build_budget_exhausted": {
    es: "No queda partida para proponer su texto de citas. Las herramientas sí cambiaron, así que revisa a mano lo que dice de citas antes de publicar.",
    en: "There is no build allowance left to propose its appointment text. The tools did change, so check what it says about appointments by hand before publishing.",
  },
  "agenda.proposal.not_structured": {
    es: "Este agente sigue instrucciones libres, así que no hay propuesta. Revisa a mano lo que dicen de citas.",
    en: "This agent follows free instructions, so there is no proposal. Check what they say about appointments by hand.",
  },

  // ── «La agenda aún no está lista» (requisito 4.4) ──────────────────────────
  "agenda.notReady.title": { es: "La agenda aún no está lista", en: "The agenda is not ready yet" },
  "agenda.notReady.body": {
    es: "Mientras falte algo, el agente pide el servicio, el día y la hora y pasa la conversación a una persona.",
    en: "While something is missing, the agent asks for the service, the day and the time and hands the conversation to a person.",
  },
  "agenda.notReady.reason.reservas_off": { es: "Reservas está apagado para este cliente.", en: "Bookings is off for this client." },
  "agenda.notReady.reason.hours_missing": { es: "Falta el horario del negocio.", en: "The business hours are missing." },
  "agenda.notReady.reason.no_staff": { es: "Nadie del equipo está dado de alta en Reservas.", en: "Nobody on the team is set up in Bookings." },
  "agenda.notReady.reason.no_services": { es: "No hay servicios que se puedan reservar.", en: "There are no services that can be booked." },
  "agenda.notReady.reason.no_bookable_service": {
    es: "Ningún servicio se puede reservar todavía. Revisa su duración y quién lo hace.",
    en: "No service can be booked yet. Check its length and who does it.",
  },
  "agenda.notReady.reason.no_capacity": { es: "Faltan las plazas o las franjas de aforo.", en: "The places or the time slots are missing." },
  "agenda.notReady.reason.other": { es: "Falta algo por completar en Reservas.", en: "Something is still missing in Bookings." },
  "agenda.notReady.inClient": {
    es: "Lo completa el cliente en Reservas, en Ajustes.",
    en: "The client completes it in Bookings, under Settings.",
  },
  "agenda.notReady.toAccess": { es: "Ir a Acceso", en: "Go to Access" },

  // ── «Gestionar citas» y la revisión (requisitos 6.3 y 3.8) ─────────────────
  "agenda.manage": { es: "Gestionar citas", en: "Manage appointments" },
  "agenda.manage.label": { es: "Gestionar citas: {label}", en: "Manage appointments: {label}" },
  "agenda.review.propose": { es: "Pedir la propuesta", en: "Ask for the proposal" },
  "agenda.review.where": { es: "En {block}", en: "In {block}" },

  // ── La propuesta, por bloque (requisito 3.3) ───────────────────────────────
  "agenda.diff.before": { es: "Antes", en: "Before" },
  "agenda.diff.after": { es: "Después", en: "After" },
  "agenda.diff.none": { es: "Nada", en: "Nothing" },
  "agenda.diff.removed": { es: "Se quita", en: "Removed" },
  "agenda.diff.all": { es: "Ver todo", en: "See all" },
  "agenda.diff.edit": { es: "Editar", en: "Edit" },
  "agenda.diff.edit.label": { es: "Aplicar y editar «{block}»", en: "Apply and edit “{block}”" },
  "agenda.ficha.note": {
    es: "La ficha del negocio dice que el equipo confirma las citas, en «{section}». La ficha es de todos los agentes del cliente, así que se cambia en Negocio.",
    en: "The business profile says the team confirms appointments, in “{section}”. The profile belongs to all the client’s agents, so it is changed in Business.",
  },
  "agenda.ficha.go": { es: "Ir a Negocio", en: "Go to Business" },
  "agenda.ficha.section.policies": { es: "Políticas", en: "Policies" },
  "agenda.ficha.section.faqs": { es: "Preguntas frecuentes", en: "FAQs" },

  // ── «Tiene la agenda preparada» (requisito 5.3) ────────────────────────────
  "agenda.prepared.title": { es: "Tiene la agenda preparada: publica para que reserve", en: "Its agenda is ready: publish it so it books" },
  "agenda.prepared.body": {
    es: "El borrador ya lleva la agenda de Reservas. La versión publicada todavía no reserva.",
    en: "The draft already has the Bookings agenda. The published version does not book yet.",
  },
  "agenda.prepared.review": { es: "Revisar la propuesta", en: "Review the proposal" },
  "agenda.prepared.publish": { es: "Revisar y publicar", en: "Review and publish" },
  "agenda.prepared.badge": { es: "Agenda preparada", en: "Agenda ready" },
  "agenda.prepared.card": { es: "Publica para que reserve.", en: "Publish it so it books." },
  "agenda.prepared.card.label": { es: "Revisar y publicar {name}", en: "Review and publish {name}" },

  // ── Los errores de la API (`contracts/console-api.md` §2 y §4) ─────────────
  "agenda.error.reservas_mode_required": {
    es: "Elige cómo reserva el negocio, Servicios o Aforo.",
    en: "Choose how the business takes bookings, Services or Capacity.",
  },
  "agenda.error.reservas_kind_required": { es: "Con Aforo, elige el tipo de negocio.", en: "With Capacity, choose the kind of business." },
  "agenda.error.reservas_kind_forbidden": { es: "El tipo de negocio solo va con Aforo.", en: "The kind of business only goes with Capacity." },
  "agenda.error.archived": {
    es: "El cliente está archivado, así que no se le puede encender Reservas.",
    en: "The client is archived, so Bookings cannot be switched on for it.",
  },
  "agenda.error.no_partner": { es: "Este cliente no está en tu cuenta.", en: "This client is not in your account." },
  "agenda.error.too_many_tools": {
    es: "Con la agenda, este agente pasaría de {max} herramientas, que es el máximo. Apaga alguna antes de activarla.",
    en: "With the agenda, this agent would go over {max} tools, the maximum. Switch some off before turning it on.",
  },
  "agenda.error.spec_invalid": {
    es: "El borrador no quedaría bien con este cambio. No se ha cambiado nada.",
    en: "The draft would not be valid with this change. Nothing has changed.",
  },
  "agenda.error.generic": { es: "No se pudo cambiar la agenda. No se ha cambiado nada.", en: "Could not change the agenda. Nothing has changed." },
} as const;
