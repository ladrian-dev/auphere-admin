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
    es: "El teammate solo puede ejecutar cuando hay una máquina conectada. Se da de alta desde la aplicación de escritorio.",
    en: "The teammate can only run things when a machine is connected. Enrol one from the desktop app.",
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
} as const;
