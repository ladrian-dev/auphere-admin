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
