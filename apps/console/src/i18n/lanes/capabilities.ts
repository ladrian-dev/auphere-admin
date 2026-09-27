/** ES/EN messages of lane `capabilities` — la pantalla de Capacidades
 *  (spec 017, R4–R5). Se esparce en `i18n/messages.ts`. */
export const capabilitiesMessages = {
  "cap.title": { es: "Capacidades", en: "Capabilities" },
  "cap.description": {
    es: "Lo que el agente sabe hacer. Lo que dejes apagado, el agente no lo ve. Cada cambio se guarda en el borrador; publicar sigue siendo un paso aparte.",
    en: "What the agent can do. Whatever you leave off, the agent does not see. Each change is saved to the draft; publishing is still a separate step.",
  },
  "cap.search": { es: "Buscar una capacidad…", en: "Search a capability…" },
  "cap.search.label": { es: "Buscar una capacidad", en: "Search a capability" },
  "cap.count": { es: "{on} de {total} encendidas", en: "{on} of {total} on" },
  "cap.enableVisible": { es: "Encender las visibles", en: "Turn on the visible ones" },
  "cap.disableVisible": { es: "Apagar las visibles", en: "Turn off the visible ones" },
  "cap.readonly": { es: "Tu rol permite ver las capacidades, no cambiarlas.", en: "Your role lets you see capabilities, not change them." },

  // ── sector ────────────────────────────────────────────────────────
  "cap.sector.hidden": {
    es: "{n} capacidades son de otros sectores y no se muestran.",
    en: "{n} capabilities belong to other sectors and are not shown.",
  },
  "cap.sector.hiddenOne": {
    es: "1 capacidad es de otro sector y no se muestra.",
    en: "1 capability belongs to another sector and is not shown.",
  },
  "cap.sector.seeAll": { es: "Ver todas", en: "See all" },
  "cap.sector.seeOwn": { es: "Ver solo las de este sector", en: "See only this sector's" },
  "cap.sector.viewingAll": { es: "Viendo todas las capacidades, también las de otros sectores.", en: "Showing every capability, including other sectors'." },
  "cap.sector.none": {
    es: "Este cliente no tiene sector, así que se ven todas las capacidades.",
    en: "This client has no sector, so every capability is shown.",
  },

  // ── grupos ────────────────────────────────────────────────────────
  "cap.fn.appointments": { es: "Citas", en: "Appointments" },
  "cap.fn.orders": { es: "Pedidos", en: "Orders" },
  "cap.fn.messages": { es: "Mensajes", en: "Messages" },
  "cap.fn.escalation": { es: "Escalado", en: "Escalation" },
  "cap.fn.knowledge": { es: "Conocimiento", en: "Knowledge" },
  "cap.fn.other": { es: "Otras", en: "Other" },

  // ── tarjeta ───────────────────────────────────────────────────────
  "cap.badge.recommended": { es: "Recomendada para tu sector", en: "Recommended for your sector" },
  "cap.badge.inActive": { es: "En la versión activa", en: "In the live version" },
  "cap.badge.notPublished": { es: "Aún no publicada", en: "Not published yet" },
  "cap.badge.readOnly": { es: "Solo lectura", en: "Read only" },
  "cap.badge.destructive": { es: "Destructiva", en: "Destructive" },
  "cap.badge.otherSector": { es: "De otro sector", en: "Another sector's" },
  "cap.state.on": { es: "Encendida", en: "On" },
  "cap.state.off": { es: "Apagada", en: "Off" },
  "cap.needs": { es: "Necesita {name} para funcionar.", en: "Needs {name} to work." },
  "cap.needs.connect": { es: "Conectarlo", en: "Connect it" },
  "cap.needs.help": {
    es: "Puedes encenderla igual: empieza a funcionar en cuanto conectes {name}. Hasta entonces el agente no la usa.",
    en: "You can switch it on anyway: it starts working as soon as you connect {name}. Until then the agent does not use it.",
  },
  "cap.mode.label": { es: "Cuándo la usa", en: "When it uses it" },
  "cap.mode.always": { es: "Siempre", en: "Always" },
  "cap.mode.blocked": { es: "Nunca", en: "Never" },
  "cap.mode.default": { es: "Por defecto ({mode})", en: "Default ({mode})" },
  "cap.mode.overridden": { es: "Lo has fijado tú; si no, seguiría el valor por defecto.", en: "You set this; otherwise it would follow the default." },
  "cap.technical": { es: "Detalle técnico", en: "Technical detail" },
  "cap.technical.name": { es: "Nombre", en: "Name" },
  "cap.technical.kind": { es: "Tipo", en: "Kind" },
  "cap.technical.kind.tool": { es: "Herramienta", en: "Tool" },
  "cap.technical.kind.skill": { es: "Habilidad", en: "Skill" },
  "cap.technical.version": { es: "Versión", en: "Version" },
  "cap.technical.tags": { es: "Etiquetas", en: "Tags" },

  // ── integraciones que estorban (R4.1) ─────────────────────────────
  "cap.int.title": { es: "Falta una integración para poder usar todo esto", en: "One integration is missing to use all of this" },
  "cap.int.titleMany": { es: "Faltan {n} integraciones para poder usar todo esto", en: "{n} integrations are missing to use all of this" },
  "cap.int.unlocks": { es: "desbloquea {n} de las que ves", en: "unlocks {n} of the ones you see" },
  "cap.int.connect": { es: "Conectar", en: "Connect" },
  "cap.int.reconnect": { es: "Reconectar", en: "Reconnect" },
  "cap.int.elsewhere": {
    es: "Pausar, desconectar o sincronizar se hace en Integraciones.",
    en: "Pausing, disconnecting or syncing is done in Integrations.",
  },

  // ── la pantalla de Integraciones (R4) ─────────────────────────────
  //
  // Prefijo `int.` y no `cap.int.`: eso último es el bloque que avisa dentro
  // de Capacidades, y son dos sitios distintos con dos trabajos distintos.
  "int.title": { es: "Integraciones", en: "Integrations" },
  "int.description": {
    es: "Lo que conecta al agente con lo que el negocio ya usa. Mientras una integración no esté conectada, las capacidades que dependen de ella se pueden encender, pero el agente no las usa.",
    en: "What connects the agent to what the business already uses. While an integration is not connected, the capabilities that depend on it can be switched on, but the agent does not use them.",
  },
  "int.count": { es: "{on} de {total} conectadas", en: "{on} of {total} connected" },
  "int.unlocks": { es: "Desbloquea {n} capacidades", en: "Unlocks {n} capabilities" },
  "int.unlocksOne": { es: "Desbloquea 1 capacidad", en: "Unlocks 1 capability" },
  "int.readonly": {
    es: "Tu rol permite ver las integraciones, no conectarlas.",
    en: "Your role lets you see integrations, not connect them.",
  },
  "int.empty.title": {
    es: "Auphere todavía no ha publicado integraciones para este entorno",
    en: "Auphere has not published integrations for this environment yet",
  },
  "int.empty.body": {
    es: "En cuanto las publiquemos aparecerán aquí, con lo que desbloquea cada una.",
    en: "They will show up here as soon as we publish them, each with what it unlocks.",
  },

  // ── vacíos ────────────────────────────────────────────────────────
  "cap.empty.title": { es: "Auphere todavía no ha publicado capacidades para este entorno", en: "Auphere has not published capabilities for this environment yet" },
  "cap.empty.body": {
    es: "En cuanto las publiquemos aparecerán aquí. Las integraciones sí se pueden conectar mientras tanto.",
    en: "They will show up here as soon as we publish them. Integrations can be connected in the meantime.",
  },
  "cap.noResults.title": { es: "Ninguna capacidad coincide con «{q}»", en: "No capability matches “{q}”" },
  "cap.noResults.body": { es: "Prueba con otra palabra, o mira también las de otros sectores.", en: "Try another word, or look at other sectors' too." },
  "cap.saved": { es: "Guardado en el borrador.", en: "Saved to the draft." },
} as const;
