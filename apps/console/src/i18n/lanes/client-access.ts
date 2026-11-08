/** ES/EN del carril `client-access` — la pestaña «Acceso» de un cliente en la
 *  consola de partners (spec 056, requisito 3; D3, D4): «Consola del cliente» y
 *  «Personas». Las reglas y los códigos son los del panel de Auphere
 *  (`apps/admin/.../access/messages.ts`), dichos al partner. La pestaña
 *  (`clients.v2.tab.access`) vive en el carril `business`. Sin punto y coma
 *  (`words.test.ts`). */
export const clientAccessMessages = {
  "clientAccess.page.title": { es: "Acceso", en: "Access" },
  "clientAccess.loading": { es: "Cargando el acceso del cliente", en: "Loading the client’s access" },
  "clientAccess.load.error": { es: "No pudimos leer el acceso de este cliente", en: "We could not read this client’s access" },
  "clientAccess.load.error.hint": { es: "No se ha cambiado nada. Vuelve a intentarlo en un momento.", en: "Nothing has changed. Try again in a moment." },
  "clientAccess.retry": { es: "Reintentar", en: "Try again" },
  "clientAccess.cancel": { es: "Cancelar", en: "Cancel" },
  "clientAccess.optional": { es: "Opcional", en: "Optional" },

  // ── Consola del cliente (3.3) ──
  "clientAccess.console.title": { es: "Consola del cliente", en: "Client console" },
  "clientAccess.console.description": {
    es: "Lo que el negocio ve cuando entra en su consola y en la app Auphere Customers.",
    en: "What the business sees when it signs in to its console and to the Auphere Customers app.",
  },
  "clientAccess.console.empty": {
    es: "Este cliente aún no tiene consola. Enciéndela y elige qué verá.",
    en: "This client has no console yet. Switch it on and choose what it will see.",
  },
  "clientAccess.console.on": { es: "Consola encendida", en: "Console on" },
  "clientAccess.console.on.hint": {
    es: "Apagarla cierra al momento las sesiones de todas sus personas, también en el teléfono.",
    en: "Switching it off ends every session of its people at once, on the phone too.",
  },
  "clientAccess.console.readonly.on": {
    es: "Tenía la consola encendida con {modules}. Mientras siga así no se puede cambiar.",
    en: "Its console was on with {modules}. While this lasts it cannot be changed.",
  },
  "clientAccess.console.readonly.off": {
    es: "No tiene la consola encendida. Mientras siga así no se puede encender.",
    en: "Its console is off. While this lasts it cannot be switched on.",
  },
  "clientAccess.modules": { es: "Qué verá", en: "What it will see" },
  "clientAccess.module.panel": { es: "Panel", en: "Dashboard" },
  "clientAccess.module.panel.hint": { es: "Cómo va su agente, lo que gasta y lo que le necesita.", en: "How its agent is doing, what it spends and what needs it." },
  "clientAccess.module.inbox": { es: "Bandeja de entrada", en: "Inbox" },
  "clientAccess.module.inbox.hint": {
    es: "Sus conversaciones de WhatsApp: leerlas, tomar el control y contestar.",
    en: "Its WhatsApp conversations: reading them, taking over and replying.",
  },
  "clientAccess.module.inbox.locked": {
    es: "Necesita un WhatsApp conectado. Conéctalo en un agente de este cliente.",
    en: "It needs a connected WhatsApp. Connect one on an agent of this client.",
  },
  "clientAccess.module.reservas": { es: "Reservas", en: "Bookings" },
  "clientAccess.module.reservas.hint": {
    es: "Su agenda: lo que reserva el agente por WhatsApp y lo que apunta su equipo.",
    en: "Its calendar: what the agent books on WhatsApp and what its team writes down.",
  },
  "clientAccess.module.usage": { es: "Consumo", en: "Usage" },
  "clientAccess.module.usage.hint": { es: "Su saldo y su gasto por día. Solo lectura.", en: "Its balance and its spend per day. Read only." },
  "clientAccess.reservas.mode": { es: "Cómo reserva el negocio", en: "How the business takes bookings" },
  "clientAccess.reservas.mode.services": { es: "Servicios", en: "Services" },
  "clientAccess.reservas.mode.services.hint": {
    es: "citas con una persona del equipo (peluquería, clínica, asesoría)",
    en: "appointments with a person of the team (hair salon, clinic, consultancy)",
  },
  "clientAccess.reservas.mode.capacity": { es: "Aforo", en: "Capacity" },
  "clientAccess.reservas.mode.capacity.hint": {
    es: "personas por hora, sin mesas (restaurante, bar, clases, tours, salas, spa)",
    en: "people per hour, without tables (restaurant, bar, classes, tours, rooms, spa)",
  },
  "clientAccess.reservas.kind": { es: "Tipo de negocio", en: "Kind of business" },
  "clientAccess.reservas.kind.pick": { es: "Elige uno", en: "Pick one" },
  "clientAccess.reservas.kind.restaurant": { es: "Restaurante", en: "Restaurant" },
  "clientAccess.reservas.kind.bar": { es: "Bar y terraza", en: "Bar and terrace" },
  "clientAccess.reservas.kind.classes": { es: "Clases y gimnasio", en: "Classes and gym" },
  "clientAccess.reservas.kind.tours": { es: "Tours y experiencias", en: "Tours and experiences" },
  "clientAccess.reservas.kind.rooms": { es: "Salas y eventos", en: "Rooms and events" },
  "clientAccess.reservas.kind.spa": { es: "Spa y circuitos", en: "Spa and circuits" },
  "clientAccess.reservas.kind.renames": {
    es: "Cambiar el tipo solo cambia las palabras. Aforo, estancia y plazas guardadas siguen como las dejó el negocio.",
    en: "Changing the kind only changes the words. Capacity, stay and held places stay as the business left them.",
  },
  "clientAccess.reservas.pendingAgents": {
    es: "Estos agentes tienen una versión preparada con Reservas. Revísala y publícala",
    en: "These agents have a version ready with Bookings. Review it and publish it",
  },
  "clientAccess.reservas.agentVersion": { es: "{name}, versión {version}", en: "{name}, version {version}" },
  "clientAccess.reservas.otherCalendar": {
    es: "Estos agentes ya reservan con un conector, así que no se les añadió Reservas para no reservar en dos sitios",
    en: "These agents already book with a connector, so Bookings was not added to them to avoid booking in two places",
  },
  "clientAccess.console.save": { es: "Guardar", en: "Save" },
  "clientAccess.console.saving": { es: "Guardando", en: "Saving" },
  "clientAccess.console.saved": { es: "Acceso guardado", en: "Access saved" },
  "clientAccess.console.saved.off": {
    es: "Consola apagada. Se cerraron las sesiones de sus personas",
    en: "Console off. Its people’s sessions were ended",
  },
  "clientAccess.console.saved.modeChanged": {
    es: "Modo cambiado. Se cancelaron las reservas futuras y se avisa a cada cliente por WhatsApp",
    en: "Mode changed. Future bookings were cancelled and each customer is told on WhatsApp",
  },
  "clientAccess.live.title": { es: "¿Cambiar el modo de Reservas?", en: "Change the Bookings mode?" },
  "clientAccess.live.body": {
    es: "Hay reservas futuras. Cambiar de modo las cancela y avisa a cada cliente por WhatsApp.",
    en: "There are future bookings. Changing the mode cancels them and tells each customer on WhatsApp.",
  },
  "clientAccess.live.body.one": {
    es: "Hay {n} reserva futura. Cambiar de modo la cancela y avisa al cliente por WhatsApp.",
    en: "There is {n} future booking. Changing the mode cancels it and tells the customer on WhatsApp.",
  },
  "clientAccess.live.body.other": {
    es: "Hay {n} reservas futuras. Cambiar de modo las cancela y avisa a cada cliente por WhatsApp.",
    en: "There are {n} future bookings. Changing the mode cancels them and tells each customer on WhatsApp.",
  },
  "clientAccess.live.confirm": { es: "Cancelarlas y cambiar", en: "Cancel them and change" },
  "clientAccess.live.keep": { es: "No cambiar", en: "Do not change" },

  // ── Personas (3.4 a 3.7) ──
  "clientAccess.people.title": { es: "Personas", en: "People" },
  "clientAccess.people.description": {
    es: "Quién entra en la consola de este cliente y en qué punto está.",
    en: "Who signs in to this client’s console and where they stand.",
  },
  "clientAccess.people.list": { es: "Personas del cliente", en: "The client’s people" },
  "clientAccess.people.empty": { es: "Aún no hay nadie", en: "Nobody yet" },
  "clientAccess.people.empty.hint": {
    es: "Invita a quien lleve el negocio. Le llegará un enlace por correo.",
    en: "Invite whoever runs the business. They will get a link by email.",
  },
  "clientAccess.people.closed": {
    es: "La consola está apagada. Enciéndela para invitar a alguien. Quien ya estaba no puede entrar mientras tanto.",
    en: "The console is off. Switch it on to invite someone. Whoever was in cannot sign in meanwhile.",
  },
  "clientAccess.people.ineligible": {
    es: "Este cliente no puede abrir su consola ahora, así que no se invita a nadie.",
    en: "This client cannot open its console right now, so nobody is invited.",
  },
  "clientAccess.invite.title": { es: "Invitar a una persona", en: "Invite a person" },
  "clientAccess.invite.email": { es: "Correo", en: "Email" },
  "clientAccess.invite.email.placeholder": { es: "nombre@negocio.com", en: "name@business.com" },
  "clientAccess.invite.name": { es: "Nombre", en: "Name" },
  "clientAccess.invite.send": { es: "Invitar", en: "Invite" },
  "clientAccess.invite.hint": {
    es: "El enlace sirve una vez y caduca a los 21 días. Invita solo a personas del negocio, porque con la Bandeja leen sus conversaciones.",
    en: "The link works once and expires after 21 days. Invite only people of the business, because with the Inbox they read its conversations.",
  },
  "clientAccess.invite.error.email": { es: "Escribe un correo válido, como nombre@negocio.com", en: "Type a valid email, like name@business.com" },
  "clientAccess.status.active": { es: "Activa", en: "Active" },
  "clientAccess.status.pending": { es: "Invitada", en: "Invited" },
  "clientAccess.status.expired": { es: "Caducada", en: "Expired" },
  "clientAccess.status.revoked": { es: "Revocada", en: "Revoked" },
  "clientAccess.person.until": { es: "El enlace vale hasta el {date}", en: "The link is valid until {date}" },
  "clientAccess.resend": { es: "Reenviar", en: "Resend" },
  "clientAccess.resend.named": { es: "Reenviar la invitación a {email}", en: "Resend the invitation to {email}" },
  "clientAccess.more.named": { es: "Más acciones de {name}", en: "More actions for {name}" },
  "clientAccess.revoke": { es: "Revocar", en: "Revoke" },
  "clientAccess.revoke.member": { es: "Revocar el acceso", en: "Revoke access" },
  "clientAccess.revoke.member.title": { es: "¿Revocar el acceso?", en: "Revoke access?" },
  "clientAccess.revoke.member.body": {
    es: "{email} dejará de entrar en la consola y en la app. Sus sesiones se cierran ahora mismo. Para que vuelva, invítala otra vez.",
    en: "{email} will no longer sign in to the console or the app. Their sessions end right now. To bring them back, invite them again.",
  },
  "clientAccess.revoke.invitation": { es: "Revocar la invitación", en: "Revoke the invitation" },
  "clientAccess.revoke.invitation.title": { es: "¿Revocar la invitación?", en: "Revoke the invitation?" },
  "clientAccess.revoke.invitation.body": {
    es: "El enlace que recibió {email} deja de servir. Puedes invitarla otra vez cuando quieras.",
    en: "The link {email} received stops working. You can invite them again whenever you want.",
  },
  "clientAccess.revoked.member": { es: "{email} ya no tiene acceso", en: "{email} no longer has access" },
  "clientAccess.revoked.invitation": { es: "Invitación revocada", en: "Invitation revoked" },

  // ── El enlace, una sola vez (3.6) ──
  "clientAccess.link.sent": { es: "Invitación enviada a {email}", en: "Invitation sent to {email}" },
  "clientAccess.link.sent.hint": {
    es: "También puedes pasarle este enlace a mano. Vale hasta el {date} y solo se enseña ahora.",
    en: "You can also hand them this link. It is valid until {date} and it is only shown now.",
  },
  "clientAccess.link.notSent": { es: "El correo a {email} no salió", en: "The email to {email} did not go out" },
  "clientAccess.link.notSent.hint": {
    es: "Pásale este enlace a mano. Vale hasta el {date} y solo se enseña ahora. Si lo pierdes, reenvía la invitación.",
    en: "Hand them this link yourself. It is valid until {date} and it is only shown now. If you lose it, resend the invitation.",
  },
  "clientAccess.link.label": { es: "Enlace de la invitación de {email}", en: "Invitation link for {email}" },
  "clientAccess.link.copy": { es: "Copiar", en: "Copy" },
  "clientAccess.link.copy.named": { es: "Copiar el enlace de {email}", en: "Copy the link for {email}" },
  "clientAccess.link.copied": { es: "Enlace copiado", en: "Link copied" },
  "clientAccess.link.copyFailed": { es: "No se pudo copiar. Selecciona el enlace y cópialo a mano.", en: "It could not be copied. Select the link and copy it yourself." },
  "clientAccess.link.dismiss": { es: "Cerrar el aviso de {email}", en: "Close the notice for {email}" },

  // ── Los no de la API, en palabras (nunca el texto técnico) ──
  "clientAccess.error.generic": { es: "No se pudo hacer. No se ha cambiado nada.", en: "That did not work. Nothing has changed." },
  "clientAccess.error.no_partner": { es: "Este cliente no está en tu cuenta.", en: "This client is not in your account." },
  "clientAccess.error.archived": { es: "El cliente está archivado. No se le puede dar acceso.", en: "The client is archived. It cannot be given access." },
  "clientAccess.error.no_modules": { es: "Elige al menos una cosa que verá para encender la consola.", en: "Choose at least one thing it will see to switch the console on." },
  "clientAccess.error.inbox_requires_whatsapp": {
    es: "La Bandeja de entrada necesita un WhatsApp conectado.",
    en: "The Inbox needs a connected WhatsApp.",
  },
  "clientAccess.error.unknown_module": { es: "Eso ya no se puede dar a un cliente. Recarga la página.", en: "That can no longer be given to a client. Reload the page." },
  "clientAccess.error.reservas_mode_required": { es: "Elige cómo reserva el negocio, Servicios o Aforo.", en: "Choose how the business takes bookings, Services or Capacity." },
  "clientAccess.error.reservas_kind_required": { es: "Con Aforo, elige el tipo de negocio.", en: "With Capacity, choose the kind of business." },
  "clientAccess.error.reservas_kind_forbidden": { es: "El tipo de negocio solo va con Aforo.", en: "The kind of business only goes with Capacity." },
  "clientAccess.error.live_reservations": {
    es: "Hay reservas futuras. Cambiar de modo las cancela y avisa a cada cliente por WhatsApp.",
    en: "There are future bookings. Changing the mode cancels them and tells each customer on WhatsApp.",
  },
  "clientAccess.error.access_disabled": { es: "Enciende la consola antes de invitar a nadie.", en: "Switch the console on before inviting anyone." },
  "clientAccess.error.account_is_partner_member": {
    es: "Ese correo es de un equipo de partner. Una cuenta no puede ser a la vez de un partner y de un cliente.",
    en: "That email belongs to a partner’s team. An account cannot be a partner’s and a client’s at the same time.",
  },
  "clientAccess.error.account_is_other_client": { es: "Ese correo ya entra en la consola de otro cliente.", en: "That email already signs in to another client’s console." },
  "clientAccess.error.already_member": { es: "Esa persona ya tiene acceso.", en: "That person already has access." },
  "clientAccess.error.not_an_invitation": { es: "Solo se pueden reenviar invitaciones.", en: "Only invitations can be resent." },
  "clientAccess.error.unknown_member": { es: "Esa persona ya no está en la lista. Recarga la página.", en: "That person is no longer on the list. Reload the page." },
  "clientAccess.error.rate_limited": {
    es: "Demasiadas invitaciones seguidas. Espera un minuto y vuelve a intentarlo.",
    en: "Too many invitations in a row. Wait a minute and try again.",
  },
} as const;
