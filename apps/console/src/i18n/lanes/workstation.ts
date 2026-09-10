/** ES/EN del lane `workstation` (spec 001, superficie 3a). Se difunde en `i18n/messages.ts`. */
export const workstationMessages = {
  "clients.tabs.workstation": { es: "Puesto de trabajo", en: "Workstation" },

  "workstation.title": { es: "Puesto de trabajo", en: "Workstation" },
  "workstation.description": {
    es: "Qué puede ejecutar el teammate en la máquina de este cliente, y en qué máquina.",
    en: "What the teammate may run on this client's machine, and on which machine.",
  },

  // ── lista blanca ───────────────────────────────────────────────────
  "workstation.allowlist.title": { es: "Ejecutables permitidos", en: "Allowed executables" },
  "workstation.allowlist.help": {
    es: "Un ejecutable que no esté en esta lista no se ejecuta, y no se puede aprobar durante una conversación: se añade aquí, a propósito. Lo que sí se aprueba en el momento son argumentos nuevos de un ejecutable ya permitido.",
    en: "An executable that is not on this list does not run, and cannot be approved mid-conversation: it is added here, deliberately. What is approved in the moment are new arguments for an already-allowed executable.",
  },
  "workstation.allowlist.empty.title": { es: "La lista está vacía", en: "The list is empty" },
  "workstation.allowlist.empty.body": {
    es: "No hay nada permitido todavía, así que el teammate no puede ejecutar nada en esta máquina. Empieza por lo que ya usáis a mano: el comando de build, el de tests.",
    en: "Nothing is allowed yet, so the teammate cannot run anything on this machine. Start with what you already run by hand: the build command, the test command.",
  },
  "workstation.allowlist.add": { es: "Añadir ejecutable", en: "Add executable" },
  "workstation.allowlist.addTitle": { es: "Añadir un ejecutable", en: "Add an executable" },
  "workstation.allowlist.addBody": {
    es: "Solo el nombre del programa — sin rutas, sin argumentos y sin símbolos de shell. Los argumentos se aprueban después, uno a uno.",
    en: "The program name only — no paths, no arguments, no shell symbols. Arguments are approved later, one at a time.",
  },
  "workstation.allowlist.field": { es: "Ejecutable", en: "Executable" },
  "workstation.allowlist.invalid": {
    es: "Solo letras, números y . _ + -  · sin barras ni espacios.",
    en: "Letters, digits and . _ + -  only · no slashes, no spaces.",
  },
  "workstation.allowlist.added": { es: "{name} añadido a la lista.", en: "{name} added to the list." },
  "workstation.allowlist.archive": { es: "Quitar de la lista", en: "Remove from list" },
  "workstation.allowlist.archiveTitle": { es: "¿Quitar {name}?", en: "Remove {name}?" },
  "workstation.allowlist.archiveBody": {
    es: "El teammate dejará de poder ejecutarlo. Lo ya ejecutado sigue en la auditoría: esto archiva, no borra.",
    en: "The teammate will no longer be able to run it. What already ran stays in the audit trail: this archives, it does not delete.",
  },
  "workstation.allowlist.archived": { es: "{name} ya no está permitido.", en: "{name} is no longer allowed." },
  "workstation.allowlist.addedBy": { es: "Añadido por {who}", en: "Added by {who}" },

  // ── dispositivos ───────────────────────────────────────────────────
  "workstation.devices.title": { es: "Máquinas", en: "Machines" },
  "workstation.devices.empty.title": { es: "Ninguna máquina dada de alta", en: "No machine enrolled" },
  "workstation.devices.empty.body": {
    es: "El teammate solo puede ejecutar cuando una máquina vinculada a este cliente está conectada. Empareja la tuya y vincúlala desde Puesto de trabajo.",
    en: "The teammate can only run things when a machine linked to this client is connected. Pair yours and link it from Workstation.",
  },
  "workstation.devices.unavailable": {
    es: "No se pudieron cargar las máquinas. La lista de ejecutables de arriba sí es correcta.",
    en: "Machines could not be loaded. The list of executables above is still correct.",
  },
  "workstation.devices.present": { es: "Conectada", en: "Connected" },
  "workstation.devices.absent": { es: "Desconectada", en: "Disconnected" },
  "workstation.devices.absentSince": { es: "Desconectada desde {when}", en: "Disconnected since {when}" },
  "workstation.devices.never": { es: "Nunca se ha conectado", en: "Never connected" },
  "workstation.devices.workdir": { es: "Directorio", en: "Directory" },

  "workstation.error.title": { es: "No se pudo cargar el puesto de trabajo", en: "Could not load the workstation" },
  "workstation.devices.noDirectory": { es: "Sin directorio declarado", en: "No directory declared" },
  "workstation.devices.manageLink": { es: "Gestionar máquinas", en: "Manage machines" },

  // ── spec 002: el puesto a nivel de partner ─────────────────────────
  "ws.title": { es: "Puesto de trabajo", en: "Workstation" },
  "ws.description": {
    es: "Tus máquinas, a qué clientes sirven y en qué directorio. Los ejecutables permitidos se gestionan en cada cliente.",
    en: "Your machines, which clients they serve and in which directory. Allowed executables are managed per client.",
  },
  "ws.machines.title": { es: "Máquinas", en: "Machines" },
  "ws.machines.empty.title": { es: "Ninguna máquina emparejada", en: "No machine paired" },
  "ws.machines.empty.body": {
    es: "Instala la aplicación de escritorio, entra con tu cuenta y pide aquí un código. La barra de la aplicación te lo pedirá.",
    en: "Install the desktop app, sign in with your account and ask for a code here. The app's bar will ask you for it.",
  },
  "ws.machines.empty.readonly": {
    es: "Nadie de tu equipo ha emparejado una máquina todavía.",
    en: "Nobody on your team has paired a machine yet.",
  },
  "ws.machines.unavailable": {
    es: "No se pudieron cargar las máquinas. El resto de la página sí es correcto.",
    en: "Machines could not be loaded. The rest of the page is still correct.",
  },
  "ws.machines.owner": { es: "de {name}", en: "{name}'s" },
  "ws.machines.mine": { es: "tuya", en: "yours" },
  "ws.machines.hostname": { es: "Nombre de sistema", en: "System name" },
  "ws.machines.clients.none": { es: "No sirve a ningún cliente todavía", en: "Serves no client yet" },
  "ws.machines.clients.needsDir": { es: "falta el directorio", en: "directory missing" },
  "ws.machines.rename": { es: "Renombrar", en: "Rename" },
  "ws.machines.renameTitle": { es: "Nombre de la máquina", en: "Machine name" },
  "ws.machines.renameField": { es: "Cómo se llama esta máquina", en: "What this machine is called" },
  "ws.machines.renamed": { es: "Máquina renombrada.", en: "Machine renamed." },
  "ws.machines.archive": { es: "Archivar", en: "Archive" },
  "ws.machines.archiveTitle": { es: "¿Archivar {name}?", en: "Archive {name}?" },
  "ws.machines.archiveBody": {
    es: "La aplicación dejará de latir en menos de un minuto y no se podrá volver a emparejar esta máquina: se empareja otra. Lo ya ejecutado sigue en la auditoría — esto archiva, no borra.",
    en: "The app will stop within a minute and this machine cannot be paired again: you pair a new one. What already ran stays in the audit trail — this archives, it does not delete.",
  },
  "ws.machines.archived": { es: "Máquina archivada.", en: "Machine archived." },
  "ws.machines.archivedSince": { es: "Archivada {when}", en: "Archived {when}" },
  "ws.machines.reason.desemparejada": { es: "desemparejada desde la máquina", en: "unpaired from the machine" },
  "ws.machines.reason.archivada_consola": { es: "archivada desde la consola", en: "archived from the console" },
  "ws.machines.reason.pertenencia_retirada": { es: "su persona dejó el equipo", en: "its person left the team" },
  "ws.machines.showArchived": { es: "Ver archivadas", en: "Show archived" },
  "ws.machines.hideArchived": { es: "Ocultar archivadas", en: "Hide archived" },

  "ws.clients.title": { es: "Clientes a los que sirve", en: "Clients it serves" },
  "ws.clients.add": { es: "Añadir cliente", en: "Add client" },
  "ws.clients.addField": { es: "Cliente", en: "Client" },
  "ws.clients.addHelp": {
    es: "Después, elige la carpeta de este cliente desde la barra de la aplicación: la consola no teclea rutas.",
    en: "Then choose this client's folder from the app's bar: the console does not type paths.",
  },
  "ws.clients.added": { es: "{name} vinculado. Falta el directorio: elígelo desde la barra de la aplicación.", en: "{name} linked. Directory missing: choose it from the app's bar." },
  "ws.clients.remove": { es: "Quitar", en: "Remove" },
  "ws.clients.removeTitle": { es: "¿Quitar {name} de esta máquina?", en: "Remove {name} from this machine?" },
  "ws.clients.removeBody": {
    es: "El teammate de este cliente dejará de tener herramientas locales en esta máquina. Lo ya ejecutado sigue en la auditoría.",
    en: "This client's teammate will no longer have local tools on this machine. What already ran stays in the audit trail.",
  },
  "ws.clients.removed": { es: "{name} ya no está vinculado.", en: "{name} is no longer linked." },
  "ws.clients.allLinked": { es: "Todos tus clientes ya están vinculados a esta máquina.", en: "All your clients are already linked to this machine." },
  "ws.clients.noClients": {
    es: "No tienes clientes todavía. Cuando des de alta el primero, podrás vincularlo aquí.",
    en: "You have no clients yet. When you create the first one, you can link it here.",
  },
  "ws.clients.dirPending": { es: "Pendiente de declarar desde la máquina", en: "Pending declaration from the machine" },

  "ws.pair.button": { es: "Emparejar esta máquina", en: "Pair this machine" },
  "ws.pair.title": { es: "Emparejar esta máquina", en: "Pair this machine" },
  "ws.pair.intro": {
    es: "Teclea este código en la barra de la aplicación de escritorio, en esta misma máquina. Vale una sola vez.",
    en: "Type this code in the desktop app's bar, on this very machine. It is valid once.",
  },
  "ws.pair.expiresIn": { es: "Caduca en {mmss}", en: "Expires in {mmss}" },
  "ws.pair.expired": { es: "El código caducó. Pide otro.", en: "The code expired. Ask for another." },
  "ws.pair.loading": { es: "Generando el código…", en: "Generating the code…" },
  "ws.pair.error": { es: "No se pudo generar el código. Vuelve a intentarlo.", en: "The code could not be generated. Try again." },
  "ws.pair.another": { es: "Pedir otro código", en: "Ask for another code" },
  "ws.pair.done": { es: "Listo", en: "Done" },
  "ws.pair.onceOnly": {
    es: "Al cerrar, el código no se vuelve a mostrar.",
    en: "Once closed, the code is not shown again.",
  },
  "ws.pair.copy": { es: "Copiar código", en: "Copy code" },
  "ws.pair.copied": { es: "Código copiado.", en: "Code copied." },

  "ws.setup.title": { es: "Tu puesto de trabajo", en: "Your workstation" },
  "ws.setup.progress": { es: "{done} de {total} pasos", en: "{done} of {total} steps" },
  "ws.setup.dismiss": { es: "Cerrar por ahora", en: "Close for now" },
  "ws.setup.step.paired": { es: "Empareja esta máquina", en: "Pair this machine" },
  "ws.setup.step.clients": { es: "Elige a qué clientes sirve", en: "Choose which clients it serves" },
  "ws.setup.step.directories": { es: "Declara el directorio de cada cliente desde la barra de la aplicación", en: "Declare each client's directory from the app's bar" },
  "ws.setup.step.executables": { es: "Ejecutables habilitados por Auphere", en: "Executables enabled by Auphere" },
  "ws.setup.pending": { es: "{n} pendiente(s)", en: "{n} pending" },
  "ws.setup.executables.help": {
    es: "Los ejecutables los habilita Auphere por cliente. Si falta alguno, pídelo desde la página del cliente.",
    en: "Executables are enabled by Auphere per client. If one is missing, request it from the client's page.",
  },
  "ws.setup.error": { es: "No se pudo comprobar la puesta en marcha.", en: "The setup could not be checked." },

  "ws.meta.continueInBrowser": {
    es: "Conectar un canal de Meta se hace desde el navegador. Copia este enlace y ábrelo ahí.",
    en: "Connecting a Meta channel is done from the browser. Copy this link and open it there.",
  },
  "ws.meta.copyLink": { es: "Copiar enlace", en: "Copy link" },
  "ws.meta.copied": { es: "Enlace copiado.", en: "Link copied." },
} as const;
