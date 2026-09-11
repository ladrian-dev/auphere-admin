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
  "settings.open": { es: "Ajustes", en: "Settings" },
  "changes.title": { es: "Cambios de este teammate", en: "Changes to this teammate" },
  "changes.by": { es: "por {name}", en: "by {name}" },
  "changes.field.job": { es: "el oficio", en: "the job" },
  "changes.field.permissions": { es: "los permisos", en: "the permissions" },
  "changes.field.local_exec": { es: "ejecutar en tu máquina", en: "running on your machine" },
  "changes.field.model": { es: "el modelo", en: "the model" },
  "changes.line": { es: "Cambió {what}", en: "Changed {what}" },
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
  "inbox.cannotDecide": { es: "Tu rol no puede decidir esto. Pídeselo a un administrador.", en: "Your role cannot decide this. Ask an administrator." },
  "level.critico": { es: "Crítico", en: "Critical" },
  "level.aviso": { es: "Aviso", en: "Notice" },
  "level.informativo": { es: "Informativo", en: "Informative" },
  "nav.team": { es: "Equipo", en: "Team" },
  "nav.pending": { es: "Pendientes", en: "Pending" },
  "env.title": { es: "Entorno", en: "Environment" },
  "env.job": { es: "Oficio", en: "Job" },
  "env.model": { es: "Modelo", en: "Model" },
  "env.machine": { es: "Máquina", en: "Machine" },
  "env.machine.absent": { es: "sin conectar", en: "not connected" },
  "env.machine.none": { es: "Sin máquina emparejada — empareja la tuya desde la barra.", en: "No machine paired — pair yours from the bar." },
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
  "session.pair": { es: "Tu máquina no está emparejada: los teammates trabajan igual, pero no pueden tocar tus archivos hasta que la emparejes desde la barra.", en: "Your machine is not paired: teammates still work, but cannot touch your files until you pair it from the bar." },
} as const;

export type AppKey = keyof typeof COPY;

export function format(lang: Lang, key: AppKey, vars?: Record<string, string | number>): string {
  let out: string = COPY[key][lang];
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
