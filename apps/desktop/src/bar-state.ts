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
  /**
   * Spec 008 R4.3 — la plataforma exige una versión más nueva.
   *
   * Es un estado de conexión y no un aviso, porque el puente está **parado**:
   * el latido no pasa. Pero, a diferencia de `archivada_desde_consola` y
   * `volver_a_emparejar`, **la credencial sigue siendo buena** — lo viejo es el
   * binario. Por eso no se llega aquí olvidando nada, y por eso se sale solo:
   * en cuanto la actualización se aplica, el siguiente latido pasa.
   */
  "version_no_admitida",
] as const;

export type BarStatus = (typeof BAR_STATUSES)[number];

/**
 * Que hay una versión esperando — spec 008, R3.7 y R3.8.
 *
 * **Va aparte de `status`, y no es un octavo estado.** Los siete que hay son de
 * conexión y se excluyen entre sí; «hay una actualización lista» es ortogonal:
 * una máquina puede estar `conectada` **y** tener una versión esperando, y
 * meterlo en la misma enumeración obligaría a elegir cuál de las dos cosas se
 * cuenta. Se perdería justo la que importa.
 *
 * `waiting` distingue las dos situaciones que la persona vive distinto:
 *
 * * `false` — «lista, se instala al cerrar». No pide nada.
 * * `true`  — «esperando a que termine lo que hay vivo». Explica por qué la
 *   aplicación **no** se está actualizando, que es la pregunta que alguien se
 *   hace cuando le dijeron que había versión nueva y sigue viendo la vieja.
 *
 * **Ausente significa que no hay nada que decir** (§V): sin versión esperando,
 * la barra no pinta indicador apagado ni texto explicando lo que no hay.
 */
export type BarUpdate = { version: string; waiting: boolean };

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
  /** Spec 008: hay versión descargada. **Ausente = no hay nada que decir** (§V). */
  update?: BarUpdate;
  /** Spec 008 R4.2: qué versión exige la plataforma, para poder decirlo. */
  requiredVersion?: string;
  /**
   * Spec 009 R1 — qué superficie se ve.
   *
   * **Ausente significa la pantalla del equipo**, y con ella no hay nada que
   * ofrecer: la ausencia se diseña (§V). Sólo se puebla cuando la consola
   * ocupa la ventana, que es el único momento en que volver lleva a algún
   * sitio.
   */
  surface?: "console";
};

export type BarAction =
  | "introducir_codigo"
  | "directorios"
  | "desemparejar"
  | "actualizar"
  /** Spec 009 R1. **Ortogonal a los siete estados**, como `update`: depende de
   *  qué superficie se ve, no de si la máquina está emparejada. */
  | "volver_a_la_app";

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
  | { kind: "person"; locale?: "es" | "en" }
  /** Spec 008: el updater avisa de lo que tiene y de si puede aplicarlo. */
  | { kind: "update_ready"; version: string; waiting: boolean }
  /** Se aplicó, o dejó de haber nada: la barra vuelve a no decir nada. */
  | { kind: "update_gone" }
  /** Spec 008: la plataforma pide una versión más nueva. NO se olvida nada. */
  | { kind: "version_rejected"; minimumVersion?: string }
  /**
   * Spec 009 R4.7 — el código de sesión no valía.
   *
   * **No toca `status` y no olvida nada.** Canjear mal no es perder la
   * conexión ni la credencial: es que ocho caracteres no eran los buenos. Se
   * cuenta como los siete estados, en tono de estado y nunca en rojo.
   */
  | { kind: "redeem_failed" };

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

/**
 * Lo que la barra ofrece, entero — spec 009, R1.
 *
 * Dos mitades que se suman y **no se mezclan**:
 *
 * * `actionsFor(state)` decide a partir de `status`, los siete estados de
 *   conexión, y se apaga sin cifrado porque sin dónde guardar no hay nada que
 *   emparejar.
 * * volver a la pantalla del equipo depende de **qué se ve**, no de la
 *   conexión, y no guarda nada.
 *
 * Meter la segunda dentro de la primera la haría desaparecer con el
 * `if (!state.encryptionAvailable) return []` de abajo, y encerrar a alguien en
 * la consola porque su llavero está bloqueado sería un castigo sin causa
 * (R2.4). Por eso se componen aquí y no allí.
 */
/**
 * El estado que se le empuja a la barra, con la superficie dentro — spec 009 R1.
 *
 * Vive aquí y no en la cáscara porque es una decisión, no pegamento: **qué
 * significa "no hay superficie que decir"**. Y la respuesta es que el campo no
 * está, no que valga `"app"` — la ausencia se diseña (§V), y un `surface:"app"`
 * obligaría a la barra a distinguir dos formas de decir lo mismo.
 */
export function withSurface(state: BarState, surface: "app" | "console"): BarState {
  return surface === "console" ? { ...state, surface: "console" } : { ...state, surface: undefined };
}

export function barActions(state: BarState): BarAction[] {
  return [
    ...(state.surface === "console" ? (["volver_a_la_app"] as const) : []),
    ...actionsFor(state),
  ];
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
    // Spec 008 R4.3: se ofrece **actualizar**, y sólo eso. No «introducir
    // código»: la credencial sigue siendo válida y volver a emparejar no
    // arreglaría nada — mandaría a la persona a dar vueltas por la consola
    // buscando un código que no es el problema.
    case "version_no_admitida":
      return ["actualizar"];
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
    // Olvidar la credencial no cambia qué superficie se está viendo.
    ...(state.surface ? { surface: state.surface } : {}),
  };
}

export function transition(state: BarState, event: BarEvent): BarState {
  switch (event.kind) {
    // Spec 008 — los dos eventos de actualización **no tocan `status`**, y eso
    // es la decisión entera: son ortogonales a la conexión. Una máquina
    // `conectada` con una versión esperando sigue estando conectada, y las
    // herramientas locales y el latido siguen dependiendo sólo de `status`.
    case "update_ready":
      return { ...state, update: { version: event.version, waiting: event.waiting } };
    // Volver a `undefined` y no a un objeto con `waiting: false`: la ausencia
    // se diseña (§V). Sin versión esperando, la barra no dice nada — ni
    // indicador apagado ni texto explicando lo que no hay.
    case "update_gone":
      return { ...state, update: undefined };
    // El puente para, pero **la credencial se conserva**: esto no es una
    // máquina archivada ni una que haya que volver a emparejar. Se sale solo en
    // cuanto la actualización se aplique.
    case "version_rejected":
      return {
        ...state,
        status: "version_no_admitida",
        requiredVersion: event.minimumVersion,
        lastError: undefined,
      };
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
    case "redeem_failed":
      return { ...state, lastError: { code: "session_code_invalid" } };
    case "person":
      return event.locale ? { ...state, locale: event.locale } : state;
  }
}
