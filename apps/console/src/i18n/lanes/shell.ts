/** ES/EN del carril `shell` — el marco de la consola nueva (spec 047, R47).
 *
 *  La barra lateral, las migas, la campana, el menú de perfil y la paleta ⌘K.
 *  Las pantallas y acciones que devuelve `GET /console/search` viajan como
 *  claves estables; su texto vive aquí (`shell.search.screen.<key>` y
 *  `shell.search.action.<key>`). */
export const shellMessages = {
  // ── Spec 056 (10.1, 14): una pantalla que falla y una ruta que no existe ──
  "shell.error.load.title": { es: "No se pudo cargar esta pantalla", en: "This screen could not load" },
  "shell.error.load.body": { es: "Vuelve a intentarlo en un momento.", en: "Try again in a moment." },
  "shell.notFound.title": { es: "Esta página no está", en: "This page is not here" },
  "shell.notFound.body": { es: "No existe o no es tuya.", en: "It does not exist or it is not yours." },
  "shell.notFound.home": { es: "Ir al inicio", en: "Go to the start" },
  "shell.notFound.signIn": { es: "Entrar", en: "Sign in" },
  // ── Spec 056 (15): la sesión caduca a los 7 días, sin renovarse ──
  "shell.session.expiring": {
    es: "Tu sesión caduca en menos de un día. Vuelve a entrar para seguir sin cortes.",
    en: "Your session expires in less than a day. Sign in again to keep going without interruptions.",
  },
  "shell.session.signInAgain": { es: "Volver a entrar", en: "Sign in again" },
  // ── El menú lateral (R47.1) ──────────────────────────────────────
  "shell.nav.label": { es: "Menú principal", en: "Main menu" },
  "shell.nav.collapse": { es: "Plegar menú", en: "Collapse menu" },
  "shell.nav.expand": { es: "Abrir menú", en: "Open menu" },
  "shell.nav.mobile.hide": { es: "Ocultar el menú", en: "Hide the menu" },
  "shell.nav.mobile.show": { es: "Mostrar el menú", en: "Show the menu" },
  // ── Las migas (R47.1) ────────────────────────────────────────────
  "shell.crumbs.label": { es: "Migas de pan", en: "Breadcrumb" },
  "shell.crumbs.usageAlerts": { es: "Alertas de consumo", en: "Usage alerts" },
  "shell.crumbs.newClient": { es: "Nuevo cliente", en: "New client" },
  "shell.crumbs.agent": { es: "Agente", en: "Agent" },
  "shell.crumbs.channel": { es: "Canal {name}", en: "Channel {name}" },
  "shell.crumbs.channelUnnamed": { es: "Canal", en: "Channel" },
  // ── El menú de perfil (R47.1) ────────────────────────────────────
  "shell.profile.open": { es: "Perfil de {name}", en: "{name}'s profile" },
  // ── La campana (R47.3) ───────────────────────────────────────────
  "shell.bell.markAll": { es: "Marcar todo como leído", en: "Mark all as read" },
  "shell.bell.markAllError": {
    es: "No se pudieron marcar como leídas. Inténtalo de nuevo.",
    en: "They could not be marked as read. Try again.",
  },
  "shell.bell.viewAll": { es: "Ver todas", en: "See all" },
  "shell.bell.unread": { es: "Sin leer", en: "Unread" },
  // ── La paleta ⌘K (R47.2) ─────────────────────────────────────────
  "shell.search.group.clients": { es: "Clientes", en: "Clients" },
  "shell.search.group.agents": { es: "Agentes", en: "Agents" },
  "shell.search.group.screens": { es: "Pantallas", en: "Screens" },
  "shell.search.group.actions": { es: "Acciones", en: "Actions" },
  // Las pestañas de un cliente: la paleta las pinta sin que la API las mande.
  "shell.search.client.business": { es: "{client} · Negocio", en: "{client} · Business" },
  "shell.search.client.agents": { es: "{client} · Agentes", en: "{client} · Agents" },
  "shell.search.screen.home": { es: "Panel", en: "Dashboard" },
  "shell.search.screen.clients": { es: "Clientes", en: "Clients" },
  "shell.search.screen.usage": { es: "Consumo", en: "Usage" },
  "shell.search.screen.audit": { es: "Auditoría", en: "Audit" },
  "shell.search.screen.knowledge": { es: "Guía del partner", en: "Playbook" },
  "shell.search.screen.workstation": { es: "Teammate", en: "Teammate" },
  "shell.search.screen.team": { es: "Equipo", en: "Team" },
  "shell.search.screen.billing": { es: "Facturación", en: "Billing" },
  "shell.search.screen.keys": { es: "API", en: "API" },
  "shell.search.screen.notifications": { es: "Notificaciones", en: "Notifications" },
  "shell.search.action.new_client": { es: "Nuevo cliente", en: "New client" },
  "shell.search.action.invite_member": { es: "Invitar a alguien al equipo", en: "Invite someone to the team" },
  "shell.search.action.new_api_key": { es: "Nueva clave de API", en: "New API key" },
} as const;
