/**
 * La puesta en marcha — spec 010, Requisitos 7.6 y 7.7.
 *
 * **Derivada, no almacenada.** Cada paso sale de algo que la aplicación ya
 * sabe: si hay sesión, cómo está el puesto, cuántos teammates hay, si alguno
 * terminó un turno, si se concedieron los avisos. Un campo «pasos completados»
 * guardado en algún sitio se desincroniza el primer día —alguien desempareja la
 * máquina y la lista sigue diciendo que está— y a partir de ahí la lista miente,
 * que es lo peor que puede hacer una lista de comprobación.
 *
 * Lo que arregla, con nombre: la consola ya tiene una tarjeta «Tu puesto de
 * trabajo · 0 de 4 pasos» cuyos pasos enlazan **todos a la misma página**, que
 * es la que ya estás mirando. Aquí cada paso lleva a donde se hace, o dice por
 * qué está bloqueado y lleva a donde se desbloquea.
 *
 * **No bloquea nada.** Es una lectura: se puede trabajar con pasos a medias, y
 * la lista está accesible en todo momento en vez de ser un muro al arrancar.
 */

export const SETUP_STEPS = [
  "cuenta_lista",
  "maquina_emparejada",
  "ejecutor_presente",
  "primer_teammate",
  "primer_turno",
  "avisos_concedidos",
] as const;
export type SetupStepKey = (typeof SETUP_STEPS)[number];

/** A dónde lleva un paso. Son secciones del armazón, no rutas sueltas. */
export type SetupSection = "cuenta" | "puesto" | "teammate" | "hoy";

export type SetupStep = {
  key: SetupStepKey;
  /** `no_aplica` = todavía no tiene sentido preguntarlo, no «lo saltaste». */
  state: "hecho" | "pendiente" | "no_aplica";
  section?: SetupSection;
  /** Por qué no se puede ahora mismo. Sin esto, un paso parado no se explica. */
  blocked_reason_key?: string;
};

export type SetupFacts = {
  signedIn: boolean;
  hasPartner: boolean;
  /** El estado del puesto, tal cual. No una copia con otro nombre. */
  workstation: string;
  executorPresent: boolean;
  teammates: number;
  finishedTurns: number;
  notificationsGranted: boolean;
  /** El plan admite al menos un teammate. Si no, crear el primero no va. */
  planAllowsTeammates: boolean;
};

const PAIRED = new Set(["conectada", "reconectando", "version_no_admitida"]);

export function deriveSetup(f: SetupFacts): SetupStep[] {
  const paired = PAIRED.has(f.workstation);
  const done = (key: SetupStepKey): SetupStep => ({ key, state: "hecho" });

  const steps: SetupStep[] = [];

  steps.push(
    f.signedIn && f.hasPartner ? done("cuenta_lista") : { key: "cuenta_lista", state: "pendiente", section: "cuenta" },
  );

  steps.push(
    paired ? done("maquina_emparejada") : { key: "maquina_emparejada", state: "pendiente", section: "puesto" },
  );

  // Preguntar por el ejecutor en una máquina sin emparejar es pedir algo que
  // todavía no tiene sentido. No es un paso saltado: es uno que no aplica.
  steps.push(
    !paired
      ? { key: "ejecutor_presente", state: "no_aplica" }
      : f.executorPresent
        ? done("ejecutor_presente")
        : { key: "ejecutor_presente", state: "pendiente", section: "puesto" },
  );

  steps.push(
    f.teammates > 0
      ? done("primer_teammate")
      : f.planAllowsTeammates
        ? { key: "primer_teammate", state: "pendiente", section: "teammate" }
        : // Bloqueado lleva a donde se **resuelve** (el plan), no a donde se
          // descubre (el formulario que va a rechazarlo).
          { key: "primer_teammate", state: "pendiente", section: "cuenta", blocked_reason_key: "setup.blocked.plan" },
  );

  steps.push(
    f.teammates === 0
      ? { key: "primer_turno", state: "no_aplica" }
      : f.finishedTurns > 0
        ? done("primer_turno")
        : { key: "primer_turno", state: "pendiente", section: "teammate" },
  );

  steps.push(
    f.notificationsGranted
      ? done("avisos_concedidos")
      : { key: "avisos_concedidos", state: "pendiente", section: "cuenta" },
  );

  return steps;
}

/** Lo que falta de verdad. `no_aplica` no cuenta: no es deuda de nadie. */
export function pendingSteps(steps: readonly SetupStep[]): SetupStep[] {
  return steps.filter((s) => s.state === "pendiente");
}
