/** ES/EN messages of lane `capabilities` — la pantalla de Capacidades
 *  (spec 017, R4–R5). Se esparce en `i18n/messages.ts`. */
export const capabilitiesMessages = {
  "cap.title": { es: "Habilidades", en: "Skills" },
  "cap.description": {
    es: "Lo que el agente sabe hacer. Lo que dejes apagado, el agente no lo ve. Cada cambio se guarda en el borrador; publicar sigue siendo un paso aparte.",
    en: "What the agent can do. Whatever you leave off, the agent does not see. Each change is saved to the draft; publishing is still a separate step.",
  },
  "cap.enableVisible": { es: "Encender las visibles", en: "Turn on the visible ones" },
  "cap.disableVisible": { es: "Apagar las visibles", en: "Turn off the visible ones" },
  "cap.readonly": { es: "Tu rol permite ver las habilidades, no cambiarlas.", en: "Your role lets you see skills, not change them." },

  // ── sector ────────────────────────────────────────────────────────
  "cap.sector.hidden": {
    es: "{n} habilidades son de otros sectores y no se muestran.",
    en: "{n} skills belong to other sectors and are not shown.",
  },
  "cap.sector.hiddenOne": {
    es: "1 habilidad es de otro sector y no se muestra.",
    en: "1 skill belongs to another sector and is not shown.",
  },
  "cap.sector.seeAll": { es: "Ver todas", en: "See all" },
  "cap.sector.seeOwn": { es: "Ver solo las de este sector", en: "See only this sector's" },
  "cap.sector.viewingAll": { es: "Viendo todas las habilidades, también las de otros sectores.", en: "Showing every skill, including other sectors'." },
  "cap.sector.none": {
    es: "Este cliente no tiene sector, así que se ven todas las habilidades.",
    en: "This client has no sector, so every skill is shown.",
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
  // Paridad fila 57. El texto viejo decía «No activable en esta versión
  // (requiere una herramienta o canal que falta)», y eso era falso: no falta
  // nada del cliente, falta que la publiquemos nosotros. Mandaba al partner
  // a buscar en su configuración un problema que no estaba ahí.
  "cap.unavailable.badge": { es: "Aún no disponible", en: "Not available yet" },
  "cap.unavailable": {
    es: "Todavía no la hemos publicado en este entorno. No depende de ti: en cuanto esté, podrás encenderla aquí.",
    en: "We have not published it in this environment yet. It is not on you: as soon as it is there, you can switch it on here.",
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
  "cap.technical.kind.skill": { es: "Skill", en: "Skill" },
  "cap.technical.version": { es: "Versión", en: "Version" },
  "cap.technical.tags": { es: "Etiquetas", en: "Tags" },

  // ── integraciones que estorban (R4.1) ─────────────────────────────
  "cap.int.title": { es: "Falta un conector para poder usar todo esto", en: "One connector is missing to use all of this" },
  "cap.int.titleMany": { es: "Faltan {n} conectores para poder usar todo esto", en: "{n} connectors are missing to use all of this" },
  "cap.int.unlocks": { es: "desbloquea {n} de las que ves", en: "unlocks {n} of the ones you see" },
  "cap.int.connect": { es: "Conectar", en: "Connect" },
  "cap.int.reconnect": { es: "Reconectar", en: "Reconnect" },
  "cap.int.elsewhere": {
    es: "Pausar, desconectar o sincronizar se hace en Conectores.",
    en: "Pausing, disconnecting or syncing is done in Connectors.",
  },

  // ── la pantalla de Integraciones (R4) ─────────────────────────────
  //
  // Prefijo `int.` y no `cap.int.`: eso último es el bloque que avisa dentro
  // de Capacidades, y son dos sitios distintos con dos trabajos distintos.
  "int.title": { es: "Conectores", en: "Connectors" },
  "int.description": {
    es: "Lo que conecta al agente con lo que el negocio ya usa. Mientras un conector no esté conectado, las habilidades que dependen de él se pueden encender, pero el agente no las usa.",
    en: "What connects the agent to what the business already uses. While a connector is not connected, the skills that depend on it can be switched on, but the agent does not use them.",
  },
  // Las categorías con las que se agrupan y se filtran (spec 018, R4.1). Una
  // que no esté aquí cae en «El resto»: enseñar su clave interna sería
  // colar jerga en la pantalla, y juntarlas todas bajo un nombre honesto
  // dice la verdad sin inventarles una categoría (R4.5).
  "int.cat.booking": { es: "Citas", en: "Appointments" },
  "int.cat.calendar": { es: "Calendario", en: "Calendar" },
  "int.cat.billing": { es: "Cobros", en: "Payments" },
  "int.cat.catalog": { es: "Catálogo y ventas", en: "Catalog and sales" },
  "int.cat.ecommerce": { es: "Tienda", en: "Store" },
  "int.cat.messaging": { es: "Mensajería", en: "Messaging" },
  "int.cat.docs": { es: "Documentos", en: "Documents" },
  "int.cat.crm": { es: "Clientes", en: "Customers" },
  "int.unlocks": { es: "Desbloquea {n} habilidades", en: "Unlocks {n} skills" },
  "int.unlocksOne": { es: "Desbloquea 1 habilidad", en: "Unlocks 1 skill" },
  "int.readonly": {
    es: "Tu rol permite ver los conectores, no conectarlos.",
    en: "Your role lets you see connectors, not connect them.",
  },
  "int.empty.title": {
    es: "Auphere todavía no ha publicado conectores para este entorno",
    en: "Auphere has not published connectors for this environment yet",
  },
  "int.empty.body": {
    es: "En cuanto las publiquemos aparecerán aquí, con lo que desbloquea cada una.",
    en: "They will show up here as soon as we publish them, each with what it unlocks.",
  },

  // ── vacíos ────────────────────────────────────────────────────────
  "cap.empty.title": { es: "Auphere todavía no ha publicado habilidades para este entorno", en: "Auphere has not published skills for this environment yet" },
  "cap.empty.body": {
    es: "En cuanto las publiquemos aparecerán aquí. Los conectores sí se pueden conectar mientras tanto.",
    en: "They will show up here as soon as we publish them. Connectors can be connected in the meantime.",
  },
  "cap.saved": { es: "Guardado en el borrador.", en: "Saved to the draft." },
} as const;
