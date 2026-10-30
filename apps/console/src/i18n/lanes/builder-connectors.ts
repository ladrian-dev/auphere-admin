/** ES/EN del carril `builder-connectors` — la sección Conectores de un agente y
 *  la página de cada conexión (spec 047, historia 21; T129; requisitos 35 y 36).
 *  En la API se llaman «integrations», en pantalla son Conectores: ni
 *  «integración» ni punto y coma (`words.test.ts`).
 *
 *  Las etiquetas de los ajustes (`agentConn.setting.{slug}.{campo}`) son las de
 *  los esquemas del catálogo de hoy. Uno que no esté aquí se nombra con el
 *  `title` de su esquema o con su clave legible. */
export const builderConnectorsMessages = {
  // ── La sección del agente (35.2) ────────────────────────────────────────
  "agentConn.title": { es: "Conectores", en: "Connectors" },
  "agentConn.intro": {
    es: "Lo que este agente usa para actuar. Se autoriza una vez por cliente y cada agente activa solo lo que necesita.",
    en: "What this agent uses to act. It is authorised once per client and each agent turns on only what it needs.",
  },
  "agentConn.category": { es: "Categoría", en: "Category" },
  "agentConn.list": { es: "Conectores para este agente", en: "Connectors for this agent" },
  "agentConn.empty": {
    es: "Todavía no hay conectores disponibles para este cliente.",
    en: "There are no connectors available for this client yet.",
  },
  "agentConn.noResults": { es: "Ningún conector coincide con la búsqueda.", en: "No connector matches the search." },
  "agentConn.clear": { es: "Quitar los filtros", en: "Clear the filters" },
  "agentConn.loading": { es: "Cargando los conectores…", en: "Loading the connectors…" },
  "agentConn.error": {
    es: "No se pudieron cargar los conectores de este agente. Lo que ya usa sigue funcionando.",
    en: "Could not load this agent's connectors. Whatever it already uses keeps working.",
  },
  "agentConn.retry": { es: "Reintentar", en: "Retry" },
  "agentConn.readonly": { es: "Tu rol puede ver los conectores, no cambiarlos.", en: "Your role can see the connectors, not change them." },
  "agentConn.state.off": { es: "Conectado, sin usar en este agente", en: "Connected, not used by this agent" },
  "agentConn.auth.oauth_composio": { es: "Se autoriza con la cuenta del servicio", en: "Authorised with the service account" },
  "agentConn.auth.api_key": { es: "Se conecta con una clave", en: "Connected with a key" },
  "agentConn.auth.browser_credentials": { es: "Se conecta con usuario y contraseña", en: "Connected with a username and password" },
  "agentConn.auth.webhook_manual": { es: "Se configura con Auphere", en: "Set up with Auphere" },
  "agentConn.auth.public_url": { es: "Se enlaza con su página pública", en: "Linked through its public page" },
  "agentConn.auth.other": { es: "Se autoriza desde el servicio", en: "Authorised from the service" },

  // ── El permiso (35.5) ──────────────────────────────────────────────────
  "agentConn.permission.off": { es: "Sin usar en este agente", en: "Not used by this agent" },
  "agentConn.permission.read": { es: "Solo leer", en: "Read only" },
  "agentConn.permission.ask_before_write": { es: "Preguntar antes de escribir", en: "Ask before writing" },
  "agentConn.permission.read_write": { es: "Leer y escribir", en: "Read and write" },
  "agentConn.permission.hint.read": { es: "Consulta, nunca cambia nada.", en: "Looks things up, never changes anything." },
  "agentConn.permission.hint.ask_before_write": {
    es: "Antes de crear o cambiar algo, pide tu aprobación.",
    en: "Asks for your approval before creating or changing anything.",
  },
  "agentConn.permission.hint.read_write": { es: "Consulta y cambia sin preguntar.", en: "Looks things up and changes them without asking." },
  "agentConn.permission.saved": { es: "{name}: {permission}.", en: "{name}: {permission}." },

  // ── Las acciones de cada fila ──────────────────────────────────────────
  "agentConn.connect": { es: "Conectar", en: "Connect" },
  "agentConn.reconnect": { es: "Reconectar", en: "Reconnect" },
  "agentConn.page": { es: "Ver su página", en: "Open its page" },
  // H10 (63.3): cada botón de la fila lleva el nombre del conector para quien no ve la fila.
  "agentConn.page.named": { es: "Ver su página de {name}", en: "Open the {name} page" },
  "agentConn.connect.named": { es: "Conectar {name}", en: "Connect {name}" },
  "agentConn.reconnect.named": { es: "Reconectar {name}", en: "Reconnect {name}" },
  "agentConn.settings.named": { es: "Ajustes de {name}", en: "{name} settings" },
  "agentConn.remove.short": { es: "Quitar", en: "Remove" },
  "agentConn.remove.named": { es: "Quitar {name}", en: "Remove {name}" },
  "agentConn.connected": { es: "Conectado", en: "Connected" },
  "agentConn.settings.permission": { es: "Permiso en este agente", en: "Permission for this agent" },
  "agentConn.searchLabel": { es: "Buscar conector", en: "Search connector" },
  "agentConn.filter.all": { es: "Todos", en: "All" },
  "agentConn.filter.connected": { es: "Conectados", en: "Connected" },
  "agentConn.noMatch": { es: "Ningún conector coincide con «{q}».", en: "No connector matches “{q}”." },
  "agentConn.note.needed": { es: "lo necesita una habilidad de este agente", en: "a skill of this agent needs it" },

  "agentConn.settings": { es: "Ajustes", en: "Settings" },
  "agentConn.remove": { es: "Quitar de este agente", en: "Remove from this agent" },

  // ── Conectar (35.3, 35.4) ──────────────────────────────────────────────
  "agentConn.connect.title": { es: "Conectar {name}", en: "Connect {name}" },
  "agentConn.connect.body": {
    es: "Elige con qué permiso lo usa este agente. Si el cliente aún no lo ha autorizado, se abre su autorización y, al terminar, queda activado con este permiso.",
    en: "Choose how this agent may use it. If the client has not authorised it yet, its authorisation opens and, once done, it is turned on with this permission.",
  },
  "agentConn.connect.permission": { es: "Permiso para este agente", en: "Permission for this agent" },
  "agentConn.connect.submit": { es: "Conectar", en: "Connect" },
  "agentConn.connect.consent": {
    es: "Se abrió la autorización de {name}. Al terminarla, quedará activado en este agente con el permiso elegido.",
    en: "The authorisation for {name} opened. Once you finish it, it is turned on for this agent with the chosen permission.",
  },
  "agentConn.connect.link": { es: "Si no se abrió, ábrela aquí (caduca {when})", en: "If it did not open, open it here (expires {when})" },
  "agentConn.connect.finished": { es: "Ya la terminé", en: "I have finished" },
  "agentConn.connect.form": {
    es: "{name} se conecta con una clave. Las credenciales se cifran al guardarse y nunca se vuelven a mostrar.",
    en: "{name} connects with a key. Credentials are encrypted on save and never shown again.",
  },
  "agentConn.connect.form.submit": { es: "Guardar y conectar", en: "Save and connect" },
  "agentConn.connect.noForm": {
    es: "{name} se conecta desde los Conectores del cliente. Después vuelve aquí para elegir el permiso.",
    en: "{name} is connected from the client's Connectors. Then come back here to choose the permission.",
  },
  "agentConn.connect.goClient": { es: "Ir a los Conectores del cliente", en: "Go to the client's Connectors" },
  "agentConn.connect.done": { es: "{name} conectado y activado en este agente.", en: "{name} connected and turned on for this agent." },
  "agentConn.connect.rejected": {
    es: "{name} rechazó la clave. Revísala y vuelve a intentarlo.",
    en: "{name} rejected the key. Check it and try again.",
  },
  "agentConn.field.required": { es: "Campo obligatorio.", en: "Required field." },

  // ── Errores de la API, con palabras ────────────────────────────────────
  "agentConn.error.connection_not_authorized": {
    es: "La conexión no está autorizada. Vuelve a conectarla.",
    en: "The connection is not authorised. Connect it again.",
  },
  "agentConn.error.invalid_settings": { es: "Revisa los ajustes marcados.", en: "Check the highlighted settings." },
  "agentConn.error.settings_not_supported": { es: "Este conector no tiene ajustes.", en: "This connector has no settings." },
  "agentConn.error.unknown_integration": { es: "Este conector ya no está en el catálogo.", en: "This connector is no longer in the catalogue." },
  "agentConn.error.unknown": { es: "No se pudo guardar. Vuelve a intentarlo.", en: "Could not save. Try again." },

  // ── Quitar de este agente (35.7) ───────────────────────────────────────
  "agentConn.remove.title": { es: "Quitar {name} de este agente", en: "Remove {name} from this agent" },
  "agentConn.remove.body": {
    es: "Este agente deja de usarlo desde el siguiente mensaje. La conexión del cliente se queda para los demás agentes.",
    en: "This agent stops using it from the next message. The client's connection stays for the other agents.",
  },
  "agentConn.remove.skills": { es: "Se quedan sin él estas habilidades: {list}.", en: "These skills lose it: {list}." },
  "agentConn.remove.none": { es: "Ninguna habilidad de este agente lo pide.", en: "No skill of this agent needs it." },
  "agentConn.remove.done": { es: "Este agente ya no usa {name}.", en: "This agent no longer uses {name}." },
  "agentConn.remove.affected": { es: "Este agente ya no usa {name}. Se quedan sin él: {list}.", en: "This agent no longer uses {name}. These lose it: {list}." },

  // ── Los ajustes (36.2) ─────────────────────────────────────────────────
  "agentConn.settings.title": { es: "Ajustes de {name} en este agente", en: "{name} settings for this agent" },
  "agentConn.settings.body": { es: "Se aplican desde el siguiente mensaje.", en: "They apply from the next message." },
  "agentConn.settings.saved": { es: "Ajustes de {name} guardados.", en: "{name} settings saved." },
  "agentConn.settings.invalid": { es: "Revisa este valor.", en: "Check this value." },
  "agentConn.settings.integer": { es: "Escribe un número entero entre {min} y {max}.", en: "Type a whole number between {min} and {max}." },
  "agentConn.settings.https": { es: "Tiene que empezar por https://", en: "It must start with https://" },
  "agentConn.settings.none": { es: "Sin ajustes", en: "No settings" },
  "agentConn.settings.yes": { es: "Sí", en: "Yes" },
  "agentConn.settings.no": { es: "No", en: "No" },
  "agentConn.setting.woocommerce.store_url": { es: "Dirección de la tienda", en: "Store address" },
  "agentConn.setting.amigable_cobro.business_uuid": { es: "Identificador del negocio", en: "Business identifier" },
  "agentConn.setting.amigable_cobro.base_url": { es: "Dirección del servicio", en: "Service address" },
  "agentConn.setting.amigable_cobro.reminders": { es: "Recordatorios de cobro", en: "Payment reminders" },
  "agentConn.setting.amigable_cobro.reminders.enabled": { es: "Enviar recordatorios", en: "Send reminders" },
  "agentConn.setting.amigable_cobro.reminders.hour_local": { es: "Hora del envío, en la hora del negocio", en: "Sending hour, in the business's time" },
  "agentConn.setting.amigable_cobro.reminders.max_overdue_days": { es: "Días de retraso como máximo", en: "Most days overdue" },
  "agentConn.setting.amigable_cobro.reminders.max_per_run": { es: "Recordatorios por envío como máximo", en: "Most reminders per run" },
  "agentConn.setting.googlecalendar.calendar_id": { es: "Calendario por defecto", en: "Default calendar" },

  // ── La página de cada conexión (36.1) ──────────────────────────────────
  "connPage.title": { es: "Conector", en: "Connector" },
  "connPage.back.agent": { es: "Volver al agente", en: "Back to the agent" },
  "connPage.back.client": { es: "Volver a los Conectores", en: "Back to Connectors" },
  "connPage.details": { es: "La conexión", en: "The connection" },
  "connPage.account": { es: "Cuenta conectada", en: "Connected account" },
  "connPage.account.none": { es: "El servicio no dice qué cuenta es", en: "The service does not say which account it is" },
  "connPage.state": { es: "Estado", en: "Status" },
  "connPage.connectedAt": { es: "Conectado desde", en: "Connected since" },
  "connPage.checkedAt": { es: "Última comprobación", en: "Last check" },
  "connPage.checkedAt.never": { es: "Aún sin comprobar", en: "Not checked yet" },
  "connPage.reauth": {
    es: "Hay que volver a autorizar {name}. Mientras tanto, los agentes que lo usan no pueden usarlo y sus pruebas lo reflejan.",
    en: "{name} needs authorising again. Until then, the agents that use it cannot, and their tests show it.",
  },
  "connPage.agents": { es: "Agentes que lo usan", en: "Agents that use it" },
  "connPage.agents.empty": {
    es: "Ningún agente lo usa todavía. Se activa desde la sección Conectores de cada agente.",
    en: "No agent uses it yet. It is turned on from each agent's Connectors section.",
  },
  "connPage.agents.agent": { es: "Agente", en: "Agent" },
  "connPage.agents.permission": { es: "Permiso", en: "Permission" },
  "connPage.agents.settings": { es: "Ajustes", en: "Settings" },
  "connPage.agents.actions": { es: "Más acciones de {name}", en: "More actions for {name}" },
  "connPage.agents.permissionOf": { es: "Permiso de {agent} con {name}", en: "{agent} permission for {name}" },
  "connPage.openAgent": { es: "Abrir el agente", en: "Open the agent" },
  "connPage.remove.title": { es: "Quitar {name} de {agent}", en: "Remove {name} from {agent}" },
  "connPage.removed": { es: "{agent} ya no usa {name}.", en: "{agent} no longer uses {name}." },
  "connPage.removed.affected": { es: "{agent} ya no usa {name}. Se quedan sin él: {list}.", en: "{agent} no longer uses {name}. These lose it: {list}." },
  "connPage.reconnect": { es: "Reconectar", en: "Reconnect" },
  "connPage.reconnect.opened": {
    es: "Se abrió la autorización de {name}. Los agentes conservan su permiso.",
    en: "The authorisation for {name} opened. The agents keep their permission.",
  },
  "connPage.disconnect": { es: "Desconectar para todos", en: "Disconnect for everyone" },
  "connPage.disconnect.title": { es: "Desconectar {name} para todos los agentes", en: "Disconnect {name} for every agent" },
  "connPage.disconnect.body": {
    es: "Se borran las credenciales y ningún agente de este cliente podrá usarlo hasta conectarlo otra vez.",
    en: "The credentials are deleted and no agent of this client can use it until it is connected again.",
  },
  "connPage.disconnect.affected": { es: "Lo usan estos agentes:", en: "These agents use it:" },
  "connPage.disconnect.agentSkills": { es: "{name}, pierde {list}", en: "{name}, loses {list}" },
  "connPage.disconnect.agentNoSkills": { es: "{name}, ninguna habilidad lo pide", en: "{name}, no skill needs it" },
  "connPage.disconnect.nobody": { es: "Ningún agente lo usa.", en: "No agent uses it." },
  "connPage.disconnect.done": { es: "{name} desconectado para todos.", en: "{name} disconnected for everyone." },
  "connPage.readonly": { es: "Tu rol puede ver este conector, no cambiarlo.", en: "Your role can see this connector, not change it." },
} as const;
