/** ES/EN del lane `workstation` (spec 001, superficie 3a). Se difunde en `i18n/messages.ts`. */
export const workstationMessages = {
  "clients.tabs.workstation": { es: "Puesto de trabajo", en: "Workstation" },

  // Aquí vivían `workstation.title` y `workstation.description`, que la spec 002
  // sustituyó por `ws.title` y `ws.description` sin llevárselas. Nadie las
  // pedía desde entonces.

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
    es: "El teammate solo puede ejecutar cuando una máquina vinculada a este cliente está conectada. Abre la aplicación de escritorio en la tuya y vincúlala desde Puesto de trabajo.",
    en: "The teammate can only run things when a machine linked to this client is connected. Open the desktop app on yours and link it from Workstation.",
  },
  "workstation.devices.unavailable": {
    es: "No se pudieron cargar las máquinas. La lista de ejecutables de arriba sí es correcta.",
    en: "Machines could not be loaded. The list of executables above is still correct.",
  },
  "workstation.devices.present": { es: "Conectada", en: "Connected" },
  // `absent` a secas no la pide nadie: donde se pinta una ausencia siempre se
  // sabe desde cuándo, y si no se sabe se usa `never`. Decir «desconectada» sin
  // más sería la única forma de que esta pantalla supiera menos de lo que sabe.
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
  "ws.machines.empty.title": { es: "Ninguna máquina registrada", en: "No machine registered" },
  // Spec 012 R6.1 — la consola ya no tiene nada que pulsar aquí: la máquina se
  // registra sola al abrir la aplicación de escritorio con la sesión puesta.
  // El siguiente paso existe, pero no vive en esta pantalla, así que se dice
  // dónde está en vez de pintar un botón que no llevaría a ninguna parte.
  "ws.machines.empty.body": {
    es: "Abre la aplicación de escritorio en la máquina que quieras usar: se registra sola con tu sesión y aparecerá aquí.",
    en: "Open the desktop app on the machine you want to use: it registers itself with your session and will show up here.",
  },
  "ws.machines.empty.readonly": {
    es: "Nadie de tu equipo ha registrado una máquina todavía.",
    en: "Nobody on your team has registered a machine yet.",
  },
  "ws.machines.unavailable": {
    es: "No se pudieron cargar las máquinas. El resto de la página sí es correcto.",
    en: "Machines could not be loaded. The rest of the page is still correct.",
  },
  "ws.machines.owner": { es: "de {name}", en: "{name}'s" },
  "ws.machines.mine": { es: "tuya", en: "yours" },
  "ws.machines.hostname": { es: "Nombre de sistema", en: "System name" },
  "ws.machines.clients.none": { es: "No sirve a ningún cliente todavía", en: "Serves no client yet" },
  // `ws.machines.clients.needsDir` decía «falta el directorio» y la pantalla usa
  // `ws.clients.dirPending` —«pendiente de declarar desde la máquina»—, que dice
  // además dónde se declara. Dos frases para el mismo estado, y la peor sin
  // dueño desde hacía tiempo.
  "ws.machines.rename": { es: "Renombrar", en: "Rename" },
  "ws.machines.renameTitle": { es: "Nombre de la máquina", en: "Machine name" },
  "ws.machines.renameField": { es: "Cómo se llama esta máquina", en: "What this machine is called" },
  "ws.machines.renamed": { es: "Máquina renombrada.", en: "Machine renamed." },
  "ws.machines.archive": { es: "Archivar", en: "Archive" },
  "ws.machines.archiveTitle": { es: "¿Archivar {name}?", en: "Archive {name}?" },
  "ws.machines.archiveBody": {
    es: "La aplicación dejará de latir en menos de un minuto y esta máquina no vuelve: al abrir la aplicación otra vez, se registra una nueva. Lo ya ejecutado sigue en la auditoría — esto archiva, no borra.",
    en: "The app will stop within a minute and this machine does not come back: opening the app again registers a new one. What already ran stays in the audit trail — this archives, it does not delete.",
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
    es: "Después, elige la carpeta de este cliente en la aplicación de escritorio: la consola no teclea rutas.",
    en: "Then choose this client's folder in the desktop app: the console does not type paths.",
  },
  "ws.clients.added": { es: "{name} vinculado. Falta el directorio: elígelo en la aplicación de escritorio.", en: "{name} linked. Directory missing: choose it in the desktop app." },
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

  "ws.setup.title": { es: "Tu puesto de trabajo", en: "Your workstation" },
  "ws.setup.progress": { es: "{done} de {total} pasos", en: "{done} of {total} steps" },
  "ws.setup.dismiss": { es: "Cerrar por ahora", en: "Close for now" },
  // La clave `paired` la nombra la API (`SetupStepKey`); el paso que describe
  // ya no es teclear nada, es abrir la aplicación. El nombre técnico se queda
  // donde está y el texto dice lo que de verdad hay que hacer.
  "ws.setup.step.paired": { es: "Abre la aplicación de escritorio en esta máquina", en: "Open the desktop app on this machine" },
  "ws.setup.step.clients": { es: "Elige a qué clientes sirve", en: "Choose which clients it serves" },
  "ws.setup.step.directories": { es: "Declara el directorio de cada cliente en la aplicación de escritorio", en: "Declare each client's directory in the desktop app" },
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
