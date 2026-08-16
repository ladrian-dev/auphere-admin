/** ES/EN messages of lane `playground` (CP-16). Spread into `i18n/messages.ts`. */
export const playgroundMessages = {
  "clients.tabs.playground": { es: "Playground", en: "Playground" },
  "playground.title": { es: "Playground", en: "Playground" },
  "playground.error": { es: "No se pudo cargar el playground", en: "Could not load the playground" },
  "playground.description": {
    es: "Prueba el agente de este cliente como si fueras un cliente final. Cada turno muestra las herramientas invocadas, los tokens y la latencia. Los efectos secundarios (reservas, envíos, pagos) se bloquean y se registran: aquí nunca pasa nada real.",
    en: "Try this client's agent as an end customer would. Every turn shows the tools invoked, the tokens and the latency. Side effects (bookings, sends, payments) are blocked and logged: nothing real ever happens here.",
  },
  "playground.dryRun": { es: "Modo seguro · sin efectos reales", en: "Safe mode · no real side effects" },
  "playground.noAgent": {
    es: "Este cliente todavía no tiene un agente publicado. Publica una versión en la pestaña Agente para poder probarlo.",
    en: "This client has no published agent yet. Publish a version in the Agent tab to try it.",
  },
  "playground.noAgent.cta": { es: "Ir al agente", en: "Go to the agent" },

  // threads
  "playground.threads": { es: "Conversaciones de prueba", en: "Test threads" },
  "playground.threads.new": { es: "Nueva conversación", en: "New thread" },
  "playground.threads.empty": { es: "Aún no has probado este agente", en: "You have not tried this agent yet" },
  "playground.threads.empty.body": {
    es: "Crea una conversación de prueba y escribe como lo haría un cliente. Solo tú ves tus conversaciones.",
    en: "Create a test thread and write as a customer would. Only you can see your threads.",
  },
  "playground.threads.untitled": { es: "Sin título", en: "Untitled" },
  "playground.threads.turns": { es: "{n} turnos", en: "{n} turns" },
  "playground.threads.turn": { es: "1 turno", en: "1 turn" },
  "playground.threads.rename": { es: "Renombrar", en: "Rename" },
  "playground.threads.archive": { es: "Archivar", en: "Archive" },
  "playground.threads.archived": { es: "Conversación archivada", en: "Thread archived" },
  "playground.threads.created": { es: "Conversación creada", en: "Thread created" },
  "playground.threads.title.label": { es: "Título de la conversación", en: "Thread title" },
  "playground.threads.select": { es: "Elige una conversación o crea una nueva", en: "Pick a thread or create a new one" },

  // composer
  "playground.composer.label": { es: "Mensaje de prueba", en: "Test message" },
  "playground.composer.placeholder": {
    es: "Escribe como lo haría un cliente… (Enter envía, Shift+Enter salto de línea)",
    en: "Write as a customer would… (Enter sends, Shift+Enter for a new line)",
  },
  "playground.composer.send": { es: "Enviar", en: "Send" },
  "playground.composer.stop": { es: "Detener", en: "Stop" },
  "playground.composer.tooLong": { es: "Máximo 4000 caracteres", en: "4000 characters maximum" },
  "playground.composer.disabledCap": {
    es: "Entrada deshabilitada: se alcanzó el tope mensual del playground.",
    en: "Input disabled: the monthly playground cap was reached.",
  },

  // transcript
  "playground.you": { es: "Tú", en: "You" },
  "playground.agent": { es: "Agente", en: "Agent" },
  "playground.thinking": { es: "El agente está respondiendo…", en: "The agent is answering…" },
  "playground.transcript.empty": {
    es: "Esta conversación empieza aquí. El historial vive en tu navegador durante la sesión.",
    en: "This thread starts here. The transcript lives in your browser for the session.",
  },
  "playground.transcript.live": { es: "Transcripción en directo", en: "Live transcript" },
  "playground.run.cancelled": { es: "Turno detenido", en: "Turn stopped" },
  "playground.run.error": { es: "El turno falló", en: "The turn failed" },
  "playground.run.gap": {
    es: "Se perdió parte del stream al reconectar. Envía otro mensaje para continuar.",
    en: "Part of the stream was lost while reconnecting. Send another message to continue.",
  },
  "playground.run.retry": { es: "Reintentar", en: "Retry" },
  "playground.run.reconnecting": { es: "Reconectando…", en: "Reconnecting…" },

  // turn inspector
  "playground.inspector": { es: "Detalle del turno", en: "Turn details" },
  "playground.inspector.empty": { es: "Envía un mensaje para ver herramientas, tokens y latencia.", en: "Send a message to see tools, tokens and latency." },
  "playground.inspector.tools": { es: "Herramientas invocadas", en: "Tools invoked" },
  "playground.inspector.tools.none": { es: "Ninguna herramienta en este turno", en: "No tools in this turn" },
  "playground.inspector.tool.blocked": { es: "Bloqueada (modo seguro)", en: "Blocked (safe mode)" },
  "playground.inspector.tool.running": { es: "En curso", en: "Running" },
  "playground.inspector.tool.done": { es: "Completada", en: "Completed" },
  "playground.inspector.tokensIn": { es: "Tokens de entrada", en: "Input tokens" },
  "playground.inspector.tokensOut": { es: "Tokens de salida", en: "Output tokens" },
  "playground.inspector.latency": { es: "Latencia", en: "Latency" },
  "playground.inspector.model": { es: "Modelo", en: "Model" },
  "playground.inspector.pending": { es: "—", en: "—" },
  "playground.inspector.status": { es: "Estado", en: "Status" },
  "playground.inspector.status.running": { es: "En curso", en: "Running" },
  "playground.inspector.status.completed": { es: "Completado", en: "Completed" },
  "playground.inspector.status.cancelled": { es: "Detenido", en: "Stopped" },
  "playground.inspector.status.error": { es: "Error", en: "Error" },

  // budget
  "playground.budget": { es: "Tope mensual del playground", en: "Monthly playground cap" },
  "playground.budget.usage": { es: "{used} de {cap} tokens ({percent}%)", en: "{used} of {cap} tokens ({percent}%)" },
  "playground.budget.resets": { es: "Se reinicia el {date}", en: "Resets on {date}" },
  "playground.budget.hint": {
    es: "Suma los tokens de entrada y salida de todas tus pruebas (todos los clientes, todo el equipo) en el mes en curso. No entra en el consumo facturable de tus clientes.",
    en: "Input plus output tokens of all your tests (every client, whole team) in the current month. It never counts towards your clients' billable usage.",
  },
  "playground.budget.reached": { es: "Tope alcanzado", en: "Cap reached" },
  "playground.budget.reached.body": {
    es: "Has consumido los {cap} tokens del playground de este mes. El playground se reactiva el {date}. Si necesitas más, escríbenos y ampliamos el tope.",
    en: "You have used this month's {cap} playground tokens. The playground reopens on {date}. Need more? Contact us and we will raise the cap.",
  },
  "playground.budget.near": { es: "Queda poco margen: {remaining} tokens", en: "Running low: {remaining} tokens left" },
  "playground.budget.error": { es: "No se pudo cargar el tope", en: "Could not load the cap" },
} as const;
