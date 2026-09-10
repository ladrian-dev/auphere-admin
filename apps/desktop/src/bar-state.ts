/**
 * La máquina de estados de la barra del puesto — Requisito 12.2 (spec 002).
 *
 * Siete estados, nombrados en `contracts/desktop-bar.md`, y **ninguno es un
 * error**: perder la conexión en un portátil es lo normal, y pintarlo en rojo
 * enseña a ignorar los rojos. Lo que aquí se decide se prueba sin display; la
 * barra solo pinta.
 *
 * Dos consecuencias viven aquí y no en la pantalla, para que no se puedan
 * olvidar: las herramientas locales **solo** existen en `conectada` (12.3) y
 * el latido solo corre en `conectada` y `reconectando`.
 */

export const BAR_STATUSES = [
  "sin_emparejar",
  "emparejando",
  "conectada",
  "reconectando",
  "sin_sesion",
  "volver_a_emparejar",
  "archivada_desde_consola",
] as const;

export type BarStatus = (typeof BAR_STATUSES)[number];

export type BarLink = { clientRef: string; clientName: string | null; needsDirectory: boolean };
export type BarMachine = { displayName: string; hostname: string };

export type BarState = {
  status: BarStatus;
  machine?: BarMachine;
  /** Historia 5.1: emparejada por otra persona; nunca se dice por quién. */
  pairedByOther?: boolean;
  links: BarLink[];
  /** Se pinta como estado, nunca en rojo. */
  lastError?: { code: string };
  /** `false` → no se guarda nada y no se ofrece emparejar (1.2). */
  encryptionAvailable: boolean;
  /** El idioma de la cuenta, para hablar como la consola; sin él, el del sistema. */
  locale?: "es" | "en";
};

export type BarAction = "introducir_codigo" | "directorios" | "desemparejar";

export type BarEvent =
  | { kind: "pair_started" }
  | { kind: "pair_ok"; machine: BarMachine }
  | { kind: "pair_failed"; code: string }
  | { kind: "link_ok" }
  | { kind: "link_lost" }
  | { kind: "links_updated"; links: BarLink[] }
  | { kind: "session_gone" }
  | { kind: "session_same_person" }
  | { kind: "session_other_person" }
  | { kind: "unauthorized" }
  | { kind: "pairing_required" }
  | { kind: "archived" }
  | { kind: "unpaired" }
  | { kind: "restored"; machine: BarMachine }
  | { kind: "person"; locale?: "es" | "en" };

export function initialState(encryptionAvailable = true): BarState {
  return { status: "sin_emparejar", links: [], encryptionAvailable };
}

/** Clave de i18n; la barra no incrusta copy en el estado. */
export function statusCopyKey(status: BarStatus): string {
  return `workstation.bar.${status}`;
}

/** Siempre `estado`. Existe para que un test lo afirme sobre los siete. */
export function statusTone(_status: BarStatus): "estado" {
  return "estado";
}

export function localToolsOffered(status: BarStatus): boolean {
  return status === "conectada";
}

export function heartbeatRuns(status: BarStatus): boolean {
  return status === "conectada" || status === "reconectando";
}

export function actionsFor(state: BarState): BarAction[] {
  if (!state.encryptionAvailable) return [];
  switch (state.status) {
    case "sin_emparejar":
    case "volver_a_emparejar":
    case "archivada_desde_consola":
      return ["introducir_codigo"];
    case "conectada":
      return ["directorios", "desemparejar"];
    case "emparejando":
    case "reconectando":
    case "sin_sesion":
      return [];
  }
}

function forget(state: BarState, status: BarStatus): BarState {
  return {
    status,
    links: [],
    encryptionAvailable: state.encryptionAvailable,
    ...(state.locale ? { locale: state.locale } : {}),
  };
}

export function transition(state: BarState, event: BarEvent): BarState {
  switch (event.kind) {
    case "pair_started":
      return { ...state, status: "emparejando", lastError: undefined, pairedByOther: undefined };
    case "pair_ok":
    case "restored":
      return {
        ...state,
        status: "conectada",
        machine: event.machine,
        lastError: undefined,
        pairedByOther: undefined,
      };
    case "pair_failed":
      return { ...state, status: "sin_emparejar", lastError: { code: event.code } };
    case "link_ok":
      return state.machine ? { ...state, status: "conectada" } : state;
    case "link_lost":
      return state.status === "conectada" ? { ...state, status: "reconectando" } : state;
    case "links_updated":
      return { ...state, links: event.links };
    case "session_gone":
      return { ...state, status: "sin_sesion" };
    case "session_same_person":
      return state.machine ? { ...state, status: "conectada" } : { ...state, status: "sin_emparejar" };
    case "session_other_person":
      return { ...forget(state, "sin_emparejar"), pairedByOther: true };
    case "unauthorized":
    case "pairing_required":
      return forget(state, "volver_a_emparejar");
    case "archived":
      return forget(state, "archivada_desde_consola");
    case "unpaired":
      return forget(state, "sin_emparejar");
    case "person":
      return event.locale ? { ...state, locale: event.locale } : state;
  }
}
