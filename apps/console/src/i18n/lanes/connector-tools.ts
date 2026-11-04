/** ES/EN del carril `connector-tools` — «Herramientas» de un conector en la pestaña
 *  Conectores de un agente: qué deja hacer ese conector, y encenderlo o apagarlo de
 *  uno en uno. Ni «integración» ni punto y coma (`words.test.ts`). */
export const connectorToolsMessages = {
  "connTools.open": { es: "Herramientas", en: "Tools" },
  "connTools.named": { es: "Herramientas de {name}", en: "{name} tools" },
  "connTools.body": {
    es: "Los cambios van al borrador y se aplican al guardarlo. Cada cambio deja desactualizadas las pruebas de este agente.",
    en: "Changes go to the draft and apply when you save it. Each change marks this agent's tests as out of date.",
  },
  "connTools.readonly": { es: "Tu rol puede ver estas herramientas, no cambiarlas.", en: "Your role can see these tools, not change them." },
  "connTools.loading": { es: "Cargando las herramientas…", en: "Loading the tools…" },
  "connTools.error": {
    es: "No se pudieron cargar las herramientas de este conector. Lo que el agente ya usa sigue funcionando.",
    en: "Could not load this connector's tools. Whatever the agent already uses keeps working.",
  },
  "connTools.empty": {
    es: "Este conector todavía no trae herramientas. Aparecen cuando termina de sincronizarse.",
    en: "This connector has no tools yet. They appear once it finishes syncing.",
  },
  "connTools.search": { es: "Buscar herramienta", en: "Find a tool" },
  "connTools.noMatch": { es: "Ninguna herramienta coincide con «{q}».", en: "No tool matches “{q}”." },
  "connTools.clear": { es: "Quitar la búsqueda", en: "Clear the search" },
  "connTools.showAll": { es: "Ver todas ({n})", en: "See all ({n})" },
  "connTools.showLess": { es: "Ver menos", en: "See fewer" },
  "connTools.shown": { es: "Se ven {shown} de {total}.", en: "Showing {shown} of {total}." },
  "connTools.group.read": { es: "Consulta", en: "Reads" },
  "connTools.group.write": { es: "Cambia", en: "Changes" },
  "connTools.suggested": { es: "Recomendada", en: "Recommended" },
  "connTools.unsaved": { es: "Sin guardar", en: "Not saved" },
  "connTools.hint.read": { es: "Solo consulta datos.", en: "Only reads data." },
  "connTools.hint.write": { es: "Puede cambiar datos.", en: "Can change data." },
  "connTools.state.on": { es: "Encendida", en: "On" },
  "connTools.state.off": { es: "Apagada", en: "Off" },
  "connTools.needsWrite": { es: "Necesita el permiso «{permission}» para actuar.", en: "Needs the “{permission}” permission to act." },
  "connTools.needsWrite.group": {
    es: "Este agente tiene el permiso «{current}». Lo de este grupo no actúa hasta que sea «{permission}», aunque esté encendido.",
    en: "This agent has the “{current}” permission. Nothing in this group acts until it is “{permission}”, even if it is on.",
  },
  "connTools.toSettings": { es: "Cambiar en Ajustes", en: "Change in Settings" },
  "connTools.locked.task": {
    es: "No se puede apagar porque una tarea de este agente la usa. Cambia la tarea primero.",
    en: "It can't be switched off because one of this agent's tasks uses it. Change the task first.",
  },
  "connTools.locked.test": {
    es: "No se puede apagar porque una prueba de este agente espera lo que solo ella hace. Cambia la prueba primero.",
    en: "It can't be switched off because one of this agent's tests expects what only it does. Change the test first.",
  },
  "connTools.locked.promise": {
    es: "No se puede apagar porque las instrucciones de este agente prometen lo que solo ella hace. Cambia las instrucciones primero.",
    en: "It can't be switched off because this agent's instructions promise what only it does. Change the instructions first.",
  },
  "connTools.failed.customer": {
    es: "No se puede encender porque deja elegir a qué cliente consultar, y un agente solo puede ver a quien le escribe.",
    en: "It can't be switched on because it lets the agent choose which customer to look up, and an agent can only see whoever is writing to it.",
  },
  "connTools.failed.full": {
    es: "Este agente ya lleva {max} herramientas, que es el máximo. Apaga alguna antes de encender otra.",
    en: "This agent already has {max} tools, the maximum. Switch one off before switching on another.",
  },
  "connTools.failed.gone": { es: "Esta herramienta ya no está disponible.", en: "This tool is no longer available." },
  "connTools.failed.refused": { es: "Este agente no puede usar esta herramienta, así que sigue apagada.", en: "This agent can't use this tool, so it stays off." },
  "connTools.failed.unknown": { es: "No se pudo cambiar y se queda como estaba. Inténtalo de nuevo.", en: "It could not be changed and stays as it was. Try again." },
} as const;
