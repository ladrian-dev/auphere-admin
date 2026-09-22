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

import { isSection } from "./sections.js";

export type Shape =
  | "none" | "id" | "thread_open" | "thread_id" | "run_events" | "thread_send" | "run" | "stream_open" | "stream_close"
  | "decide" | "tasks_list" | "pref" | "open_console" | "notif_prefs" | "roster_create" | "roster_update"
  // Spec 010 — el armazón y el puesto absorbido.
  | "section" | "content_bounds" | "shell_prefs" | "pair_code" | "client_ref" | "handoff"
  | "exec_output" | "search";

export type InvokeChannel = { name: `app:${string}`; input: Shape };

export const APP_INVOKE_CHANNELS: readonly InvokeChannel[] = [
  { name: "app:whoami", input: "none" },
  { name: "app:roster.list", input: "none" },
  { name: "app:roster.create", input: "roster_create" },
  { name: "app:roster.update", input: "roster_update" },
  { name: "app:roster.archive", input: "id" },
  { name: "app:roster.changes", input: "id" },
  { name: "app:roster.jobs", input: "none" },
  { name: "app:thread.open", input: "thread_open" },
  //  Spec 013, R4 — varias conversaciones por teammate. La base de datos las
  //  admite desde la 003; lo que faltaba era poder pedirlas y crearlas.
  { name: "app:thread.create", input: "thread_open" },
  { name: "app:thread.list", input: "thread_open" },
  //  Spec 013, R7 — buscar dentro de lo hablado. ⌘K solo navegaba.
  { name: "app:companion.search", input: "search" },
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
  /**
   * El plan y lo que admite — spec 010, R9. **Solo lectura**: contratar y
   * comprar ocurren en el navegador (R9.4), y la aplicación no pide ni enseña
   * datos de tarjeta en ningún caso (R9.10).
   */
  { name: "app:membership", input: "none" },
  { name: "app:team", input: "none" },
  { name: "app:env.forThread", input: "thread_id" },
  { name: "app:openConsole", input: "open_console" },
  { name: "app:notifications.prefs", input: "notif_prefs" },

  /*
   * Spec 010 (`contracts/desktop-app-ipc-v2.md`). Tres grupos:
   *
   * * **el armazón** — pedir una sección, decir dónde cabe el panel y guardar
   *   las preferencias de la ventana;
   * * **el puesto de trabajo**, que deja de ser superficie propia y trae aquí
   *   sus capacidades (enmienda del contrato de la spec 002);
   * * **los recorridos que salen y vuelven** — entrar por el navegador, la
   *   puesta en marcha, instalar la versión descargada y la vuelta del pago.
   *
   * Ninguno acepta `tenant_id`, ninguno aprueba nada y ninguno devuelve
   * credenciales: `redact` sigue aplicándose a todo lo que sale.
   */
  { name: "app:shell.showSection", input: "section" },
  { name: "app:shell.contentBounds", input: "content_bounds" },
  { name: "app:shell.prefs", input: "shell_prefs" },
  { name: "app:signIn.start", input: "none" },
  { name: "app:signIn.cancel", input: "none" },
  { name: "app:workstation.state", input: "none" },
  { name: "app:workstation.pair", input: "pair_code" },
  { name: "app:workstation.unpair", input: "none" },
  { name: "app:workstation.pickDirectory", input: "client_ref" },
  /**
   * Lo que escribió un comando ya ejecutado (spec 013, R3). Va por el proceso
   * principal porque la pantalla no tiene credenciales, como todo lo demás. La
   * salida **no se guarda en ningún sitio**: esto la pide mientras dura.
   */
  { name: "app:workstation.execOutput", input: "exec_output" },
  { name: "app:setup.status", input: "none" },
  { name: "app:update.install", input: "none" },
  /**
   * Comprobar el canal **ahora**, porque la persona lo pidió (R6.4 y R6.5).
   * Sin esto, la única salida de «esta versión ya no se admite» era abrir el
   * directorio crudo del canal en el navegador: una lista de `.zip` y `.yml`.
   */
  { name: "app:update.check", input: "none" },
  /**
   * Abrir el panel de avisos de Ajustes del sistema — spec 010, R7.10.
   *
   * **Sin parámetros, y a propósito.** Un canal que aceptara una dirección le
   * daría a la pantalla la capacidad de abrir cualquier esquema del sistema
   * operativo, que es mucho más de lo que hace falta y más de lo que se puede
   * justificar al ampliar una lista cerrada. El destino está en el principal.
   */
  { name: "app:system.openNotificationSettings", input: "none" },
  { name: "app:handoff.done", input: "handoff" },
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
  // Spec 010. `app:waiting` es la **única** fuente del número de decisiones que
  // esperan; `app:connectivity` es lo que separa «sin red» de «sin sesión».
  "app:console.location",
  /**
   * La sección de administrar que la consola **no pudo cargar**, o `null`
   * cuando vuelve a cargar. Sin esto, lo que ocupaba el panel con la red caída
   * era la página de error de Chromium: en inglés y sin nada que pulsar.
   */
  "app:console.failed",
  /**
   * La aplicación acaba de **salir al navegador del sistema** (pago, entrada
   * con Google, cualquier enlace externo). Hasta ahora esto pasaba en silencio:
   * la ventana se quedaba igual y el navegador se abría detrás o delante sin
   * que nada dijera por qué (R5.3).
   */
  "app:handoff",
  "app:workstation",
  "app:signIn",
  "app:update",
  "app:waiting",
  "app:connectivity",
  /**
   * Mostrar u ocultar la lista lateral (R1.7).
   *
   * La orden vive en el menú porque la guía de escritorio lo pide y porque es
   * como se descubre el atajo; el estado de la lista lo lleva la pantalla. Es
   * el único camino para que una orden de menú alcance al armazón.
   */
  "app:shell.toggleSidebar",
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
/** Píxeles lógicos: entero y no negativo. Nada de decimales ni de negativos. */
const px = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;

/**
 * El alfabeto del código de emparejamiento (spec 002): sin I, L, O, U ni 0/1,
 * para que nadie confunda un carácter al teclearlo. Se comprueba **aquí**,
 * antes de tocar la red, porque un código mal tecleado no es un viaje.
 */
const PAIRING_ALPHABET = /^[ABCDEFGHJKMNPQRSTVWXYZ23456789]{8}$/;
const pairingCode = (v: unknown): v is string =>
  typeof v === "string" && PAIRING_ALPHABET.test(v.replace(/-/g, "").toUpperCase());

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
      // `prefer` (013, R4) es opcional; si viene, es un uuid. La entrada se
      // valida, no se adivina.
      return need(
        isRecord(input) &&
          uuidish(input.teammate_id) &&
          (input.prefer === undefined || uuidish(input.prefer)),
        "teammate_id",
      );
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

    // ── Spec 010 ────────────────────────────────────────────────────────────
    case "section":
      // Lo que no está en la lista canónica no existe: ni se muestra, ni se
      // traduce a una ruta. Una ruta **no** es una sección.
      return need(isRecord(input) && isSection(input.section), "section fuera de la lista canónica");
    case "content_bounds":
      return need(
        isRecord(input) && px(input.x) && px(input.y) && px(input.width) && px(input.height),
        "x, y, width, height: enteros no negativos",
      );
    case "shell_prefs":
      return need(
        isRecord(input) &&
          (input.theme === undefined || ["system", "light", "dark"].includes(String(input.theme))) &&
          (input.sidebarWidth === undefined || px(input.sidebarWidth)) &&
          // R1.10: la sección con la que se cerró. Se valida contra la lista
          // canónica, como `app:shell.showSection`: una preferencia guardada no
          // puede llevar a una sección que ya no existe.
          (input.section === undefined || isSection(input.section)) &&
          (input.silenceAviso === undefined || typeof input.silenceAviso === "boolean"),
        "theme, sidebarWidth, section, silenceAviso",
      );
    case "pair_code":
      return need(isRecord(input) && pairingCode(input.code), "code");
    case "client_ref":
      return need(isRecord(input) && str(input.client_ref), "client_ref");

    case "search":
      return need(isRecord(input) && typeof input.q === "string", "q");

    case "exec_output":
      return need(
        isRecord(input) && str(input.client_ref) && uuidish(input.execution_id),
        "exec_output",
      );
    case "handoff":
      return need(isRecord(input) && ["sign_in", "payment"].includes(String(input.kind)), "kind");
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
