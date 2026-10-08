/**
 * ES/EN messages of lane `agents` (spec 030, iteration 3): a client with
 * more than one agent — the selector of the record, «Nuevo agente», rename,
 * archive and the agent of each number. Spread into `i18n/messages.ts`;
 * every key is asked for literally by some component (`no-orphan-keys.test.ts`).
 */
export const agentsMessages = {
  "agents.switcher.label": { es: "Agente", en: "Agent" },
  "agents.switcher.unpublished": { es: "{name} · sin publicar", en: "{name} · not published" },

  "agents.new": { es: "Nuevo agente", en: "New agent" },
  "agents.new.description": {
    es: "Con su propio prompt, habilidades y versiones. Nace como borrador: no contesta en ningún número hasta que lo publiques y le asignes uno en Canales.",
    en: "With its own prompt, skills and versions. It starts as a draft: it answers on no number until you publish it and give it one in Channels.",
  },
  "agents.new.loading": { es: "Cargando plantillas", en: "Loading templates" },
  "agents.new.templatesError": {
    es: "No pudimos cargar las plantillas. Cierra y vuelve a intentarlo.",
    en: "We couldn't load the templates. Close this and try again.",
  },
  "agents.new.name": { es: "Nombre", en: "Name" },
  "agents.new.name.hint": {
    es: "Lo verán tu equipo y el cliente, por ejemplo «Ventas» o «Soporte».",
    en: "Your team and the client will see it, for example “Sales” or “Support”.",
  },
  "agents.new.template": { es: "Plantilla", en: "Template" },
  "agents.new.retry": { es: "Reintentar", en: "Try again" },
  "agents.new.noTemplates": {
    es: "No hay plantillas disponibles para crear un agente. Pídele a Auphere que active una.",
    en: "There are no templates to create an agent from. Ask Auphere to enable one.",
  },
  "agents.new.create": { es: "Crear agente", en: "Create agent" },
  "agents.new.created": {
    es: "«{name}» creado. Revisa su borrador y publícalo.",
    en: "“{name}” created. Review its draft and publish it.",
  },

  "agents.rename": { es: "Renombrar", en: "Rename" },
  "agents.rename.title": { es: "Renombrar agente", en: "Rename agent" },
  "agents.rename.description": {
    es: "El nombre nuevo se ve en la consola y en la del cliente. El agente no cambia.",
    en: "The new name shows here and in the client's console. The agent itself does not change.",
  },
  "agents.archive": { es: "Archivar", en: "Archive" },
  "agents.archive.title": { es: "¿Archivar «{name}»?", en: "Archive “{name}”?" },
  "agents.archive.description": {
    es: "Deja de aparecer en la consola. Sus versiones y su historial se conservan. Un agente que contesta en algún número no se puede archivar.",
    en: "It stops showing in the console. Its versions and history are kept. An agent that answers on a number cannot be archived.",
  },
  "agents.archive.done": { es: "«{name}» archivado.", en: "“{name}” archived." },
  "agents.rename.done": { es: "Ahora se llama «{name}».", en: "It is now called “{name}”." },

  "agents.channel.label": { es: "Contesta", en: "Answers" },
  "agents.channel.confirm": { es: "Cambiar agente", en: "Change agent" },
  "agents.channel.confirm.title": {
    es: "¿Que conteste {name} en {number}?",
    en: "Have {name} answer on {number}?",
  },
  "agents.channel.confirm.body": {
    es: "Desde el próximo mensaje contesta {name}. Las conversaciones abiertas conservan su historial.",
    en: "{name} answers from the next message on. Open conversations keep their history.",
  },
  "agents.channel.saved": {
    es: "Desde el próximo mensaje contesta {name}.",
    en: "{name} answers from the next message on.",
  },

  "agents.error.name_taken": { es: "Ya hay un agente con ese nombre.", en: "There is already an agent with that name." },
  "agents.error.agent_has_channels": {
    es: "Este agente contesta en algún número. Dale ese número a otro agente antes de archivarlo.",
    en: "This agent answers on a number. Give that number to another agent before archiving it.",
  },
  "agents.error.last_agent": {
    es: "Es el único agente del cliente: no se puede archivar.",
    en: "It is the client's only agent: it cannot be archived.",
  },
  "agents.error.agent_not_published": {
    es: "Ese agente aún no está publicado. Publícalo antes de darle un número.",
    en: "That agent is not published yet. Publish it before giving it a number.",
  },
  "agents.error.channel_send_only": {
    es: "Ese número solo envía avisos: no lo atiende ningún agente.",
    en: "That number only sends notices: no agent answers on it.",
  },
  "agents.error.agent_archived": { es: "Ese agente está archivado.", en: "That agent is archived." },
} as const;
