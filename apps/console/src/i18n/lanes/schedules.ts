/** ES/EN del carril `schedules` — Rutinas (spec 082).
 *
 *  Una rutina es una instrucción que un agente ejecuta a su hora. En pantalla
 *  se dice «rutina» y «ejecución», nunca «schedule» ni «run», y las
 *  herramientas son herramientas: ni «capacidades» ni «integraciones».
 *  Sin punto y coma (`words.test.ts`). */
export const schedulesMessages = {
  "nav.schedules": { es: "Rutinas", en: "Routines" },
  "schedules.title": { es: "Rutinas", en: "Routines" },
  "schedules.description": {
    es: "Una instrucción que un agente ejecuta a su hora. Tú lees la respuesta.",
    en: "An instruction an agent runs at its hour. You read the answer.",
  },

  "schedules.pick.title": { es: "Elige un cliente", en: "Pick a client" },
  "schedules.pick.lead": {
    es: "Una rutina es de un agente, y un agente es de un cliente. Aquí ves las de uno cada vez.",
    en: "A routine belongs to an agent, and an agent to a client. You see one client at a time.",
  },
  "schedules.pick.active": { es: "{count} activas", en: "{count} active" },
  "schedules.pick.none": { es: "Sin rutinas", en: "No routines" },

  "schedules.filter.all": { es: "Todas", en: "All" },
  "schedules.filter.active": { es: "Activas", en: "Active" },
  "schedules.filter.paused": { es: "En pausa", en: "Paused" },
  "schedules.filter.archived": { es: "Archivadas", en: "Archived" },
  "schedules.filter.agent": { es: "Todos los agentes", en: "Every agent" },
  "schedules.filter.none": {
    es: "Ninguna rutina coincide con ese filtro.",
    en: "No routine matches that filter.",
  },

  "schedules.col.routine": { es: "Rutina", en: "Routine" },
  "schedules.col.agent": { es: "Agente", en: "Agent" },
  "schedules.col.when": { es: "Cuándo", en: "When" },
  "schedules.col.next": { es: "Próxima", en: "Next" },
  "schedules.col.runs": { es: "Ejecuciones del mes", en: "Runs this month" },
  "schedules.col.state": { es: "Estado", en: "State" },

  "schedules.state.active": { es: "Activa", en: "Active" },
  "schedules.state.paused": { es: "En pausa", en: "Paused" },
  "schedules.state.archived": { es: "Archivada", en: "Archived" },
  "schedules.reason.manual": { es: "La pausaste tú", en: "You paused it" },
  "schedules.reason.agent_unavailable": {
    es: "Su agente no está atendiendo",
    en: "Its agent is not attending",
  },
  "schedules.reason.no_balance": { es: "El cliente se quedó sin saldo", en: "The client ran out of balance" },
  "schedules.reason.failures": { es: "Falló tres veces seguidas", en: "It failed three times in a row" },

  "schedules.when.daily": { es: "Cada día, {time}", en: "Every day, {time}" },
  "schedules.when.weekly": { es: "{days}, {time}", en: "{days}, {time}" },
  "schedules.when.monthly": { es: "Día {day} de cada mes, {time}", en: "Day {day} every month, {time}" },
  "schedules.when.once": { es: "Una vez, {date}, {time}", en: "Once, {date}, {time}" },
  "schedules.when.never": { es: "Sin próxima", en: "No next run" },

  "schedules.empty.title": {
    es: "{client} todavía no tiene ninguna rutina",
    en: "{client} has no routines yet",
  },
  "schedules.empty.body": {
    es: "Lo que le dirías a su agente por chat, pero puesto a una hora y repetido solo.",
    en: "What you would tell its agent in a chat, but set to an hour and repeated on its own.",
  },

  "schedules.noclients.title": {
    es: "Todavía no tienes clientes",
    en: "You have no clients yet",
  },
  "schedules.noclients.body": {
    es: "Una rutina es de un agente, y un agente es de un cliente. Crea tu primer cliente y su agente, y vuelve.",
    en: "A routine belongs to an agent, and an agent to a client. Create your first client and its agent, then come back.",
  },
  "schedules.noclients.action": { es: "Ir a Clientes", en: "Go to Clients" },
  "schedules.noagents.title": {
    es: "{client} todavía no tiene ningún agente",
    en: "{client} has no agent yet",
  },
  "schedules.noagents.body": {
    es: "No hay a quién vincular la rutina. Crea el agente de este cliente y vuelve.",
    en: "There is nobody to attach the routine to. Create this client's agent and come back.",
  },
  "schedules.noagents.action": { es: "Ver este cliente", en: "Open this client" },

  "schedules.tools.note": {
    es: "Una rutina no añade herramientas: reparte en el tiempo las que el agente ya tiene.",
    en: "A routine adds no tools: it spreads over time the ones the agent already has.",
  },
  "schedules.timezone": { es: "Hora de {zone}, la del negocio", en: "Time in {zone}, the business's" },
} as const;
