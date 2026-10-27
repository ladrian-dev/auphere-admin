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

  // Spec 047, historia 2: un solo borrador por agente, una sola barra de
  // guardado y el aviso de conflicto con los dos cambios.
  "agents.draft.prompt.title": { es: "Instrucciones", en: "Instructions" },
  "agents.draft.prompt.help": {
    es: "Lo que el agente sigue en cada conversación. Se guarda en el borrador del agente. Publicarlo es otro paso.",
    en: "What the agent follows in every conversation. It is saved to the agent's draft. Publishing is a separate step.",
  },
  "agents.draft.prompt.empty": {
    es: "Escribe las instrucciones antes de guardar.",
    en: "Write the instructions before saving.",
  },
  "agents.draft.context.draft": { es: "Borrador v{n} de {agent}, desde v{base}", en: "Draft v{n} of {agent}, from v{base}" },
  "agents.draft.context.draftFirst": { es: "Borrador v{n} de {agent}", en: "Draft v{n} of {agent}" },
  "agents.draft.context.active": {
    es: "Editas a partir de v{n} de {agent}. El borrador nace al guardar.",
    en: "You are editing from v{n} of {agent}. The draft is created when you save.",
  },
  "agents.draft.context.none": {
    es: "{agent} todavía no tiene versiones. La primera nace al guardar.",
    en: "{agent} has no versions yet. The first one is created when you save.",
  },
  "agents.draft.readonly": {
    es: "Puedes leer el borrador, pero tu rol no puede cambiarlo.",
    en: "You can read the draft, but your role cannot change it.",
  },

  "agents.draft.bar.region": { es: "Cambios sin guardar", en: "Unsaved changes" },
  "agents.draft.bar.pending": { es: "Cambios sin guardar en {sections}", en: "Unsaved changes in {sections}" },
  "agents.draft.bar.and": { es: "y", en: "and" },
  "agents.draft.bar.note": { es: "Nota del cambio (opcional)", en: "Change note (optional)" },
  "agents.draft.bar.notePlaceholder": { es: "Qué cambia y por qué", en: "What changes and why" },
  "agents.draft.bar.discard": { es: "Deshacer cambios", en: "Undo changes" },
  "agents.draft.bar.save": { es: "Guardar", en: "Save" },
  "agents.draft.bar.saved": {
    es: "Guardado en el borrador v{n}. Publícalo cuando esté listo.",
    en: "Saved to draft v{n}. Publish it when it is ready.",
  },
  "agents.draft.bar.failed": {
    es: "No se pudo guardar. Tus cambios siguen aquí: vuelve a intentarlo.",
    en: "It could not be saved. Your changes are still here: try again.",
  },
  "agents.draft.bar.fix": { es: "Revisa los campos marcados.", en: "Check the highlighted fields." },
  "agents.draft.section.prompt": { es: "Instrucciones", en: "Instructions" },
  "agents.draft.section.settings": { es: "Ajustes", en: "Settings" },

  "agents.draft.conflict.title": { es: "Hay cambios más nuevos de {who}", en: "There are newer changes by {who}" },
  "agents.draft.conflict.titlePublished": {
    es: "{who} publicó el borrador mientras editabas",
    en: "{who} published the draft while you were editing",
  },
  "agents.draft.conflict.titleDiscarded": {
    es: "{who} descartó el borrador mientras editabas",
    en: "{who} discarded the draft while you were editing",
  },
  "agents.draft.conflict.titleSomeone": {
    es: "Alguien guardó cambios mientras editabas",
    en: "Someone saved changes while you were editing",
  },
  "agents.draft.conflict.body": {
    es: "No se ha guardado nada tuyo ni se ha perdido nada suyo. Elige qué hacer.",
    en: "Nothing of yours was saved and nothing of theirs was lost. Choose what to do.",
  },
  "agents.draft.conflict.theirs": { es: "Sus cambios", en: "Their changes" },
  "agents.draft.conflict.mine": { es: "Tus cambios, sin guardar", en: "Your changes, not saved" },
  "agents.draft.conflict.nothing": { es: "Sin cambios de campos", en: "No field changes" },
  "agents.draft.conflict.both": {
    es: "Los dos habéis cambiado {fields}. Si guardas los tuyos, ahí quedan los tuyos.",
    en: "You both changed {fields}. If you save yours, yours stay there.",
  },
  "agents.draft.conflict.comparePrompt": {
    es: "Ver las dos versiones de las instrucciones",
    en: "See both versions of the instructions",
  },
  "agents.draft.conflict.theirPrompt": { es: "La suya", en: "Theirs" },
  "agents.draft.conflict.myPrompt": { es: "La tuya", en: "Yours" },
  "agents.draft.conflict.keepMine": { es: "Guardar los míos encima", en: "Save mine on top" },
  "agents.draft.conflict.keepTheirs": { es: "Quedarme con los suyos", en: "Keep theirs" },
  "agents.draft.conflict.keptTheirs": {
    es: "Tienes delante el borrador de {who}. Lo tuyo no se guardó.",
    en: "You now see {who}'s draft. Yours was not saved.",
  },

  "agents.draft.field.system_prompt": { es: "Instrucciones", en: "Instructions" },
  "agents.draft.field.tools": { es: "Herramientas", en: "Tools" },
  "agents.draft.field.skills": { es: "Habilidades", en: "Skills" },
  "agents.draft.field.identity": { es: "Identidad", en: "Identity" },
  "agents.draft.field.tone": { es: "Tono", en: "Tone" },
  "agents.draft.field.objective": { es: "Objetivo", en: "Goal" },
  "agents.draft.field.schedule": { es: "Horario", en: "Hours" },
  "agents.draft.field.languages": { es: "Idiomas", en: "Languages" },
  "agents.draft.field.escalation": { es: "Escalado", en: "Escalation" },
  "agents.draft.field.ai_disclosure": { es: "Aviso de IA", en: "AI disclosure" },
  "agents.draft.field.audience": { es: "A quién responde", en: "Who it answers" },
  "agents.draft.field.payment_review": { es: "Revisión de pagos", en: "Payment review" },
  "agents.draft.field.other": { es: "Otros ajustes", en: "Other settings" },

  "agents.history.title": { es: "Versiones de {agent}", en: "Versions of {agent}" },
  "agents.history.description": {
    es: "Cada versión dice quién la escribió, cuándo, con qué nota y de cuál partió.",
    en: "Each version says who wrote it, when, with which note and which one it started from.",
  },
  "agents.history.list": { es: "Versiones", en: "Versions" },
  "agents.history.empty": { es: "Todavía no hay versiones", en: "There are no versions yet" },
  "agents.history.empty.body": {
    es: "Escribe las instrucciones y guarda: así nace la primera.",
    en: "Write the instructions and save: that is how the first one is created.",
  },
  "agents.history.error": {
    es: "No pudimos leer las versiones. El borrador y los ajustes siguen funcionando.",
    en: "We couldn't read the versions. The draft and the settings still work.",
  },
  "agents.history.retry": { es: "Volver a intentarlo", en: "Try again" },
  "agents.history.number": { es: "v{n}", en: "v{n}" },
  "agents.history.status.staged": { es: "Borrador", en: "Draft" },
  "agents.history.status.active": { es: "Activa", en: "Active" },
  "agents.history.status.archived": { es: "Anterior", en: "Earlier" },
  "agents.history.status.discarded": { es: "Descartada", en: "Discarded" },
  "agents.history.written": { es: "{who} · {when}", en: "{who} · {when}" },
  "agents.history.from": { es: "desde v{n}", en: "from v{n}" },
  "agents.history.publishedBy": { es: "Publicada por {who} · {when}", en: "Published by {who} · {when}" },
  "agents.history.noNote": { es: "Sin nota", en: "No note" },
  "agents.history.saveFirst": {
    es: "Guarda los cambios antes de publicar: el borrador aún no los tiene.",
    en: "Save your changes before publishing: the draft does not have them yet.",
  },
  "agents.history.discard": { es: "Descartar borrador", en: "Discard draft" },
  "agents.history.discard.title": { es: "Descartar el borrador v{n}", en: "Discard draft v{n}" },
  "agents.history.discard.body": {
    es: "{agent} sigue con la versión activa, que no cambia. El borrador queda en el historial como descartado.",
    en: "{agent} keeps its active version, which does not change. The draft stays in the history as discarded.",
  },
  "agents.history.discard.confirm": { es: "Descartar", en: "Discard" },
  "agents.history.discarded": { es: "Borrador descartado.", en: "Draft discarded." },
} as const;
