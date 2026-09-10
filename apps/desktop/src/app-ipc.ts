/**
 * El canal de la pantalla de operar — spec 003, Requisito 12.1 y 12.2.
 *
 * **La lista es el contrato** (`contracts/desktop-app-ipc.md`): el `preload`
 * expone exactamente estos nombres y ninguno más; un test lo recorre. Cada
 * entrada declara qué acepta, y el proceso principal valida la entrada antes
 * de hacer nada con ella.
 *
 * Y la regla que más importa: **nada de lo que sale por aquí lleva una sesión,
 * una cookie, un token ni una credencial.** `redact` quita esas claves a
 * cualquier profundidad antes de contestar, y el test de aislamiento lo
 * afirma con cuerpos envenenados.
 */

export type Shape = "none" | "id" | "thread_open" | "thread_id" | "run_events" | "thread_send" | "run" | "stream_open" | "stream_close" | "decide" | "tasks_list" | "pref" | "open_console" | "notif_prefs" | "roster_create" | "roster_update";

export type InvokeChannel = { name: `app:${string}`; input: Shape };

export const APP_INVOKE_CHANNELS: readonly InvokeChannel[] = [
  { name: "app:whoami", input: "none" },
  { name: "app:roster.list", input: "none" },
  { name: "app:roster.create", input: "roster_create" },
  { name: "app:roster.update", input: "roster_update" },
  { name: "app:roster.archive", input: "id" },
  { name: "app:roster.jobs", input: "none" },
  { name: "app:thread.open", input: "thread_open" },
  { name: "app:thread.runs", input: "thread_id" },
  { name: "app:run.events", input: "run_events" },
  { name: "app:thread.send", input: "thread_send" },
  { name: "app:thread.cancel", input: "run" },
  { name: "app:stream.open", input: "stream_open" },
  { name: "app:stream.close", input: "stream_close" },
  { name: "app:inbox.list", input: "none" },
  { name: "app:inbox.decide", input: "decide" },
  { name: "app:tasks.list", input: "tasks_list" },
  { name: "app:tasks.cancel", input: "id" },
  { name: "app:policy.prefs", input: "none" },
  { name: "app:policy.setPref", input: "pref" },
  { name: "app:usage", input: "none" },
  { name: "app:env.forThread", input: "thread_id" },
  { name: "app:openConsole", input: "open_console" },
  { name: "app:notifications.prefs", input: "notif_prefs" },
] as const;

export const APP_PUSH_CHANNELS = [
  "app:event",
  "app:inbox",
  "app:inbox.focus",
  "app:stream.end",
  "app:inbox.changed",
  "app:task.state",
  "app:session",
  "app:presence",
] as const;

export type PushChannel = (typeof APP_PUSH_CHANNELS)[number];

/** Claves que **nunca** viajan al renderer, a ninguna profundidad. */
export const FORBIDDEN_KEYS = /session|cookie|token|credential|authorization|secret|password/i;

export class InvalidIpcInput extends Error {
  constructor(channel: string, why: string) {
    super(`${channel}: ${why}`);
    this.name = "InvalidIpcInput";
  }
}

const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown): v is string => typeof v === "string" && v.length > 0 && v.length <= 4096;
const uuidish = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f-]{36}$/i.test(v);

/** Valida la entrada de un canal. Lanza `InvalidIpcInput`; nunca adivina. */
export function validateInput(channel: string, input: unknown): void {
  const entry = APP_INVOKE_CHANNELS.find((c) => c.name === channel);
  if (!entry) throw new InvalidIpcInput(channel, "canal fuera de la lista");
  const need = (ok: boolean, why: string) => {
    if (!ok) throw new InvalidIpcInput(channel, why);
  };
  switch (entry.input) {
    case "none":
      return;
    case "id":
      return need(isRecord(input) && uuidish(input.id), "id");
    case "run":
      return need(isRecord(input) && uuidish(input.run_id), "run_id");
    case "thread_open":
      return need(isRecord(input) && uuidish(input.teammate_id), "teammate_id");
    case "thread_id":
      return need(isRecord(input) && uuidish(input.thread_id), "thread_id");
    case "run_events":
      return need(
        isRecord(input) && uuidish(input.run_id) && (input.since_seq === undefined || typeof input.since_seq === "number"),
        "run_id",
      );
    case "thread_send":
      return need(
        isRecord(input) && uuidish(input.thread_id) && str(input.text) && (input.client_ref === undefined || str(input.client_ref)),
        "thread_id, text",
      );
    case "stream_open":
      return need(isRecord(input) && uuidish(input.run_id) && typeof input.since_seq === "number", "run_id, since_seq");
    case "stream_close":
      return need(isRecord(input) && str(input.stream_id), "stream_id");
    case "decide":
      return need(
        isRecord(input) && uuidish(input.action_id) && uuidish(input.run_id) && ["confirm", "edit", "cancel"].includes(String(input.decision)),
        "action_id, run_id, decision",
      );
    case "tasks_list":
      return need(input === undefined || (isRecord(input) && (input.state === undefined || str(input.state))), "state");
    case "pref":
      return need(
        isRecord(input) && (input.executable === null || str(input.executable)) && ["ask", "always", "never"].includes(String(input.mode)),
        "executable, mode",
      );
    case "open_console":
      return need(isRecord(input) && typeof input.path === "string" && input.path.startsWith("/") && !input.path.startsWith("//"), "path");
    case "notif_prefs":
      return need(input === undefined || (isRecord(input) && (input.silence_aviso === undefined || typeof input.silence_aviso === "boolean")), "silence_aviso");
    case "roster_create":
      return need(isRecord(input) && str(input.name) && str(input.job) && str(input.model), "name, job, model");
    case "roster_update":
      return need(isRecord(input) && uuidish(input.id) && isRecord(input.patch), "id, patch");
  }
}

/**
 * Quita, a cualquier profundidad, toda clave que pueda llevar una sesión o una
 * credencial. Se aplica a **todo** lo que el principal devuelve al renderer,
 * aunque «no debería» llevarla: la regla no es una promesa.
 */
export function redact<T>(value: T): T {
  if (Array.isArray(value)) return value.map((v) => redact(v)) as T;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (FORBIDDEN_KEYS.test(k)) continue;
      out[k] = redact(v);
    }
    return out as T;
  }
  return value;
}

/** ¿Contiene el valor alguna clave prohibida? Para el test, no para producción. */
export function hasForbiddenKey(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasForbiddenKey);
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).some(([k, v]) => FORBIDDEN_KEYS.test(k) || hasForbiddenKey(v));
  }
  return false;
}
