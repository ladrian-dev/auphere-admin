/** ES/EN del carril `builder-model-quality` — Agente › Avanzado › Calidad
 *  (spec 047, historia 23; T147; requisito 39). Precios, nunca costes (C9), y
 *  sin nombrar la unidad interna (`money-words.test.ts`). Las líneas de cada
 *  opción son de la consola, no las de la API. Sin punto y coma (`words.test.ts`). */
export const builderModelQualityMessages = {
  "modelQuality.title": { es: "Calidad", en: "Quality" },
  "modelQuality.intro": {
    es: "Cuánta calidad paga este agente. Cada opción dice su precio estimado por mensaje. El cambio va al borrador y se aplica al guardar, si pasa las pruebas.",
    en: "How much quality this agent pays for. Each option shows its estimated price per message. The change goes to the draft and applies when you save, if it passes the tests.",
  },
  "modelQuality.loading": { es: "Cargando las opciones de calidad…", en: "Loading the quality options…" },
  "modelQuality.error": { es: "No se pudieron cargar las opciones de calidad.", en: "Could not load the quality options." },
  "modelQuality.retry": { es: "Reintentar", en: "Retry" },
  "modelQuality.readonly": { es: "Tu rol puede ver la calidad, no cambiarla.", en: "Your role can see the quality, not change it." },
  "modelQuality.source.agent_30d": {
    es: "Estimado con los mensajes de este agente en los últimos 30 días.",
    en: "Estimated from this agent's messages over the last 30 days.",
  },
  "modelQuality.source.sector": {
    es: "Estimado con un agente típico de su sector, hasta que este tenga mensajes.",
    en: "Estimated from a typical agent of its sector, until this one has messages.",
  },
  "modelQuality.real": { es: "Precio real medio por mensaje, últimos 7 días", en: "Real average price per message, last 7 days" },
  "modelQuality.real.none": { es: "Aún no hay mensajes en los últimos 7 días.", en: "No messages in the last 7 days yet." },
  "modelQuality.now": { es: "Ahora", en: "Now" },
  "modelQuality.legacy": { es: "El modelo que tenía antes de la consola nueva", en: "The model it had before the new console" },
  "modelQuality.drafted": { es: "En el borrador: {name}. Se aplica al guardar.", en: "In the draft: {name}. It applies when you save." },
  "modelQuality.eu": {
    es: "Este cliente tiene «Solo UE». Solo se ofrecen las opciones con modelos en la UE.",
    en: "This client is “EU only”. Only options with models in the EU are offered.",
  },
  "modelQuality.suggest": {
    es: "Este agente usa el modelo que tenía antes. Te proponemos «Automático», {price} por mensaje.",
    en: "This agent uses the model it had before. We suggest “Automatic”, {price} per message.",
  },
  "modelQuality.suggest.noPrice": {
    es: "Este agente usa el modelo que tenía antes. Te proponemos «Automático».",
    en: "This agent uses the model it had before. We suggest “Automatic”.",
  },

  // ── Las opciones (39.4) ────────────────────────────────────────────────
  "modelQuality.options": { es: "Opciones de calidad", en: "Quality options" },
  "modelQuality.profile.auto": { es: "Automático", en: "Automatic" },
  "modelQuality.profile.economy": { es: "Económico", en: "Economy" },
  "modelQuality.profile.balanced": { es: "Equilibrado", en: "Balanced" },
  "modelQuality.profile.max": { es: "Máximo", en: "Maximum" },
  "modelQuality.line.auto": {
    es: "Auphere elige en cada tarea el modelo más barato que la hace bien.",
    en: "Auphere picks, for each task, the cheapest model that does it well.",
  },
  "modelQuality.line.economy": { es: "El precio más bajo, para preguntas sencillas y repetidas.", en: "The lowest price, for simple and repeated questions." },
  "modelQuality.line.balanced": { es: "Más calidad en las respuestas sin disparar el precio.", en: "Better answers without a jump in price." },
  "modelQuality.line.max": { es: "La mejor calidad disponible, para conversaciones delicadas.", en: "The best quality available, for delicate conversations." },
  "modelQuality.pinned.title": { es: "Fijar un modelo", en: "Pin a model" },
  "modelQuality.pinned.line": {
    es: "Un modelo fijo para conversar. Las demás tareas siguen en «Automático».",
    en: "One fixed model for conversations. Every other task stays on “Automatic”.",
  },
  "modelQuality.pinned.empty": { es: "No hay modelos que se puedan fijar para este agente.", en: "There are no models that can be pinned for this agent." },
  "modelQuality.pinned.list": { es: "Modelos que se pueden fijar", en: "Models that can be pinned" },
  "modelQuality.residency.eu": { es: "En la UE", en: "In the EU" },
  "modelQuality.residency.us": { es: "En EE. UU.", en: "In the US" },
  "modelQuality.residency.global": { es: "Fuera de la UE", en: "Outside the EU" },
  "modelQuality.price": { es: "{amount} por mensaje", en: "{amount} per message" },
  "modelQuality.price.none": { es: "Sin precio estimado", en: "No estimated price" },
  "modelQuality.price.tiny": { es: "menos de {amount}", en: "less than {amount}" },
  "modelQuality.delta.more": { es: "{amount} más que la actual", en: "{amount} more than the current one" },
  "modelQuality.delta.less": { es: "{amount} menos que la actual", en: "{amount} less than the current one" },
  "modelQuality.delta.same": { es: "Lo mismo que la actual", en: "Same as the current one" },
  "modelQuality.badge.current": { es: "Actual", en: "Current" },
  "modelQuality.badge.drafted": { es: "En el borrador", en: "In the draft" },

  // ── «Comprobando la calidad…» (39.9) ───────────────────────────────────
  "modelQuality.check.none": { es: "Sin comprobar con este agente", en: "Not checked with this agent" },
  "modelQuality.check.certified": { es: "Comprobada con este agente", en: "Checked with this agent" },
  "modelQuality.check.running": { es: "Comprobando la calidad…", en: "Checking the quality…" },
  "modelQuality.check.passed": { es: "Pasó la comprobación", en: "Passed the check" },
  "modelQuality.check.failed": { es: "No pasó la comprobación", en: "Did not pass the check" },
  "modelQuality.check.run": { es: "Comprobar la calidad con {name}", en: "Check the quality with {name}" },
  "modelQuality.check.again": { es: "Comprobar otra vez con {name}", en: "Check again with {name}" },
  "modelQuality.check.cost": {
    es: "Comprobar pasa las pruebas del agente con esa opción y se paga en «Construcción y pruebas».",
    en: "Checking runs the agent's tests with that option and is paid from “Building and testing”.",
  },
  "modelQuality.check.done": { es: "{name} pasó la comprobación.", en: "{name} passed the check." },
  "modelQuality.check.notPassed": { es: "{name} no pasó la comprobación.", en: "{name} did not pass the check." },
  "modelQuality.reason.critical_failed": { es: "Falló una prueba crítica.", en: "A critical test failed." },
  "modelQuality.reason.no_result": { es: "La pasada no dio resultado.", en: "The run gave no result." },
  "modelQuality.reason.regression": { es: "Las pruebas bajan {points} puntos frente a la última pasada.", en: "The tests drop {points} points against the last run." },
  "modelQuality.reason.run_failed": { es: "La pasada no terminó.", en: "The run did not finish." },
  "modelQuality.reason.unknown": { es: "No cumple la puerta de calidad.", en: "It does not meet the quality gate." },

  // ── Usarla en el borrador (39.1) ───────────────────────────────────────
  "modelQuality.use": { es: "Usar {name} en el borrador", en: "Use {name} in the draft" },
  "modelQuality.used": { es: "{name} queda en el borrador. Pulsa «Guardar» para aplicarlo.", en: "{name} is in the draft. Press “Save” to apply it." },
  "modelQuality.use.needsCheck": { es: "Comprueba la calidad antes de usarla.", en: "Check the quality before using it." },
  "modelQuality.error.use": { es: "No se pudo cambiar el borrador. Vuelve a intentarlo.", en: "Could not change the draft. Try again." },
  "modelQuality.error.check": { es: "No se pudo comprobar la calidad. Vuelve a intentarlo.", en: "Could not check the quality. Try again." },
  "modelQuality.error.no_version": {
    es: "Este agente aún no tiene una versión que comprobar.",
    en: "This agent has no version to check yet.",
  },
  "modelQuality.error.not_eu": {
    es: "Esta opción no tiene modelos en la UE para todas sus tareas.",
    en: "This option does not have EU models for all its tasks.",
  },
  "modelQuality.error.invalid": { es: "Esa opción ya no se puede elegir.", en: "That option can no longer be chosen." },
} as const;
