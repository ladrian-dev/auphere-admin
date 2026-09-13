/**
 * Cuándo se actualiza sola, y cuándo no — spec 001, Requisito 9.2.
 *
 * **Puro, como el resto de lo que decide.** Recibe cómo está firmado este
 * binario, qué está pasando en la máquina y qué versión hay disponible, y dice
 * qué se hace. `main.ts` sólo ejecuta lo que esto devuelve, igual que con
 * `notifications-policy`.
 *
 * Tres reglas, y las tres son producto:
 *
 * * **Un build que no está firmado para distribuir no se actualiza, y ni
 *   siquiera pregunta.** Esta aplicación ejecuta órdenes en la máquina del
 *   partner: el canal de actualización es ejecución remota de código con otro
 *   nombre. La política falla **cerrada** — con un paquete ya descargado en el
 *   disco, un binario sin firmar sigue diciendo que no.
 * * **Descargar e instalar son decisiones distintas.** Descargar no molesta a
 *   nadie y se hace aunque haya trabajo vivo. Instalar reinicia la aplicación,
 *   así que espera: nunca se mata una sesión de agente ni se tira una acción
 *   que está esperando a que una persona la confirme.
 * * **Se instala al salir, nunca reiniciando por su cuenta.** Quien decide
 *   cuándo se va la aplicación es la persona que la está usando.
 *
 * Lo que esto NO hace, a propósito: comprobar la firma. Eso lo hace el sistema
 * operativo —Squirrel.Mac valida el *designated requirement* y rechaza un
 * paquete que no case— y no se reimplementa aquí. Lo que hace este módulo es no
 * llegar a pedirlo cuando de antemano no puede salir bien.
 */

/** Cómo está firmado el binario que está corriendo ahora mismo. */
export type BuildKind =
  /** `npm start` o un `--dir` sin firmar: no hay nada que actualizar. */
  | "unpackaged"
  /** Empaquetado y firmado ad-hoc (`codesign --sign -`). No distribuye. */
  | "adhoc"
  /** Firmado con un Developer ID y notarizado. El único que se actualiza. */
  | "signed";

/** Lo que está pasando en la máquina ahora. Si algo de esto es > 0, no se instala. */
export type Activity = {
  /** Sesiones de agente vivas en esta máquina. */
  liveSessions: number;
  /** Acciones que esperan la confirmación de una persona. */
  pendingApprovals: number;
};

export type Version = { version: string };

export type UpdateInput = {
  build: BuildKind;
  activity: Activity;
  /** Versión ya descargada y lista para instalar, si la hay. */
  downloaded: Version | null;
  /** Versión anunciada por el canal y todavía sin descargar, si la hay. */
  available: Version | null;
};

export type UpdateDecision =
  | { kind: "do-not-check"; reason: "unpackaged" | "unsigned" }
  | { kind: "check" }
  | { kind: "download"; version: string }
  | { kind: "wait"; version: string; reason: "busy" }
  | { kind: "install-on-quit"; version: string };

/** Hay trabajo que un reinicio destruiría. */
export function isBusy(activity: Activity): boolean {
  return activity.liveSessions > 0 || activity.pendingApprovals > 0;
}

/**
 * La decisión. El orden de las ramas **es** la política: la firma se mira
 * antes que nada, así que ninguna rama posterior puede rescatar a un binario
 * que no distribuye.
 */
export function decideUpdate(input: UpdateInput): UpdateDecision {
  if (input.build === "unpackaged") return { kind: "do-not-check", reason: "unpackaged" };
  if (input.build === "adhoc") return { kind: "do-not-check", reason: "unsigned" };

  if (input.downloaded) {
    // Descargado y listo. Sólo falta el momento, y lo elige el trabajo vivo.
    if (isBusy(input.activity)) {
      return { kind: "wait", version: input.downloaded.version, reason: "busy" };
    }
    return { kind: "install-on-quit", version: input.downloaded.version };
  }

  // Descargar no interrumpe a nadie: se hace haya o no trabajo vivo.
  if (input.available) return { kind: "download", version: input.available.version };

  return { kind: "check" };
}

/** Marcadores que delatan una configuración sin rellenar. */
const PLACEHOLDERS = ["change-me", "changeme", "example.com", "localhost", "TODO"];

/**
 * De dónde se acepta una actualización.
 *
 * Exige `https`: un canal por `http` deja que cualquiera en la red entregue el
 * binario que se va a ejecutar en la máquina del partner. Y rechaza un destino
 * a medio configurar, por la misma razón por la que `config.py` rechaza un
 * secreto que todavía dice `change-me`: un defecto de plantilla que llega a
 * producción no avisa, y aquí lo que llega es código.
 */
export function feedIsAcceptable(feed: string): boolean {
  if (!feed) return false;
  let url: URL;
  try {
    url = new URL(feed);
  } catch {
    return false;
  }
  if (url.protocol !== "https:") return false;
  const haystack = feed.toLowerCase();
  return !PLACEHOLDERS.some((marker) => haystack.includes(marker.toLowerCase()));
}

/**
 * El requisito de firma que este binario tiene que satisfacer para aceptar una
 * actualización: **firmado por Apple y con nuestro equipo en la hoja**.
 *
 * Comprobar la propia firma antes de actualizarse no es paranoia: si una copia
 * manipulada pudiera hablar con el canal, el canal dejaría de ser el único
 * camino. El texto sale de aquí —y no de una constante suelta en el pegamento—
 * para que se pueda leer y probar sin arrancar Electron.
 */
export function developerIdRequirement(teamId: string): string {
  return `anchor apple generic and certificate leaf[subject.OU] = "${teamId}"`;
}
