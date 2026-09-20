/**
 * Los textos de la pantalla de operar. Los del hilo viven en el paquete
 * (`CompanionLocaleProvider`); aquí solo lo que es de la app: el roster, los
 * estados, la sesión. Sin tildes en los identificadores; con tildes en lo que
 * se lee.
 */
import * as React from "react";

export type Lang = "es" | "en";

const COPY = {
  "app.title": { es: "Tu equipo", en: "Your team" },
  "roster.empty.title": { es: "Todavía no tienes teammates", en: "No teammates yet" },
  "roster.empty.body": { es: "Crea el primero: llega con su oficio, su modelo y sin permisos peligrosos.", en: "Create the first one: it arrives with a job, a model and no dangerous permissions." },
  "roster.create": { es: "Crear teammate", en: "Create teammate" },
  "roster.loading": { es: "Cargando tu equipo…", en: "Loading your team…" },
  "roster.error": { es: "No se pudo leer el equipo. La plataforma respondió, la pantalla no.", en: "Could not read the team. The platform answered; the screen did not." },
  "roster.retry": { es: "Reintentar", en: "Retry" },
  "roster.forbidden": { es: "Tu rol no puede usar teammates. Pídele a un administrador el rol de constructor.", en: "Your role cannot use teammates. Ask an administrator for the builder role." },
  "state.en_marcha": { es: "En marcha", en: "Working" },
  "state.esperandote": { es: "Esperándote", en: "Waiting for you" },
  "state.en_pausa_por_tope": { es: "En pausa por tope", en: "Paused: cap reached" },
  "state.bloqueado": { es: "Esperando a otro", en: "Waiting on another" },
  "state.en_espera": { es: "En espera", en: "Idle" },
  "state.unread": { es: "Te contestó", en: "Replied" },
  "thread.pick": { es: "Elige un teammate para abrir tu hilo con él.", en: "Pick a teammate to open your thread." },
  "thread.opening": { es: "Abriendo tu hilo…", en: "Opening your thread…" },
  "thread.state.cargando": { es: "Cargando la conversación…", en: "Loading the conversation…" },
  "thread.state.vacio": { es: "Tu hilo con {name} está vacío. Lo que le pidas sigue aunque cierres la aplicación.", en: "Your thread with {name} is empty. What you ask keeps going even if you close the app." },
  "thread.state.error": { es: "La plataforma respondió, el hilo no. Lo que tenía en marcha sigue corriendo en el servidor: esto es la pantalla, no el trabajo.", en: "The platform answered, the thread did not. Whatever was running keeps running on the server: this is the screen, not the work." },
  "thread.state.reconectando": { es: "Reconectando… el trabajo sigue.", en: "Reconnecting… the work continues." },
  "thread.state.parcial": { es: "Se muestra parte de la conversación: hay turnos que no se pudieron leer.", en: "Part of the conversation is shown: some turns could not be read." },
  "thread.state.esperandote": { es: "{name} espera una decisión tuya.", en: "{name} is waiting for your decision." },
  "thread.state.en_pausa_por_tope": { es: "Trabajo en pausa: alcanzaste el tope. Los hilos y las confirmaciones siguen vivos. El tope se sube desde la consola.", en: "Work paused: the cap was reached. Threads and confirmations stay alive. Raise the cap from the console." },
  "thread.state.maquina_ausente": { es: "{name} necesita tu máquina y no está conectada. Sigue con todo lo demás.", en: "{name} needs your machine and it is not connected. Everything else continues." },
  // ── crear teammate (US4, R2.1) ────────────────────────────────────────
  "create.title": { es: "Nuevo teammate", en: "New teammate" },
  "create.name": { es: "Nombre", en: "Name" },
  "create.job": { es: "Oficio", en: "Job" },
  "create.model": { es: "Cerebro", en: "Brain" },
  "create.permissions": { es: "Qué le dejas hacer", en: "What it may do" },
  "create.submit": { es: "Crear teammate", en: "Create teammate" },
  "create.cancel": { es: "Cancelar", en: "Cancel" },
  "create.loading": { es: "Cargando oficios y modelos…", en: "Loading jobs and models…" },
  "create.error": { es: "No se pudieron leer los oficios y los modelos. Sin ellos el formulario no puede terminar.", en: "Could not read jobs and models. Without them the form cannot be completed." },
  "create.noModels": {
    es: "Tu partner no tiene ningún modelo habilitado, así que no hay cerebro que darle a un teammate. Lo habilita un administrador desde la consola.",
    en: "Your partner has no model enabled, so there is no brain to give a teammate. An administrator enables it from the console.",
  },
  "create.cost.bajo": { es: "Gasta poco", en: "Spends little" },
  "create.cost.medio": { es: "Gasta lo normal", en: "Spends about average" },
  "create.cost.alto": { es: "Gasta más", en: "Spends more" },
  "create.cost.desconocido": { es: "Cuánto gasta: no consta", en: "How much it spends: not on record" },
  "create.perm.read": { es: "Leer", en: "Read" },
  "create.perm.read.hint": { es: "Ver clientes, canales, consumo y auditoría. No cambia nada.", en: "See clients, channels, usage and audit. Changes nothing." },
  "create.perm.write": { es: "Proponer cambios", en: "Propose changes" },
  "create.perm.write.hint": { es: "Prepara cambios y los prueba; los aplica cuando tú confirmas.", en: "Prepares and tests changes; applies them when you confirm." },
  "create.perm.spend": { es: "Gastar", en: "Spend" },
  "create.perm.spend.hint": { es: "Mover el reparto de consumo y elegir modelo de un cliente.", en: "Move usage allocation and pick a client's model." },
  "create.perm.publish": { es: "Publicar", en: "Publish" },
  "create.perm.publish.hint": { es: "Poner una versión del agente en producción.", en: "Put a version of the agent into production." },
  "create.perm.contact": { es: "Invitar y pedir ayuda", en: "Invite and ask for help" },
  "create.perm.contact.hint": { es: "Invitar a alguien al equipo y abrir tickets a Auphere.", en: "Invite someone to the team and open tickets with Auphere." },
  "create.perm.local_exec": { es: "Ejecutar en tu máquina", en: "Run on your machine" },
  "create.perm.local_exec.hint": { es: "Solo programas de la lista del cliente, y siempre con tu política delante.", en: "Only programs on the client's list, and always behind your policy." },
  "create.failed.model_not_allowed": { es: "Ese modelo no está en la lista de tu partner. Elige otro o pídeselo a un administrador.", en: "That model is not on your partner's list. Pick another or ask an administrator." },
  "create.failed.tool_not_in_catalog": { es: "La plataforma no reconoce alguna de las herramientas de esos permisos. No se ha creado nada.", en: "The platform does not recognise one of the tools for those permissions. Nothing was created." },
  "create.failed.unknown": { es: "No se pudo crear. No se ha creado nada; vuelve a intentarlo.", en: "Could not create it. Nothing was created; try again." },
  // El tope del plan. **Tres frases y no una**: el rechazo es correcto, así que
  // ninguna dice «vuelve a intentarlo» — no hay nada que reintentar—, y un plan
  // de cero no es lo mismo que un plan lleno. Con Free, `limit` y `current`
  // valen los dos 0: «admite 0 y ya tienes 0» suena a avería del sistema, y
  // ofrecer archivar no lleva a ninguna parte porque no hay nada que liberar.
  "create.failed.tier_none": {
    es: "Tu plan no incluye teammates. Para crear uno hay que cambiar de plan, en Cuenta.",
    en: "Your plan includes no teammates. Creating one means changing plan, in Account.",
  },
  "create.failed.tier_full": {
    es: "Tu plan admite {limit} teammates y ya tienes {current}. Archiva uno o cambia de plan, en Cuenta.",
    en: "Your plan allows {limit} teammates and you already have {current}. Archive one or change plan, in Account.",
  },
  // Cuando los números no llegan —el cuerpo viene de la red y puede venir con
  // otra forma—, se dice lo que sí se sabe. Nunca un hueco ni un `undefined`.
  "create.failed.tier_limit_reached": {
    es: "Tu plan no permite crear más teammates. Puedes cambiarlo en Cuenta.",
    en: "Your plan does not allow more teammates. You can change it in Account.",
  },
  // ── cambiar y archivar (US4, R2.3 y R2.6) ─────────────────────────────
  "settings.title": { es: "Ajustes del teammate", en: "Teammate settings" },
  "settings.save": { es: "Guardar cambios", en: "Save changes" },
  "settings.close": { es: "Cerrar", en: "Close" },
  "settings.jobHint": { es: "Cambiar el oficio o los permisos cambia lo que puede hacer desde el siguiente turno, y queda anotado en los hilos.", en: "Changing the job or the permissions changes what it can do from the next turn, and it is noted in the threads." },
  "settings.archive": { es: "Archivar", en: "Archive" },
  "settings.archive.confirm": {
    es: "Archivar a {name} lo saca del equipo y cancela lo que estuviera esperándote. No se borra: sus hilos siguen legibles y su historial también.",
    en: "Archiving {name} removes it from the team and cancels whatever was waiting for you. Nothing is deleted: its threads and history stay readable.",
  },
  "settings.archive.yes": { es: "Sí, archivar", en: "Yes, archive" },
  "settings.archive.no": { es: "Mejor no", en: "Never mind" },
  "settings.archived": { es: "Este teammate está archivado. Sus hilos siguen legibles; para volver a tener uno así, crea otro.", en: "This teammate is archived. Its threads stay readable; to have one like it again, create another." },
  "settings.failed.unknown": { es: "No se pudo guardar. Nada ha cambiado; vuelve a intentarlo.", en: "Could not save. Nothing changed; try again." },
  "settings.failed.archive": { es: "No se pudo archivar. Sigue activo; vuelve a intentarlo.", en: "Could not archive it. It is still active; try again." },
  "settings.open": { es: "Ajustes", en: "Settings" },
  "changes.title": { es: "Cambios de este teammate", en: "Changes to this teammate" },
  "changes.by": { es: "por {name}", en: "by {name}" },
  "changes.field.job": { es: "el oficio", en: "the job" },
  "changes.field.permissions": { es: "los permisos", en: "the permissions" },
  "changes.field.local_exec": { es: "ejecutar en tu máquina", en: "running on your machine" },
  "changes.field.model": { es: "el modelo", en: "the model" },
  "changes.line": { es: "Cambió {what}", en: "Changed {what}" },
  // ── Cuenta (US5, R8 y R9.3) ───────────────────────────────────────────
  "nav.account": { es: "Cuenta", en: "Account" },
  "account.loading": { es: "Cargando tu consumo…", en: "Loading your usage…" },
  "account.error": { es: "No se pudo leer el consumo. Lo gastado está contado en la plataforma: esto es la pantalla.", en: "Could not read usage. What was spent is counted on the platform: this is the screen." },
  "account.usage.title": { es: "Uso de esta semana", en: "This week" },
  // Spec 004 (R7.1): proporción y fecha, **sin la cifra del pool**. El partner
  // no ve cuántos tokens le quedan; ve cuánto le queda y cuándo vuelve. Así el
  // tamaño del pool deja de ser un compromiso público y se puede ajustar sin
  // que cada ajuste sea un anuncio.
  "account.usage.line": { es: "Has usado el {percent} %. Vuelve a empezar el {resets}.", en: "You have used {percent} %. Starts over on {resets}." },
  // R7.4: el lector de pantalla recibe LO MISMO que quien ve la barra. Una
  // barra sin valores no le dice nada a nadie.
  "account.usage.valuetext": { es: "{percent} % del consumo de la semana", en: "{percent} % of this week's usage" },
  "account.usage.runs": { es: "{runs} turnos", en: "{runs} turns" },
  "account.usage.empty": { es: "Esta semana ningún teammate ha gastado todavía.", en: "No teammate has spent anything this week yet." },
  // La diferencia entre el total y lo atribuido se NOMBRA (R4.4). Sin cifra,
  // por la misma razón que la línea de arriba: lo que importa es que existe y
  // de dónde viene, no cuántos tokens son.
  "account.usage.elsewhere": {
    es: "Parte de lo consumido no sale de un teammate: la consola y lo que se ejecuta en tu máquina gastan del mismo sitio.",
    en: "Some of what was used did not come from a teammate: the console and what runs on your machine spend from the same place.",
  },
  "account.usage.capped.label": { es: "Consumo de la semana", en: "This week's usage" },
  // R5.3/R5.5: agotar el pool ya NO detiene el trabajo si hay saldo comprado.
  // Decir «se pausa» sin más sería mentir en el caso normal.
  "account.usage.capped": {
    es: "Se agotó el consumo incluido de esta semana. Si tu cuenta tiene saldo, el trabajo sigue con él; si no, queda en pausa hasta que vuelva el {resets}. Los hilos y lo que espera tu confirmación siguen vivos.",
    en: "This week's included usage is spent. If your account has credit, work continues on it; if not, it pauses until it comes back on {resets}. Threads and anything waiting for your confirmation stay alive.",
  },
  "account.team.title": { es: "Equipo", en: "Team" },
  "account.team.you": { es: "tú", en: "you" },
  "account.team.readOnly": { es: "El equipo se administra en la consola: invitar, cambiar roles y dar de baja.", en: "The team is managed in the console: inviting, changing roles and removing." },
  "account.team.unreadable": { es: "No se pudo leer el equipo. El resto de esta pantalla sigue siendo cierto.", en: "Could not read the team. The rest of this screen is still true." },
  "account.role.owner": { es: "Propietario", en: "Owner" },
  "account.role.admin": { es: "Administrador", en: "Admin" },
  "account.role.builder": { es: "Constructor", en: "Builder" },
  "account.role.analyst": { es: "Lectura", en: "Read only" },
  "account.role.billing": { es: "Facturación", en: "Billing" },
  "account.role.unknown": { es: "Rol desconocido", en: "Unknown role" },
  "account.policy.title": { es: "Ejecución en tu máquina", en: "Running on your machine" },
  "account.policy.effective": { es: "Ahora mismo se aplica: {mode}.", en: "Right now this applies: {mode}." },
  "account.policy.mode.ask": { es: "preguntar", en: "ask" },
  "account.policy.mode.always": { es: "permitir siempre", en: "always allow" },
  "account.policy.mode.never": { es: "no ejecutar nunca", en: "never run" },
  "account.policy.capped": {
    es: "El techo del partner es «{mode}» y acota lo que elegiste. Lo cambia un administrador desde la página de equipo de la consola.",
    en: "The partner ceiling is \u00ab{mode}\u00bb and caps what you chose. An administrator changes it from the team page in the console.",
  },
  "account.openConsole": { es: "Abrir la consola", en: "Open the console" },
  "account.signOut": { es: "Cerrar sesión", en: "Sign out" },
  "account.signOut.hint": {
    es: "Tu sesión es la de la consola y se cierra allí: la aplicación no añade otra.",
    en: "Your session is the console's and is closed there: the app does not add another.",
  },
  // ── panel de entorno (T080, R11) ──────────────────────────────────────
  "env.client": { es: "Cliente", en: "Client" },
  "env.workdir": { es: "Directorio", en: "Directory" },
  "env.workdir.none": { es: "Sin directorio declarado", en: "No directory declared" },
  "env.files.title": { es: "Lo que los comandos nombraron", en: "What the commands named" },
  "env.files.hint": {
    es: "Referencia de esta tarea, no un listado del directorio: la plataforma no sabe qué ficheros se escribieron, y la aplicación no los abre.",
    en: "A reference for this task, not a directory listing: the platform does not know which files were written, and the app does not open them.",
  },
  "env.setup.title": { es: "Puesta en marcha", en: "Setup" },
  "env.setup.noMachine": {
    es: "No hay ninguna máquina emparejada, así que no hay dónde ejecutar. Se empareja desde la consola.",
    en: "No machine is paired, so there is nowhere to run. Pairing happens in the console.",
  },
  "env.setup.noWorkdir": {
    es: "Esta máquina está, pero el cliente está sin directorio declarado: hasta que lo declares no hay dónde trabajar.",
    en: "The machine is here, but the client has no directory declared: until you declare one there is nowhere to work.",
  },
  "env.setup.open": { es: "Ir a la puesta en marcha", en: "Go to setup" },
  "inbox.title": { es: "Pendientes", en: "Pending" },
  "inbox.empty.title": { es: "Nada te espera", en: "Nothing is waiting for you" },
  "inbox.empty.body": {
    es: "Cuando un teammate necesite permiso para algo que no puede hacer solo, aparece aquí. Nada se ejecuta antes.",
    en: "When a teammate needs permission for something it cannot do alone, it appears here. Nothing runs before that.",
  },
  "inbox.error": { es: "No se pudo leer Pendientes. Lo que espera sigue esperando: esto es la pantalla.", en: "Could not read Pending. What is waiting keeps waiting: this is the screen." },
  "inbox.approve": { es: "Aprobar", en: "Approve" },
  "inbox.reject": { es: "Rechazar", en: "Reject" },
  "inbox.openThread": { es: "Ver el hilo", en: "Open the thread" },
  "inbox.refresh": { es: "Actualizar", en: "Refresh" },
  "inbox.stale": { es: "Esta lista puede estar desfasada: no se pudo actualizar. Lo que ves es lo último que se leyó.", en: "This list may be out of date: it could not be refreshed. What you see is the last thing read." },
  // ── contexto de cada pendiente (US6, R10.1 y R10.7) ───────────────────
  "inbox.reversible": { es: "se puede deshacer", en: "can be undone" },
  "inbox.irreversible": { es: "no se deshace", en: "cannot be undone" },
  "inbox.decided.confirm": { es: "{by} lo aprobó", en: "{by} approved it" },
  "inbox.decided.edit": { es: "{by} pidió cambios", en: "{by} asked for changes" },
  "inbox.decided.cancel": { es: "{by} lo rechazó", en: "{by} rejected it" },
  "inbox.decided.someone": { es: "Alguien de tu equipo", en: "Someone on your team" },
  "inbox.cannotDecide": { es: "Tu rol no puede decidir esto. Pídeselo a un administrador.", en: "Your role cannot decide this. Ask an administrator." },
  "level.critico": { es: "Crítico", en: "Critical" },
  "level.aviso": { es: "Aviso", en: "Notice" },
  "level.informativo": { es: "Informativo", en: "Informative" },
  "nav.team": { es: "Equipo", en: "Team" },

  /* ── El armazón — spec 010 ──────────────────────────────────────────── */
  "shell.search": { es: "Buscar", en: "Search" },
  "shell.sidebar.operate": { es: "Operar", en: "Operate" },
  "shell.sidebar.manage": { es: "Administrar", en: "Manage" },
  "shell.sidebar.toggle": { es: "Mostrar u ocultar la lista lateral", en: "Show or hide the sidebar" },
  "shell.today": { es: "Hoy", en: "Today" },
  "shell.pending": { es: "Pendientes", en: "Pending" },
  "shell.teammates": { es: "Teammates", en: "Teammates" },
  "shell.teammates.empty": { es: "Todavía no tienes ninguno.", en: "You do not have any yet." },
  "shell.backToTeam": { es: "Volver al equipo", en: "Back to your team" },
  "shell.openConsole": { es: "Abrir la consola", en: "Open the console" },
  "shell.console": { es: "Consola", en: "Console" },
  "section.failed": { es: "No se pudo cargar «{name}».", en: "Could not load “{name}”." },
  "section.failed.keeps": { es: "Es la pantalla, no tu cuenta: lo que tengas en marcha sigue.", en: "This is the screen, not your account: anything running keeps going." },
  // ── la taxonomía de avisos (US3, R5.2 y 5.3) ──────────────────────────
  "feedback.dismiss": { es: "Entendido", en: "Got it" },
  "feedback.decide.failed": { es: "No se pudo decidir. Sigue esperando; vuelve a intentarlo.", en: "Could not be decided. It is still waiting; try again." },
  "feedback.decide.conflict": { es: "No se pudo decidir: alguien la decidió antes que tú. Actualiza para ver cómo quedó.", en: "Could not be decided: someone decided it before you. Refresh to see how it ended." },
  "feedback.policy.failed": { es: "No se pudo guardar. Tu política sigue siendo la de antes.", en: "Could not be saved. Your policy is still the previous one." },
  "feedback.send.failed": { es: "No se pudo enviar. Lo que escribiste sigue ahí.", en: "Could not be sent. What you wrote is still there." },
  "feedback.changes.failed": { es: "No se pudieron leer los cambios de este teammate. El hilo sigue.", en: "Could not read this teammate's changes. The thread continues." },
  "feedback.env.failed": { es: "No se pudo leer dónde trabaja. El hilo sigue.", en: "Could not read where it works. The thread continues." },
  "feedback.browser": { es: "Se abrió en tu navegador. Vuelve aquí cuando termines.", en: "It opened in your browser. Come back here when you are done." },
  // ── avisos del sistema (US3, R5.8) ────────────────────────────────────
  "notifications.title": { es: "Avisos", en: "Notifications" },
  "notifications.silence": { es: "Avisarme solo de lo crítico", en: "Only notify me about critical things" },
  "notifications.silence.hint": { es: "Deja de avisar por lo que puede esperar. Sigue apareciendo en Pendientes y en el número.", en: "Stops notifying about what can wait. It still shows in Pending and in the count." },
  "notifications.keeps": { es: "Lo que espera tu decisión sigue avisando siempre: si nadie decide, el trabajo se queda parado.", en: "Anything waiting for your decision always notifies: if nobody decides, the work stays parked." },
  // ── permisos del sistema (US4, R7.8 y R7.10) ──────────────────────────
  "permission.notifications.why": { es: "Para avisarte cuando un teammate espera una decisión tuya y la aplicación no está delante. Nunca se dice en el aviso qué leyó ni qué ejecutó.", en: "So we can tell you when a teammate is waiting on your decision and the app is not in front. The notice never says what it read or ran." },
  "permission.notifications.ask": { es: "Permitir los avisos", en: "Allow notifications" },
  "permission.notifications.loses": { es: "Los avisos están bloqueados: con la aplicación cerrada o detrás, no te enterarás de lo que espera tu decisión hasta que vuelvas.", en: "Notifications are blocked: with the app closed or behind, you will not hear about what waits on your decision until you come back." },
  "permission.notifications.keeps": { es: "Todo lo demás sigue igual: el trabajo corre en el servidor y lo pendiente te espera en la lista.", en: "Everything else is unchanged: the work runs on the server and what is pending waits for you in the list." },
  "permission.notifications.settings": { es: "Abrir Ajustes del sistema", en: "Open System Settings" },
  // ── la actualización (US3, R6) ────────────────────────────────────────
  "update.ready": { es: "La versión {version} está lista. Se instala cuando tú digas y vuelves a donde estabas.", en: "Version {version} is ready. It installs when you say so, and you come back to where you were." },
  "update.waiting": { es: "La versión {version} espera a que termine lo que hay en marcha. No se instala encima de una decisión sin tomar.", en: "Version {version} is waiting for what is running to finish. It will not install on top of an untaken decision." },
  "update.install": { es: "Instalar y reabrir", en: "Install and reopen" },
  "update.busy": { es: "Todavía hay trabajo en marcha.", en: "There is still work running." },
  "update.check": { es: "Buscar la actualización", en: "Look for the update" },
  "update.unsupported": { es: "Tienes la versión {installed} y la plataforma ya no la admite: hace falta la {required} o posterior.", en: "You have version {installed} and the platform no longer supports it: {required} or later is required." },
  "update.unsupported.nomin": { es: "Tienes la versión {installed} y la plataforma ya no la admite.", en: "You have version {installed} and the platform no longer supports it." },
  "update.unsupported.nochannel": { es: "El canal no tiene ninguna versión nueva ahora mismo: escríbenos y lo miramos.", en: "The channel has no new version right now: write to us and we will look into it." },
  "shell.setup": { es: "Puesta en marcha", en: "Getting set up" },
  "shell.account": { es: "Cuenta", en: "Account" },
  "shell.section.inicio": { es: "Inicio", en: "Home" },
  "shell.section.clientes": { es: "Clientes", en: "Clients" },
  "shell.section.conocimiento": { es: "Conocimiento", en: "Knowledge" },
  "shell.section.puesto": { es: "Puesto de trabajo", en: "Workstation" },
  "shell.section.consumo": { es: "Consumo", en: "Usage" },
  "shell.section.auditoria": { es: "Auditoría", en: "Audit" },
  "shell.section.notificaciones": { es: "Notificaciones", en: "Notifications" },
  "shell.section.equipo": { es: "Equipo", en: "Team" },
  "shell.section.claves": { es: "Claves de API", en: "API keys" },
  "shell.section.facturacion": { es: "Facturación", en: "Billing" },
  "shell.search.placeholder": { es: "Ve a una sección, abre un teammate, ejecuta una acción…", en: "Go to a section, open a teammate, run an action…" },
  "shell.search.empty": { es: "Nada coincide con eso.", en: "Nothing matches that." },
  "shell.command.section": { es: "Sección", en: "Section" },
  "shell.command.teammate": { es: "Teammate", en: "Teammate" },
  "shell.command.action": { es: "Acción", en: "Action" },
  "shell.command.newTeammate": { es: "Nuevo teammate", en: "New teammate" },
  "locale.tag": { es: "es", en: "en" },

  /* ── Hoy — la primera pantalla no está vacía (R7.9) ─────────────────── */
  "today.waiting.title": { es: "Lo que te espera", en: "Waiting for you" },
  "today.waiting.none": { es: "Nada espera tu decisión.", en: "Nothing is waiting for your decision." },
  "today.waiting.some": { es: "{count} decisiones esperan por ti.", en: "{count} decisions are waiting for you." },
  "today.waiting.open": { es: "Ver Pendientes", en: "Open Pending" },
  "today.team.title": { es: "Tu equipo", en: "Your team" },
  "today.machine.title": { es: "Tu máquina", en: "Your machine" },
  "workstation.action.introducir_codigo": { es: "Emparejar esta máquina", en: "Pair this machine" },
  "workstation.action.directorios": { es: "Declarar directorios", en: "Declare folders" },
  "workstation.action.desemparejar": { es: "Desemparejar", en: "Unpair" },
  "workstation.action.actualizar": { es: "Actualizar la aplicación", en: "Update the app" },

  /* ── El puesto, en la franja (R3.6) ─────────────────────────────────── */
  "workstation.bar.comprobando": { es: "Comprobando esta máquina…", en: "Checking this machine…" },
  "workstation.bar.sin_emparejar": { es: "sin emparejar", en: "not paired" },
  "workstation.bar.emparejando": { es: "emparejando…", en: "pairing…" },
  "workstation.bar.conectada": { es: "conectada", en: "connected" },
  "workstation.bar.reconectando": { es: "reconectando", en: "reconnecting" },
  "workstation.bar.sin_sesion": { es: "sin sesión", en: "no session" },
  "workstation.bar.volver_a_emparejar": { es: "hay que volver a emparejarla", en: "needs pairing again" },
  "workstation.bar.archivada_desde_consola": { es: "archivada desde la consola", en: "archived from the console" },
  "workstation.bar.version_no_admitida": { es: "esta versión ya no se admite", en: "this version is no longer supported" },
  "workstation.cause.sin_red": { es: "sin conexión", en: "no connection" },
  "workstation.cause.sin_ejecutor": { es: "falta lo que ejecuta en tu máquina", en: "what runs on your machine is missing" },
  "workstation.cause.sesion_perdida": { es: "se cerró la sesión", en: "the session ended" },

  /* ── Conexión y sesión, dichas por su nombre (R3.1, R3.4) ───────────── */
  "conn.offline": { es: "Sin conexión. Lo que ya estaba en marcha sigue en el servidor.", en: "No connection. Whatever was running keeps going on the server." },
  "conn.unconfirmed": { es: "No se ha podido comprobar la conexión.", en: "The connection could not be checked." },
  "conn.retry": { es: "Reintentar", en: "Retry" },
  "conn.back": { es: "Conexión recuperada.", en: "Connection is back." },
  "session.expired.title": { es: "Tu sesión terminó", en: "Your session ended" },
  "session.expired.body": { es: "Lo que escribiste sigue aquí. Entra otra vez y sigues donde estabas.", en: "What you wrote is still here. Sign in again and pick up where you were." },
  "session.expired.signIn": { es: "Entrar de nuevo", en: "Sign in again" },
  // Los ocho estados del turno (R4.3). `terminado` y `esperando_decision` no
  // tienen texto: no se anuncian aquí, y una clave sin uso se acaba usando.
  "turn.enviando": { es: "Enviando tu mensaje…", en: "Sending your message…" },
  "turn.esperando": { es: "Esperando la respuesta…", en: "Waiting for the answer…" },
  "turn.razonando": { es: "Pensando cómo resolverlo…", en: "Working out how to do it…" },
  "turn.herramienta": { es: "Usando {tool}…", en: "Using {tool}…" },
  "turn.herramienta.sinNombre": { es: "Usando una herramienta…", en: "Using a tool…" },
  "turn.detenido": { es: "Turno detenido. Lo que llegó a hacer sigue arriba.", en: "Turn stopped. What it got done is still above." },
  "turn.fallido": { es: "El turno falló. Lo que llegó a hacer sigue arriba.", en: "The turn failed. What it got done is still above." },
  "thread.open.error": { es: "No se pudo abrir tu hilo con {name}.", en: "Could not open your thread with {name}." },
  "thread.open.error.keeps": { es: "Lo que estuviera haciendo sigue en el servidor: esto es la pantalla, no el trabajo.", en: "Whatever it was doing keeps going on the server: this is the screen, not the work." },
  "thread.open.error.detail": { es: "Copiar el detalle", en: "Copy the details" },
  "thread.open.error.copied": { es: "Copiado", en: "Copied" },
  "nav.pending": { es: "Pendientes", en: "Pending" },
  "env.title": { es: "Entorno", en: "Environment" },
  "env.job": { es: "Oficio", en: "Job" },
  "env.model": { es: "Modelo", en: "Model" },
  "env.machine": { es: "Máquina", en: "Machine" },
  "env.machine.absent": { es: "sin conectar", en: "not connected" },
  "env.machine.none": { es: "Sin máquina emparejada — empareja la tuya desde el pie de la lista lateral.", en: "No machine paired — pair yours from the bottom of the sidebar." },
  "env.browser.soon": { es: "Navegador: todavía no.", en: "Browser: not yet." },
  "policy.title": { es: "Ejecución en tu máquina", en: "Running on your machine" },
  "policy.ask": { es: "Preguntar", en: "Ask" },
  "policy.always": { es: "Permitir siempre", en: "Always allow" },
  "policy.never": { es: "Nunca", en: "Never" },
  "policy.capped": {
    es: "El techo de tu partner manda: se aplica «{effective}». Se cambia en la consola, en Equipo.",
    en: "Your partner's ceiling wins: “{effective}” applies. It changes in the console, under Team.",
  },
  "env.openConsole": { es: "Abrir la consola", en: "Open the console" },
  "session.stop.anonymous": { es: "Sin sesión. Entra en la consola para ver tu equipo.", en: "No session. Sign in to the console to see your team." },
  "session.stop.no_membership": { es: "Tu cuenta no pertenece a ningún partner. Esta aplicación es para partners de Auphere.", en: "Your account belongs to no partner. This app is for Auphere partners." },
  "session.open": { es: "Ir a la consola", en: "Go to the console" },
  "session.pair": { es: "Tu máquina no está emparejada: los teammates trabajan igual, pero no pueden tocar tus archivos hasta que la emparejes. Se empareja desde el pie de la lista lateral.", en: "Your machine is not paired: teammates still work, but cannot touch your files until you pair it. You pair it from the bottom of the sidebar." },
  // ── entrar (US4, R7.1-7.4). Cierra `009-T029`. ────────────────────────
  "signin.title": { es: "Entra en tu cuenta de Auphere", en: "Sign in to your Auphere account" },
  "signin.idle": { es: "Se abrirá tu navegador para que entres. Vuelve aquí cuando termines: la aplicación se entera sola.", en: "Your browser will open so you can sign in. Come back here when you are done: the app notices on its own." },
  "signin.start": { es: "Entrar", en: "Sign in" },
  "signin.esperando": { es: "Esperando a que termines en el navegador.", en: "Waiting for you to finish in the browser." },
  "signin.reopen": { es: "Abrir de nuevo", en: "Open again" },
  "signin.copy": { es: "Copiar el enlace", en: "Copy the link" },
  "signin.copied": { es: "Copiado", en: "Copied" },
  "signin.cancel": { es: "Cancelar", en: "Cancel" },
  "signin.retry": { es: "Volver a intentarlo", en: "Try again" },
  "signin.vuelto": { es: "Listo: ya estás dentro.", en: "Done: you are in." },
  "signin.cancelada": { es: "Se canceló en el navegador. No se ha entrado con ninguna cuenta.", en: "It was cancelled in the browser. No account was signed in." },
  "signin.caducada": { es: "Pasó demasiado tiempo y la espera se cerró. No se ha entrado con ninguna cuenta.", en: "Too much time passed and the wait closed. No account was signed in." },
  "signin.error": { es: "No se pudo completar la entrada. Tu cuenta no ha cambiado.", en: "Sign-in could not be completed. Your account is unchanged." },
  // ── sin partner (US4, R7.5): dos salidas y ningún bucle ───────────────
  "nopartner.title": { es: "Tu cuenta no pertenece a ningún partner", en: "Your account belongs to no partner" },
  "nopartner.body": { es: "Auphere se usa dentro de un partner. Si te han invitado, el correo trae un enlace; si no, entra con la cuenta con la que te invitaron.", en: "Auphere is used inside a partner. If you were invited, the email has a link; if not, sign in with the account you were invited with." },
  "nopartner.invite.label": { es: "Enlace de la invitación", en: "Invitation link" },
  "nopartner.invite.placeholder": { es: "Pega aquí el enlace del correo", en: "Paste the link from the email here" },
  "nopartner.invite": { es: "Abrir la invitación", en: "Open the invitation" },
  "nopartner.invite.invalid": { es: "Eso no parece una invitación. Copia el enlace entero del correo.", en: "That does not look like an invitation. Copy the whole link from the email." },
  "nopartner.other": { es: "Entrar con otra cuenta", en: "Sign in with another account" },
  // ── puesta en marcha (US4, R7.6 y 7.7) ────────────────────────────────
  "setup.title": { es: "Puesta en marcha", en: "Getting set up" },
  "setup.body": { es: "Nada de esto te bloquea: puedes trabajar con pasos a medias. Está aquí para saber qué falta.", en: "None of this blocks you: you can work with steps half done. It is here so you know what is missing." },
  "setup.done": { es: "Todo listo. Esta lista deja de hacer falta.", en: "All set. This list is no longer needed." },
  "setup.go": { es: "Ir", en: "Go" },
  "setup.unblock": { es: "Desbloquear", en: "Unblock" },
  "setup.step.cuenta_lista": { es: "Entrar con tu cuenta de partner", en: "Sign in with your partner account" },
  "setup.step.maquina_emparejada": { es: "Emparejar esta máquina", en: "Pair this machine" },
  "setup.step.ejecutor_presente": { es: "Dejar la aplicación abierta para que tu máquina responda", en: "Keep the app open so your machine answers" },
  "setup.step.primer_teammate": { es: "Crear tu primer teammate", en: "Create your first teammate" },
  "setup.step.primer_turno": { es: "Pedirle algo y ver cómo lo hace", en: "Ask it for something and watch it work" },
  "setup.step.avisos_concedidos": { es: "Permitir los avisos, para enterarte de lo que espera tu decisión", en: "Allow notifications, so you hear about what waits on your decision" },
  "setup.state.hecho": { es: "hecho", en: "done" },
  "setup.state.pendiente": { es: "pendiente", en: "pending" },
  "setup.state.no_aplica": { es: "todavía no aplica", en: "not applicable yet" },
  "setup.blocked.plan": { es: "Tu plan no incluye teammates todavía. Se cambia en Cuenta.", en: "Your plan does not include teammates yet. You change it in Account." },
  // ── emparejar (US4, R8.2 y 8.3). Sustituye a la hoja de la barra ──────
  "pair.title": { es: "Emparejar esta máquina", en: "Pair this machine" },
  "pair.body": { es: "El código se pide en la consola, en Puesto de trabajo, y vale una sola vez. Tecléalo aquí sin salir.", en: "You ask for the code in the console, under Workstation, and it works once. Type it here without leaving." },
  "pair.ask": { es: "Pedir el código en la consola", en: "Ask for the code in the console" },
  "pair.code": { es: "Código de emparejamiento", en: "Pairing code" },
  "pair.submit": { es: "Emparejar", en: "Pair" },
  "pair.cancel": { es: "Cancelar", en: "Cancel" },
  "pair.error.pairing_code_invalid": { es: "Ese código ya no vale. Pide otro en la consola: cada uno sirve una sola vez.", en: "That code is no longer valid. Ask for another in the console: each one works once." },
  "pair.error.pairing_rate_limited": { es: "Demasiados intentos seguidos. Espera un minuto y vuelve a probar.", en: "Too many attempts in a row. Wait a minute and try again." },
  "pair.error.pairing_unavailable": { es: "No se pudo emparejar ahora mismo. Tu máquina sigue como estaba.", en: "Could not pair right now. Your machine is unchanged." },
  // ── directorios (US4, R8.4): cada motivo, su frase ────────────────────
  "dirs.title": { es: "Dónde trabaja cada cliente", en: "Where each client works" },
  "dirs.body": { es: "Un teammate sólo toca el directorio que declares para su cliente. Lo eliges tú, en esta máquina, y no sale de aquí.", en: "A teammate only touches the directory you declare for its client. You pick it, on this machine, and it does not leave here." },
  "dirs.none": { es: "sin declarar", en: "not declared" },
  "dirs.choose": { es: "Elegir carpeta", en: "Choose folder" },
  "dirs.change": { es: "Cambiar", en: "Change" },
  "dirs.close": { es: "Cerrar", en: "Close" },
  "dirs.invalid.exists": { es: "Esa carpeta ya no está donde la elegiste. Vuelve a elegirla.", en: "That folder is no longer where you picked it. Choose it again." },
  "dirs.invalid.is_dir": { es: "Eso es un archivo, no una carpeta. Elige la carpeta que lo contiene.", en: "That is a file, not a folder. Pick the folder that contains it." },
  "dirs.invalid.resolves_within": { es: "Esa carpeta es un enlace que apunta a otro sitio. Elige la carpeta de verdad.", en: "That folder is a link pointing somewhere else. Pick the real folder." },
  "dirs.invalid.readable": { es: "No se puede leer esa carpeta con tu usuario. Revisa sus permisos o elige otra.", en: "That folder cannot be read with your user. Check its permissions or pick another." },
  "dirs.invalid.unknown": { es: "Esa carpeta no vale y el motivo no llegó. Prueba con otra.", en: "That folder does not work and the reason did not arrive. Try another." },
  // ── desemparejar (US4, R8.5) ──────────────────────────────────────────
  "unpair.title": { es: "Desemparejar esta máquina", en: "Unpair this machine" },
  "unpair.loses": { es: "Esta máquina olvidará su credencial: tus teammates dejarán de poder leer y ejecutar aquí hasta que la vuelvas a emparejar.", en: "This machine will forget its credential: your teammates will stop being able to read and run here until you pair it again." },
  "unpair.keeps": { es: "Todo lo demás sigue: los hilos, las tareas y lo que ya hicieron viven en el servidor y no se tocan.", en: "Everything else stays: threads, tasks and what was already done live on the server and are untouched." },
  "unpair.cancel": { es: "Cancelar", en: "Cancel" },
  "unpair.confirm": { es: "Desemparejar", en: "Unpair" },
  // ── plan, cobro y saldo (US5, R9) ─────────────────────────────────────
  "plan.title": { es: "Tu plan", en: "Your plan" },
  "plan.current": { es: "{name} · {teammates} de {max} teammates.", en: "{name} · {teammates} of {max} teammates." },
  "plan.pool": { es: "Llevas gastado el {percent} % de lo que incluye tu plan esta semana. Se reinicia el {date}.", en: "You have used {percent}% of what your plan includes this week. It resets on {date}." },
  "plan.near": { es: "Vas por el {percent} %. Cuando se acabe, el trabajo se pausa hasta el {date} o hasta que compres saldo; los hilos y lo pendiente no se pierden.", en: "You are at {percent}%. When it runs out, work pauses until {date} or until you buy credit; threads and pending items are not lost." },
  "plan.credit": { es: "Tienes saldo comprado, válido hasta el {date}. Se usa cuando lo del plan se agota.", en: "You have purchased credit, valid until {date}. It is used when the plan's allowance runs out." },
  "plan.degraded": { es: "Hay un cobro pendiente. Mientras siga así, el servicio puede degradarse: mejor resolverlo antes de que se note en el trabajo.", en: "There is a payment outstanding. While it stays that way the service may degrade: better to resolve it before it shows up in the work." },
  "plan.change": { es: "Ver planes", en: "See plans" },
  "plan.action.plan_lleno": { es: "Cambiar de plan", en: "Change plan" },
  "plan.action.cobro_fallido": { es: "Resolver el cobro", en: "Resolve the payment" },
  "plan.action.sin_plan": { es: "Elegir un plan", en: "Choose a plan" },
  "plan.action.pool_agotado": { es: "Comprar saldo", en: "Buy credit" },
  "plan.ask.billing": { es: "Esto lo resuelve quien lleva la facturación de tu partner. Pídeselo: tú no necesitas permiso para nada más.", en: "Whoever handles your partner's billing resolves this. Ask them: you need no permission for anything else." },
  "plan.ask.owner": { es: "Esto lo resuelve la persona propietaria del partner.", en: "The partner's owner resolves this." },
  // Los topes, dichos donde se topan (R9.1, R9.3)
  "cap.sin_plan": { es: "Tu plan no incluye teammates. Elige uno que sí, y vuelve aquí.", en: "Your plan includes no teammates. Pick one that does, and come back here." },
  "cap.plan_lleno": { es: "Tu plan está lleno. Cambia de plan o archiva uno que ya no uses.", en: "Your plan is full. Change plan or archive one you no longer use." },
  "cap.pool_agotado": { es: "Se agotó lo que incluye tu plan esta semana.", en: "What your plan includes this week has run out." },
  "cap.cobro_fallido": { es: "Hay un cobro pendiente de resolver.", en: "There is a payment to resolve." },
  "cap.version_no_admitida": { es: "Esta versión ya no se admite.", en: "This version is no longer supported." },
  "cap.sin_plan.ask": { es: "Tu plan no incluye teammates. Quien lleva la facturación de tu partner puede cambiarlo.", en: "Your plan includes no teammates. Whoever handles your partner's billing can change it." },
  "cap.plan_lleno.ask": { es: "Tu plan está lleno. Quien lleva la facturación puede subirlo; tú puedes archivar uno que ya no uses.", en: "Your plan is full. Whoever handles billing can raise it; you can archive one you no longer use." },
  "cap.pool_agotado.ask": { es: "Se agotó lo de esta semana. Quien lleva la facturación puede comprar saldo.", en: "This week's allowance ran out. Whoever handles billing can buy credit." },
  "cap.cobro_fallido.ask": { es: "Hay un cobro pendiente. Quien lleva la facturación de tu partner puede resolverlo.", en: "There is an outstanding payment. Whoever handles your partner's billing can resolve it." },
  // ── traspaso al navegador (US5, R9.4) ─────────────────────────────────
  "handoff.payment": { es: "El pago se abrió en tu navegador. Vuelve aquí cuando termines: el plan y el consumo se releen solos.", en: "Payment opened in your browser. Come back here when you are done: plan and usage are re-read on their own." },
  "handoff.sign_in": { es: "Se abrió tu navegador para entrar. Vuelve aquí cuando termines.", en: "Your browser opened so you can sign in. Come back here when you are done." },
  "handoff.reopen": { es: "Abrir de nuevo", en: "Open again" },
  "handoff.cancel": { es: "Cancelar la espera", en: "Stop waiting" },
  // ── reanudar lo pausado (US5, R9.11) ──────────────────────────────────
  "resume.ready": { es: "{count} trabajo(s) quedaron en pausa por consumo. Ya hay de nuevo: sigue donde se quedó, sin empezar otra vez.", en: "{count} piece(s) of work were paused by usage. There is allowance again: it continues where it left off, without starting over." },
  "resume.capped": { es: "{count} trabajo(s) quedaron en pausa por consumo. Siguen esperando: con saldo comprado continúan donde se quedaron.", en: "{count} piece(s) of work were paused by usage. They are still waiting: with purchased credit they continue where they left off." },
  "resume.action": { es: "Reanudar", en: "Resume" },
} as const;

export type AppKey = keyof typeof COPY;

export function format(lang: Lang, key: AppKey, vars?: Record<string, string | number>): string {
  const entry = COPY[key];
  if (!entry) {
    /*
     * Una clave que no existe es un defecto, y aquí **no se calla**: se
     * registra. Lo que no puede hacer es lanzar. `COPY[key][lang]` sobre un
     * `undefined` tiraba el render, y sin red de seguridad eso es la ventana
     * en negro — pasó con `t(\`pair.error.${code}\`)` y un código que la tabla
     * no tenía. El tipo `AppKey` impide el error en el 99 % de los sitios; el
     * 1 % son las claves que se arman en tiempo de ejecución, que es
     * exactamente donde nadie mira.
     */
    console.error(`[i18n] falta la clave «${key}»`);
    return String(key);
  }
  let out: string = entry[lang];
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
  return out;
}

const LangContext = React.createContext<Lang>("es");
export const LangProvider = LangContext.Provider;

export function useLang(): Lang {
  return React.useContext(LangContext);
}

export function useAppT() {
  const lang = useLang();
  return React.useCallback((key: AppKey, vars?: Record<string, string | number>) => format(lang, key, vars), [lang]);
}

export function systemLang(): Lang {
  return (navigator.language || "es").toLowerCase().startsWith("en") ? "en" : "es";
}
