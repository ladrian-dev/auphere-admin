/**
 * ES/EN messages of lane `companion` (CO-03). Spread into `i18n/messages.ts`.
 *
 * The division of labour with the backend is a rule, not a habit (§1.4 of
 * `docs/companion/CONTRACT-V1.md`): **the backend emits stable
 * identifiers, this file emits text for humans.**
 *
 * So `phase.changed.label` arrives hardcoded in Spanish and is NOT
 * painted — `phase` is, through `companion.phase.*` below. Same for
 * `verify.result.checks[].name`, `impact[].key` and `intake.slots[].key`:
 * the identifier is the contract, the wording is ours, and an identifier
 * we do not recognise falls back to what the backend sent rather than
 * rendering blank.
 *
 * The three exceptions painted verbatim, because they come from the CO-02
 * tool catalogue or from the model itself: `citation.claim`,
 * `tool.call.started.label` and `plan.proposed.steps[].title`.
 */
export const companionMessages = {
  // ── bubble + drawer chrome ───────────────────────────────────────────
  "companion.title": { es: "Companion", en: "Companion" },
  "companion.open": { es: "Abrir el Companion", en: "Open the Companion" },
  "companion.close": { es: "Cerrar el Companion", en: "Close the Companion" },
  "companion.bubble.busy": { es: "El Companion está trabajando", en: "The Companion is working" },
  "companion.bubble.awaiting": { es: "El Companion espera tu confirmación", en: "The Companion is waiting for your confirmation" },
  "companion.bubble.disabled.role": {
    es: "Tu rol no puede usar el Companion. Pídele a un administrador el rol de constructor.",
    en: "Your role cannot use the Companion. Ask an administrator for the builder role.",
  },
  "companion.bubble.disabled.cap": {
    es: "Se alcanzó el tope mensual de tokens del Companion.",
    en: "The Companion's monthly token cap has been reached.",
  },
  "companion.shortcut": { es: "Atajo: ⌘J", en: "Shortcut: ⌘J" },
  "companion.closeBlocked": {
    es: "Hay una confirmación pendiente. Decide antes de cerrar.",
    en: "There is a pending confirmation. Decide before closing.",
  },
  "companion.resize": { es: "Ancho del cajón", en: "Drawer width" },
  "companion.resize.hint": {
    es: "Arrastra, o usa las flechas izquierda y derecha para ajustar el ancho.",
    en: "Drag, or use the left and right arrow keys to adjust the width.",
  },

  // ── threads ──────────────────────────────────────────────────────────
  "companion.thread.new": { es: "Nueva conversación", en: "New conversation" },
  "companion.thread.untitled": { es: "Sin título", en: "Untitled" },
  "companion.thread.select": { es: "Elegir conversación", en: "Choose a conversation" },
  "companion.thread.archive": { es: "Archivar conversación", en: "Archive conversation" },
  "companion.thread.shared": {
    es: "Enlace copiado. Quien lo abra verá esta conversación si tiene permiso.",
    en: "Link copied. Anyone who opens it sees this conversation if they have permission.",
  },
  "companion.thread.share": { es: "Copiar enlace de la conversación", en: "Copy link to this conversation" },

  // ── phases (§2.8) — the pill. Identifier in, wording here. ───────────
  "companion.phase.understand": { es: "Entendiendo", en: "Understanding" },
  "companion.phase.investigate": { es: "Investigando", en: "Investigating" },
  "companion.phase.intake": { es: "Preguntando", en: "Asking" },
  "companion.phase.plan": { es: "Planificando", en: "Planning" },
  "companion.phase.awaiting": { es: "Esperándote", en: "Waiting for you" },
  "companion.phase.execute": { es: "Ejecutando", en: "Executing" },
  "companion.phase.verify": { es: "Verificando", en: "Verifying" },
  "companion.phase.respond": { es: "Respondiendo", en: "Answering" },
  "companion.phase.done": { es: "Listo", en: "Done" },
  "companion.working": { es: "Trabajando…", en: "Working…" },

  // ── the five Hurff states ────────────────────────────────────────────
  "companion.loading": { es: "Cargando la conversación…", en: "Loading the conversation…" },
  "companion.empty.title": { es: "¿En qué te echo una mano?", en: "What can I help you with?" },
  "companion.empty.body": {
    es: "Pregunta lo que quieras sobre tus clientes, sus agentes o tu consumo. En modo Consultar solo leo; para cambiar algo tendrás que confirmarlo tú.",
    en: "Ask anything about your clients, their agents or your usage. In Consult mode I only read; to change anything you will have to confirm it yourself.",
  },
  "companion.empty.suggestions": { es: "Para empezar", en: "To get started" },
  "companion.error.title": { es: "No se pudo cargar la conversación", en: "Could not load the conversation" },
  "companion.error.network": {
    es: "No hay conexión con la consola. El trabajo del Companion sigue en marcha en el servidor.",
    en: "No connection to the console. The Companion's work carries on server-side.",
  },
  "companion.partial.title": { es: "Falta parte de esta conversación", en: "Part of this conversation is missing" },
  "companion.partial.body": {
    es: "Esta conversación empezó en otro navegador o dispositivo. Se muestra desde aquí en adelante; lo anterior sigue guardado en el servidor.",
    en: "This conversation started in another browser or device. It is shown from here on; what came before is still stored server-side.",
  },
  "companion.reconnecting": { es: "Reconectando…", en: "Reconnecting…" },

  // ── notices ──────────────────────────────────────────────────────────
  "companion.notice.gap": {
    es: "Se perdió un tramo del directo al reconectar. Lo anterior sigue arriba.",
    en: "A stretch of the live feed was lost while reconnecting. What came before is still above.",
  },
  "companion.notice.cancelled": { es: "Turno detenido", en: "Turn stopped" },
  "companion.notice.error": { es: "El turno falló", en: "The turn failed" },
  "companion.notice.interrupted": {
    es: "El turno se cortó por el lado del servidor. Vuelve a preguntar.",
    en: "The turn was cut short server-side. Ask again.",
  },
  "companion.notice.unsupported": {
    es: "No pude responder esto con datos que haya leído, así que prefiero no afirmarlo.",
    en: "I could not answer this from data I actually read, so I would rather not assert it.",
  },

  // ── thinking (§8.2) ──────────────────────────────────────────────────
  "companion.thinking.summary": { es: "Pensó {seconds} s", en: "Thought for {seconds} s" },
  "companion.thinking.summaryWithTools": {
    es: "Pensó {seconds} s · comprobó {n} cosas",
    en: "Thought for {seconds} s · checked {n} things",
  },
  "companion.thinking.summaryOneTool": {
    es: "Pensó {seconds} s · comprobó 1 cosa",
    en: "Thought for {seconds} s · checked 1 thing",
  },
  "companion.thinking.live": { es: "Pensando…", en: "Thinking…" },
  "companion.thinking.expand": { es: "Ver el razonamiento", en: "Show the reasoning" },
  "companion.thinking.note": {
    es: "El razonamiento no se guarda: desaparece al recargar.",
    en: "Reasoning is not stored: it disappears on reload.",
  },

  // ── tool cards (§8.3) ────────────────────────────────────────────────
  "companion.tool.running": { es: "En curso", en: "Running" },
  "companion.tool.ok": { es: "Hecho", en: "Done" },
  "companion.tool.failed": { es: "Falló", en: "Failed" },
  "companion.tool.raw": { es: "Ver petición y respuesta", en: "Show request and response" },
  "companion.tool.args": { es: "Petición", en: "Request" },
  "companion.tool.result": { es: "Respuesta", en: "Response" },
  "companion.tool.noResult": {
    es: "La respuesta no viaja por el directo: va al contexto del modelo, no al navegador.",
    en: "The response does not travel over the live feed: it goes to the model's context, not to the browser.",
  },
  "companion.tool.source": { es: "Fuente", en: "Source" },
  "companion.tool.fetchedAt": { es: "Leído el {date}", en: "Read on {date}" },

  // Human names for the 18 read tools of CO-02. The backend also sends a
  // `label`; this table is what we paint when it is absent.
  "companion.tool.name.console.whoami": { es: "Comprobando quién eres", en: "Checking who you are" },
  "companion.tool.name.console.list_clients": { es: "Listando tus clientes", en: "Listing your clients" },
  "companion.tool.name.console.get_client": { es: "Leyendo la ficha del cliente", en: "Reading the client record" },
  "companion.tool.name.console.get_agent": { es: "Leyendo el agente", en: "Reading the agent" },
  "companion.tool.name.console.get_policy": { es: "Leyendo la política", en: "Reading the policy" },
  "companion.tool.name.console.list_tools": { es: "Listando las herramientas activas", en: "Listing the active tools" },
  "companion.tool.name.console.list_skills": { es: "Listando las skills", en: "Listing the skills" },
  "companion.tool.name.console.list_knowledge": { es: "Listando el conocimiento", en: "Listing the knowledge base" },
  "companion.tool.name.console.list_channels": { es: "Listando los canales", en: "Listing the channels" },
  "companion.tool.name.console.channel_diagnostics": { es: "Diagnosticando el canal", en: "Diagnosing the channel" },
  "companion.tool.name.console.list_templates": { es: "Listando las plantillas", en: "Listing the templates" },
  "companion.tool.name.console.get_usage": { es: "Consultando el consumo", en: "Checking the usage" },
  "companion.tool.name.console.usage_series": { es: "Consultando la serie de consumo", en: "Checking the usage series" },
  "companion.tool.name.console.conversation_stats": { es: "Consultando las conversaciones", en: "Checking the conversations" },
  "companion.tool.name.console.get_audit": { es: "Revisando la auditoría", en: "Reviewing the audit trail" },
  "companion.tool.name.console.get_onboarding": { es: "Revisando la puesta en marcha", en: "Reviewing the onboarding" },
  "companion.tool.name.console.get_quota": { es: "Consultando tu cupo", en: "Checking your quota" },
  "companion.tool.name.console.get_prompt_library": { es: "Consultando la biblioteca de prompts", en: "Checking the prompt library" },
  "companion.tool.name.console.apply": { es: "Aplicando el cambio confirmado", en: "Applying the confirmed change" },

  // ── plan card (§2.1) ─────────────────────────────────────────────────
  "companion.plan.title": { es: "Plan propuesto", en: "Proposed plan" },
  "companion.plan.note": {
    es: "Todavía no ha pasado nada. Cada paso que escriba te lo pediré por separado.",
    en: "Nothing has happened yet. I will ask you separately for every step that writes.",
  },
  "companion.plan.steps": { es: "{n} pasos", en: "{n} steps" },
  "companion.plan.step": { es: "1 paso", en: "1 step" },
  "companion.plan.risk": { es: "Riesgo", en: "Risk" },
  "companion.plan.risk.low": { es: "bajo", en: "low" },
  "companion.plan.risk.medium": { es: "medio", en: "medium" },
  "companion.plan.risk.high": { es: "alto", en: "high" },
  "companion.plan.reversible": { es: "Reversible", en: "Reversible" },
  "companion.plan.irreversible": { es: "No reversible", en: "Not reversible" },
  "companion.plan.tokens": { es: "≈{n} tokens", en: "≈{n} tokens" },
  "companion.plan.forClient": { es: "cliente {ref}", en: "client {ref}" },

  // ── intake card (§2.2) ───────────────────────────────────────────────
  "companion.intake.title": { es: "Me falta saber", en: "What I still need" },
  "companion.intake.body": {
    es: "Responde lo que quieras, en el orden que quieras. Puedes escribirlo con tus palabras en el cuadro de abajo.",
    en: "Answer whatever you like, in any order. You can write it in your own words in the box below.",
  },
  "companion.intake.required": { es: "imprescindible", en: "required" },
  "companion.intake.optional": { es: "opcional", en: "optional" },
  "companion.intake.examples": { es: "Por ejemplo", en: "For example" },
  "companion.intake.answer": { es: "Responder «{label}»", en: "Answer “{label}”" },
  // Copy of our own for the stable slot keys we know. Anything else falls
  // back to the backend's `label` / `why`.
  "companion.intake.slot.forbidden_behaviour": { es: "Qué NO debe hacer el agente", en: "What the agent must NOT do" },
  "companion.intake.slot.business_hours": { es: "Horario de atención", en: "Opening hours" },
  "companion.intake.slot.timezone": { es: "Zona horaria", en: "Time zone" },
  "companion.intake.slot.legal_name": { es: "Nombre fiscal", en: "Registered name" },
  "companion.intake.slot.escalation": { es: "Cuándo pasar a una persona", en: "When to hand over to a person" },

  // ── confirmation card (§2.3, §2.4) ───────────────────────────────────
  "companion.confirm.title": { es: "Necesito tu confirmación", en: "I need your confirmation" },
  "companion.confirm.live": { es: "El Companion pide confirmación: {title}", en: "The Companion asks for confirmation: {title}" },
  "companion.confirm.confirm": { es: "Confirmar", en: "Confirm" },
  "companion.confirm.edit": { es: "Cambiar algo", en: "Change something" },
  "companion.confirm.cancel": { es: "Cancelar", en: "Cancel" },
  "companion.confirm.note.label": { es: "Qué quieres cambiar", en: "What you want changed" },
  "companion.confirm.note.placeholder": {
    es: "Ej.: igual pero sin tocar el horario",
    en: "E.g. same but without touching the opening hours",
  },
  "companion.confirm.note.send": { es: "Enviar", en: "Send" },
  "companion.confirm.note.hint": {
    es: "Lo que escribas vuelve al Companion para que ajuste el plan.",
    en: "What you write goes back to the Companion so it can adjust the plan.",
  },
  "companion.confirm.expires": { es: "Caduca en {time}", en: "Expires in {time}" },
  "companion.confirm.expired.title": { es: "Se pasó el plazo", en: "The window closed" },
  "companion.confirm.expired.body": {
    es: "Esta propuesta caducó. Pídemelo otra vez y la vuelvo a preparar con los datos de ahora.",
    en: "This proposal expired. Ask me again and I will prepare it afresh with current data.",
  },
  "companion.confirm.stale.title": { es: "Alguien cambió esto mientras decidías", en: "Someone changed this while you were deciding" },
  "companion.confirm.stale.body": {
    es: "El estado ya no es el que viste. Lo vuelvo a proponer con los datos frescos.",
    en: "The state is no longer the one you saw. I will propose it again with fresh data.",
  },
  "companion.confirm.decided": { es: "Esta propuesta ya se decidió.", en: "This proposal has already been decided." },
  "companion.confirm.failed": { es: "No se pudo registrar tu decisión.", en: "Your decision could not be recorded." },
  "companion.confirm.resolved.confirm": { es: "Confirmado por {by}", en: "Confirmed by {by}" },
  "companion.confirm.resolved.edit": { es: "Devuelto para cambios por {by}", en: "Sent back for changes by {by}" },
  "companion.confirm.resolved.cancel": { es: "Cancelado por {by}", en: "Cancelled by {by}" },
  "companion.confirm.resolved.you": { es: "ti", en: "you" },
  "companion.confirm.diff": { es: "Qué cambia", en: "What changes" },
  "companion.confirm.diff.add": { es: "línea añadida", en: "line added" },
  "companion.confirm.diff.del": { es: "línea eliminada", en: "line removed" },
  "companion.confirm.impact": { es: "A qué afecta", en: "What it affects" },
  "companion.confirm.preview": { es: "Detalle", en: "Detail" },
  "companion.confirm.irreversible": {
    es: "Esto no se puede deshacer.",
    en: "This cannot be undone.",
  },

  // `kind` → human title of the action (§3.1)
  "companion.kind.client": { es: "Crear un cliente", en: "Create a client" },
  "companion.kind.prompt": { es: "Cambiar el prompt", en: "Change the prompt" },
  "companion.kind.policy": { es: "Cambiar la política", en: "Change the policy" },
  "companion.kind.tools": { es: "Cambiar las herramientas", en: "Change the tools" },
  "companion.kind.skills": { es: "Cambiar las skills", en: "Change the skills" },
  "companion.kind.publish": { es: "Publicar una versión", en: "Publish a version" },
  "companion.kind.channel_role": { es: "Cambiar el rol de un canal", en: "Change a channel's role" },
  "companion.kind.usage_alerts": { es: "Cambiar los avisos de consumo", en: "Change the usage alerts" },
  "companion.kind.invite": { es: "Invitar a alguien al equipo", en: "Invite someone to the team" },
  "companion.kind.unknown": { es: "Cambio propuesto", en: "Proposed change" },

  // `preview` fields we know how to name (§3.4)
  "companion.preview.client_ref": { es: "Cliente", en: "Client" },
  "companion.preview.summary": { es: "Resumen", en: "Summary" },
  "companion.preview.from_version": { es: "Versión actual", en: "Current version" },
  "companion.preview.to_version": { es: "Versión nueva", en: "New version" },
  "companion.preview.evals_run": { es: "Se ejecutaron evaluaciones", en: "Evaluations were run" },
  "companion.preview.evals_warning": { es: "Aviso", en: "Warning" },
  "companion.preview.name": { es: "Nombre", en: "Name" },
  "companion.preview.vertical": { es: "Vertical", en: "Vertical" },
  "companion.preview.timezone": { es: "Zona horaria", en: "Time zone" },
  "companion.preview.language": { es: "Idioma", en: "Language" },
  "companion.preview.quota_used": { es: "Clientes usados", en: "Clients used" },
  "companion.preview.quota_max": { es: "Clientes del cupo", en: "Clients in quota" },
  "companion.preview.email_masked": { es: "Correo", en: "Email" },
  "companion.preview.role": { es: "Rol", en: "Role" },
  "companion.preview.yes": { es: "Sí", en: "Yes" },
  "companion.preview.no": { es: "No", en: "No" },

  // `impact[].key` we know; anything else falls back to the raw key.
  "companion.impact.channels_affected": { es: "Canales afectados", en: "Channels affected" },
  "companion.impact.conversations_open": { es: "Conversaciones abiertas", en: "Open conversations" },
  "companion.impact.tools_changed": { es: "Herramientas que cambian", en: "Tools changed" },
  "companion.impact.members_notified": { es: "Miembros avisados", en: "Members notified" },

  // ── verification table (§2.5) ────────────────────────────────────────
  "companion.verify.title": { es: "Lo que comprobé después", en: "What I checked afterwards" },
  "companion.verify.ok": { es: "Todo cuadra", en: "Everything checks out" },
  "companion.verify.failed": { es: "Algo no cuadra", en: "Something does not check out" },
  "companion.verify.failedBody": {
    es: "Volví a leerlo de la plataforma y no coincide con lo que esperaba. No es culpa tuya: o me equivoqué yo, o el cambio no se aplicó del todo.",
    en: "I read it back from the platform and it does not match what I expected. This is not your fault: either I got it wrong, or the change did not fully apply.",
  },
  "companion.verify.check": { es: "Comprobación", en: "Check" },
  "companion.verify.expected": { es: "Esperado", en: "Expected" },
  "companion.verify.actual": { es: "Real", en: "Actual" },
  "companion.verify.check.active_version": { es: "Versión activa", en: "Active version" },
  "companion.verify.check.tools_enabled": { es: "Herramientas activas", en: "Tools enabled" },
  "companion.verify.check.skills_enabled": { es: "Skills activas", en: "Skills enabled" },
  "companion.verify.check.client_status": { es: "Estado del cliente", en: "Client status" },
  "companion.verify.check.channel_role": { es: "Rol del canal", en: "Channel role" },
  "companion.verify.check.draft_saved": { es: "Borrador guardado", en: "Draft saved" },

  // ── meters (§12) ─────────────────────────────────────────────────────
  "companion.meter.context": { es: "Contexto", en: "Context" },
  "companion.meter.context.detail": {
    es: "{used} de {max} tokens de la ventana del modelo ({percent}%)",
    en: "{used} of {max} tokens of the model's window ({percent}%)",
  },
  "companion.meter.turn": { es: "Turno", en: "Turn" },
  "companion.meter.turn.detail": { es: "{input} de entrada · {output} de salida", en: "{input} in · {output} out" },
  "companion.meter.month": { es: "Mes", en: "Month" },
  "companion.meter.month.detail": {
    es: "{used} de {cap} tokens del tope mensual del Companion ({percent}%)",
    en: "{used} of {cap} tokens of the Companion's monthly cap ({percent}%)",
  },
  "companion.meter.month.resets": { es: "Se reinicia el {date}", en: "Resets on {date}" },
  "companion.meter.exhausted": { es: "Tope alcanzado", en: "Cap reached" },
  "companion.meter.exhausted.body": {
    es: "Se agotaron los tokens del Companion de este mes. Escríbenos y ampliamos el tope.",
    en: "This month's Companion tokens are used up. Contact us and we will raise the cap.",
  },

  // ── composer ─────────────────────────────────────────────────────────
  "companion.composer.label": { es: "Mensaje al Companion", en: "Message to the Companion" },
  "companion.composer.placeholder": {
    es: "Pregunta o pide algo… (Enter envía, Mayús+Enter salto de línea)",
    en: "Ask or request something… (Enter sends, Shift+Enter for a new line)",
  },
  "companion.composer.send": { es: "Enviar", en: "Send" },
  "companion.composer.stop": { es: "Detener", en: "Stop" },
  "companion.composer.tooLong": { es: "Máximo 8000 caracteres", en: "8000 characters maximum" },
  "companion.composer.blocked": {
    es: "Decide la confirmación pendiente antes de seguir.",
    en: "Decide the pending confirmation before carrying on.",
  },
  "companion.mode": { es: "Modo", en: "Mode" },
  "companion.mode.consult": { es: "Consultar", en: "Consult" },
  "companion.mode.build": { es: "Construir", en: "Build" },
  "companion.mode.consult.hint": {
    es: "Solo lectura: responde, diagnostica y explica. No propone cambios salvo que se los pidas.",
    en: "Read-only: it answers, diagnoses and explains. It proposes no changes unless you ask.",
  },
  "companion.mode.build.hint": {
    es: "Puede proponer cambios. Cada uno pasa por tu confirmación antes de aplicarse.",
    en: "It can propose changes. Each one goes through your confirmation before being applied.",
  },
  "companion.context.here": { es: "Aquí: {route}", en: "Here: {route}" },
  "companion.context.client": { es: "Cliente {ref}", en: "Client {ref}" },

  // ── suggestions of the empty state (§14: derived, never generic) ──────
  "companion.suggest.home.1": { es: "¿Qué cliente mío necesita atención hoy?", en: "Which of my clients needs attention today?" },
  "companion.suggest.home.2": { es: "Resúmeme cómo fue la semana", en: "Sum up how the week went" },
  "companion.suggest.home.3": { es: "¿Hay algo a medio configurar?", en: "Is anything half-configured?" },

  "companion.suggest.clients.1": { es: "¿Cuáles de mis clientes no están listos para producción?", en: "Which of my clients are not production-ready?" },
  "companion.suggest.clients.2": { es: "¿Cuánto cupo de clientes me queda?", en: "How much client quota do I have left?" },
  "companion.suggest.clients.3": { es: "Ayúdame a dar de alta un cliente nuevo", en: "Help me set up a new client" },

  "companion.suggest.client.1": { es: "¿Qué le falta a {client} para estar listo?", en: "What does {client} still need to be ready?" },
  "companion.suggest.client.2": { es: "¿Cómo va {client} este mes?", en: "How is {client} doing this month?" },
  "companion.suggest.client.3": { es: "Explícame la configuración de {client}", en: "Walk me through {client}'s setup" },

  "companion.suggest.agent.1": { es: "Mejora este prompt y enséñame el diff", en: "Improve this prompt and show me the diff" },
  "companion.suggest.agent.2": { es: "¿Qué herramientas tiene activas este agente y para qué sirven?", en: "Which tools does this agent have on, and what for?" },
  "companion.suggest.agent.3": { es: "¿Es seguro publicar la versión en borrador?", en: "Is it safe to publish the draft version?" },

  "companion.suggest.agentSettings.1": { es: "¿Qué hace cada ajuste de esta pantalla?", en: "What does each setting on this screen do?" },
  "companion.suggest.agentSettings.2": { es: "¿Esta política deja pasar algo que no debería?", en: "Does this policy let through anything it should not?" },
  "companion.suggest.agentSettings.3": { es: "Compara esta política con la de mis otros clientes", en: "Compare this policy with my other clients'" },

  "companion.suggest.tools.1": { es: "¿Qué hace cada herramienta activa aquí?", en: "What does each tool enabled here do?" },
  "companion.suggest.tools.2": { es: "¿Falta alguna herramienta para lo que hace este agente?", en: "Is any tool missing for what this agent does?" },
  "companion.suggest.tools.3": { es: "¿Alguna de estas herramientas puede hacer algo irreversible?", en: "Can any of these tools do something irreversible?" },

  "companion.suggest.skills.1": { es: "¿Qué aporta cada skill activa?", en: "What does each enabled skill add?" },
  "companion.suggest.skills.2": { es: "¿Alguna skill choca con la política de este cliente?", en: "Does any skill clash with this client's policy?" },
  "companion.suggest.skills.3": { es: "¿Qué skills usan mis clientes parecidos?", en: "Which skills do my similar clients use?" },

  "companion.suggest.knowledge.1": { es: "¿Qué sabe este agente y qué no?", en: "What does this agent know, and what does it not?" },
  "companion.suggest.knowledge.2": { es: "¿Hay conocimiento que se contradiga?", en: "Is any of the knowledge contradictory?" },
  "companion.suggest.knowledge.3": { es: "¿Qué le falta saber para las preguntas más frecuentes?", en: "What does it still need to know for the most common questions?" },

  "companion.suggest.channels.1": { es: "¿Por qué bajó la calidad de este número?", en: "Why did this number's quality drop?" },
  "companion.suggest.channels.2": { es: "¿Hay plantillas rechazadas y por qué?", en: "Are any templates rejected, and why?" },
  "companion.suggest.channels.3": { es: "¿Este canal está bien conectado?", en: "Is this channel properly connected?" },

  "companion.suggest.playground.1": { es: "¿Qué debería probar antes de publicar?", en: "What should I test before publishing?" },
  "companion.suggest.playground.2": { es: "Dame casos difíciles para este agente", en: "Give me hard cases for this agent" },
  "companion.suggest.playground.3": { es: "¿Por qué respondió así en la última prueba?", en: "Why did it answer that way in the last test?" },

  "companion.suggest.conversations.1": { es: "¿En qué se atasca la gente al hablar con este agente?", en: "Where do people get stuck talking to this agent?" },
  "companion.suggest.conversations.2": { es: "¿Cuántas conversaciones acabaron escaladas?", en: "How many conversations ended up escalated?" },
  "companion.suggest.conversations.3": { es: "¿Qué falla más en las últimas conversaciones?", en: "What fails most in recent conversations?" },

  "companion.suggest.usage.1": { es: "¿Por qué subió el consumo este mes?", en: "Why did usage go up this month?" },
  "companion.suggest.usage.2": { es: "¿Qué cliente me está costando más y por qué?", en: "Which client is costing me most, and why?" },
  "companion.suggest.usage.3": { es: "Proyecta cómo cerrará el mes", en: "Project how the month will close" },

  "companion.suggest.audit.1": { es: "¿Qué cambió esta semana y quién lo cambió?", en: "What changed this week and who changed it?" },
  "companion.suggest.audit.2": { es: "¿Hubo algún cambio raro en producción?", en: "Was there any odd change in production?" },
  "companion.suggest.audit.3": { es: "Enséñame los cambios que hizo el Companion", en: "Show me the changes the Companion made" },

  "companion.suggest.team.1": { es: "¿Quién tiene permiso para publicar agentes?", en: "Who has permission to publish agents?" },
  "companion.suggest.team.2": { es: "¿Qué puede hacer cada rol exactamente?", en: "What exactly can each role do?" },
  "companion.suggest.team.3": { es: "¿Hay invitaciones sin aceptar?", en: "Are there unaccepted invitations?" },

  "companion.suggest.keys.1": { es: "¿Para qué sirve cada clave y quién la usa?", en: "What is each key for, and who uses it?" },
  "companion.suggest.keys.2": { es: "¿Hay alguna clave sin usar desde hace tiempo?", en: "Is any key unused for a long time?" },
  "companion.suggest.keys.3": { es: "¿Cómo integro la API en mi producto?", en: "How do I integrate the API into my product?" },

  "companion.suggest.billing.1": { es: "Explícame esta factura", en: "Explain this invoice" },
  "companion.suggest.billing.2": { es: "¿Qué parte del gasto es de cada cliente?", en: "How much of the spend is each client's?" },
  "companion.suggest.billing.3": { es: "¿Cómo bajo el coste sin perder calidad?", en: "How do I cut cost without losing quality?" },
} as const;
