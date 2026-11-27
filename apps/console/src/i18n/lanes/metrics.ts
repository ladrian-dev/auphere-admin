/** ES/EN del carril `metrics` — la pantalla Métricas de la consola de partners
 *  (antes Consumo) y su sección «Conversaciones» de un cliente (spec 083, enmienda
 *  del 2026-11-27). Cifras y rótulos cortos; las definiciones van juntas en
 *  «Cómo se cuenta» (13.4). Sin punto y coma (`words.test.ts`). */
export const metricsMessages = {
  "nav.metrics": { es: "Métricas", en: "Metrics" },
  "metrics.title": { es: "Métricas", en: "Metrics" },
  "metrics.description": {
    es: "Conversaciones, saldo y gasto de tus clientes, por periodo.",
    en: "Conversations, balance and spend of your clients, by period.",
  },
  "metrics.filters": { es: "Cliente y periodo", en: "Client and period" },

  "metrics.conv.title": { es: "Conversaciones", en: "Conversations" },
  "metrics.conv.period": { es: "Últimos {n} días · hora de {zone}", en: "Last {n} days · {zone} time" },
  "metrics.conv.choose": { es: "Elige un cliente para ver sus conversaciones", en: "Pick a client to see their conversations" },
  "metrics.loading": { es: "Cargando las conversaciones", en: "Loading the conversations" },
  "metrics.error": { es: "No se pudieron cargar las conversaciones", en: "We could not load the conversations" },
  "metrics.retry": { es: "Reintentar", en: "Try again" },
  "metrics.empty": { es: "Sin conversaciones en estos días", en: "No conversations in these days" },
  "metrics.compare.error": {
    es: "No se pudo leer el periodo anterior: las cifras van sin comparar.",
    en: "We could not read the previous period: the figures are not compared.",
  },

  "metrics.print": { es: "Imprimir", en: "Print" },
  "metrics.print.title": { es: "Conversaciones del agente", en: "Agent conversations" },
  "metrics.print.range": { es: "Del {from} al {to}", en: "From {from} to {to}" },
  "metrics.print.zone": { es: "hora de {zone}", en: "{zone} time" },
  "metrics.print.generated": { es: "Generado el {date}", en: "Generated on {date}" },

  "metrics.figures": { es: "Cifras del periodo", en: "Figures for the period" },
  "metrics.fig.conversations": { es: "Conversaciones", en: "Conversations" },
  "metrics.fig.withoutPerson": { es: "Resueltas sin persona", en: "Resolved without a person" },
  "metrics.fig.within": { es: "Respondidas en {s} s o menos", en: "Answered in {s} s or less" },
  "metrics.fig.median": { es: "Primera respuesta, mediana", en: "First response, median" },
  "metrics.fig.incidents": { es: "Incidencias", en: "Incidents" },
  "metrics.fig.cost": { es: "Coste por conversación", en: "Cost per conversation" },
  "metrics.fig.withPerson": { es: "{n} con persona", en: "{n} with a person" },
  "metrics.fig.unanswered": { es: "{n} sin respuesta del agente", en: "{n} without a reply from the agent" },
  "metrics.fig.p90": { es: "9 de cada 10 en {time} o menos", en: "9 in 10 in {time} or less" },
  "metrics.fig.open": { es: "{n} abiertas", en: "{n} open" },
  "metrics.target": { es: "Objetivo {n} %", en: "Target {n}%" },
  "metrics.target.met": { es: "Alcanza el objetivo", en: "Meets the target" },
  "metrics.target.missed": { es: "Por debajo del objetivo", en: "Below the target" },

  "metrics.delta.vs": { es: "{delta} frente a los {n} días anteriores", en: "{delta} vs the previous {n} days" },
  "metrics.delta.same": { es: "Igual", en: "Same" },
  "metrics.delta.sameAs": { es: "Igual que los {n} días anteriores", en: "Same as the previous {n} days" },
  "metrics.unit.pct": { es: "{n} %", en: "{n}%" },
  "metrics.unit.point": { es: "{n} punto", en: "{n} point" },
  "metrics.unit.points": { es: "{n} puntos", en: "{n} points" },
  "metrics.unit.seconds": { es: "{n} s", en: "{n} s" },
  "metrics.percent": { es: "{n} %", en: "{n}%" },
  "metrics.seconds": { es: "{n} s", en: "{n} s" },
  "metrics.minutes": { es: "{n} min", en: "{n} min" },
  "metrics.minutesSeconds": { es: "{m} min {s} s", en: "{m} min {s} s" },

  "metrics.chart.day": { es: "Por día", en: "By day" },
  "metrics.chart.hour": { es: "Por hora del día", en: "By hour of the day" },
  "metrics.chart.weekday": { es: "Por día de la semana", en: "By day of the week" },
  "metrics.chart.col.day": { es: "Día", en: "Day" },
  "metrics.chart.col.hour": { es: "Hora", en: "Hour" },
  "metrics.series.withoutPerson": { es: "Sin persona", en: "Without a person" },
  "metrics.series.withPerson": { es: "Con persona", en: "With a person" },
  "metrics.chart.of": { es: "{n} conversaciones", en: "{n} conversations" },
  "metrics.chart.empty": { es: "Sin conversaciones", en: "No conversations" },

  "metrics.inc.title": { es: "Incidencias por motivo", en: "Incidents by reason" },
  "metrics.inc.col.cause": { es: "Motivo", en: "Reason" },
  "metrics.inc.col.total": { es: "Incidencias", en: "Incidents" },
  "metrics.inc.col.share": { es: "Parte", en: "Share" },
  "metrics.inc.col.delta": { es: "Frente al anterior", en: "Vs previous" },
  "metrics.inc.col.resolved": { es: "Resueltas", en: "Resolved" },
  "metrics.inc.none": { es: "Ninguna incidencia en estos días", en: "No incidents in these days" },
  "metrics.cause.booking_brake": { es: "Freno de reservas", en: "Booking brake" },

  "metrics.agenda.title": { es: "Agenda", en: "Agenda" },
  "metrics.agenda.col.op": { es: "Reservas", en: "Bookings" },
  "metrics.agenda.col.agent": { es: "Agente", en: "Agent" },
  "metrics.agenda.col.person": { es: "Persona", en: "Person" },
  "metrics.agenda.col.customer": { es: "Contacto", en: "Contact" },
  "metrics.agenda.col.total": { es: "Total", en: "Total" },
  "metrics.agenda.created": { es: "Creadas", en: "Created" },
  "metrics.agenda.moved": { es: "Movidas", en: "Moved" },
  "metrics.agenda.cancelled": { es: "Canceladas", en: "Cancelled" },
  "metrics.agenda.released": { es: "Liberadas sin confirmar", en: "Released unconfirmed" },

  "metrics.rem.title": { es: "Recordatorios", en: "Reminders" },
  "metrics.rem.col.kind": { es: "Aviso", en: "Notice" },
  "metrics.rem.col.sent": { es: "Enviados", en: "Sent" },
  "metrics.rem.col.failed": { es: "Fallidos", en: "Failed" },
  "metrics.rem.col.skipped": { es: "Omitidos", en: "Skipped" },
  "metrics.rem.reminder": { es: "Recordatorio de la cita", en: "Appointment reminder" },
  "metrics.rem.ask_confirmation": { es: "Petición de confirmación", en: "Confirmation request" },

  "metrics.brake.title": { es: "Freno de reservas", en: "Booking brake" },
  "metrics.brake.stopped": { es: "Respuestas paradas", en: "Replies stopped" },
  "metrics.brake.corrected": { es: "Corregidas por el agente", en: "Fixed by the agent" },
  "metrics.brake.handed": { es: "Pasadas a una persona", en: "Handed to a person" },

  "metrics.how.title": { es: "Cómo se cuenta", en: "How it is counted" },
  "metrics.how.conversations": {
    es: "Conversación: un ciclo, desde que el contacto escribe hasta que se resuelve, a mano o por inactividad. Cuenta en el día y la hora de su primer mensaje, en la zona del cliente.",
    en: "Conversation: a cycle, from when the contact writes until it is resolved, by hand or for inactivity. It counts on the day and hour of its first message, in the client’s time zone.",
  },
  "metrics.how.withoutPerson": {
    es: "Sin persona: en ese ciclo no se pasó a nadie, nadie la tomó y el freno de reservas no paró ninguna respuesta.",
    en: "Without a person: in that cycle it was not handed to anyone, nobody took it and the booking brake stopped no reply.",
  },
  "metrics.how.autoclose": {
    es: "Este cliente no cierra solas las conversaciones inactivas: una que nadie resuelve cuenta una sola vez.",
    en: "This client does not close idle conversations on their own: one nobody resolves counts once.",
  },
  "metrics.how.firstResponse": {
    es: "Primera respuesta: del primer mensaje del contacto a que el canal acepta la del agente, con los 3 s de espera. Las conversaciones sin respuesta del agente no entran.",
    en: "First response: from the contact’s first message until the channel accepts the agent’s, including the 3 s wait. Conversations without a reply from the agent are left out.",
  },
  "metrics.how.incidents": {
    es: "Incidencia: el agente pidió una persona, una regla no le dejó contestar o el freno paró una respuesta. Resuelta: se resolvió esa conversación.",
    en: "Incident: the agent asked for a person, a rule did not let it reply or the brake stopped a reply. Resolved: that conversation was resolved.",
  },
  "metrics.how.agenda": {
    es: "Agenda: lo hecho en el periodo, por quién. Liberadas: reservas sin confirmar que se soltaron solas. Las importadas no cuentan.",
    en: "Agenda: what was done in the period, by whom. Released: unconfirmed bookings let go on their own. Imported ones do not count.",
  },
  "metrics.how.reminders": {
    es: "Recordatorios: enviado es que el canal lo aceptó. Omitido, que no tocaba enviarlo.",
    en: "Reminders: sent means the channel accepted it. Skipped, that it was not due.",
  },
  "metrics.how.brake": {
    es: "Freno: para una respuesta que da por hecha una cita que no está en la agenda. No detecta una cita confirmada a mano fuera de la agenda.",
    en: "Brake: stops a reply that treats as booked an appointment not in the agenda. It does not detect one confirmed by hand outside the agenda.",
  },
  "metrics.how.compare": {
    es: "La diferencia compara con los mismos días justo antes.",
    en: "The difference compares with the same number of days just before.",
  },
} as const;
