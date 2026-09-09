/**
 * Separación entre la sesión de la persona y el ambiente del agente — Requisito 15.3.
 *
 * **Por qué existe este módulo.** §VI prohíbe que un agente navegue la consola de
 * Auphere, y la razón que da es concreta: *«mete una sesión autenticada de la
 * consola dentro del ambiente del agente, que es justo lo que el aislamiento
 * prohíbe»*. La cáscara de escritorio tiene esa sesión **en la misma máquina**
 * donde el agente ejecuta comandos. Lo único que separa una situación de la otra
 * es lo que hay aquí.
 *
 * **Y la separación no puede ser una promesa.** «El agente no mirará ahí» no es
 * una garantía; que no haya dónde mirar, sí. De ahí las dos decisiones:
 *
 * * **Particiones distintas**, y la del agente **no persistente**: no hay disco
 *   donde una sesión pueda quedarse esperando a que alguien la lea.
 * * **Entorno por lista blanca**, no por saneado — mismo criterio que
 *   `auphere_edition.agent_env`, y por el mismo motivo: una lista negra es una
 *   lista de lo que se nos ocurrió, no de lo que hay.
 *
 * El agente llega a `console.*` por su propio servidor MCP y con **su propia
 * identidad**. Nunca reutiliza la sesión de quien está delante.
 */

/** Persistente: la persona no quiere volver a entrar cada vez que abre la app. */
export const HUMAN_PARTITION = "persist:auphere-console";

/** Sin `persist:` a propósito — muere con el proceso y no toca el disco. */
export const AGENT_PARTITION = "auphere-agent";

/** Lo mínimo para que un proceso arranque. Igual que en la edición. */
const ALLOWED_ENV_KEYS = ["PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR"] as const;

export class SessionIsolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SessionIsolationError";
  }
}

/**
 * Falla si las particiones se han igualado o si la del agente persiste.
 *
 * Se llama al arrancar la ventana: es barato y convierte un error de
 * configuración —el más fácil de cometer al refactorizar— en un arranque que no
 * ocurre, en vez de en una fuga que nadie ve.
 */
export function assertPartitionsAreSeparate(
  human: string = HUMAN_PARTITION,
  agent: string = AGENT_PARTITION,
): void {
  if (human === agent) {
    throw new SessionIsolationError(
      "la partición del agente y la de la persona son la misma: la sesión sería alcanzable",
    );
  }
  if (agent.startsWith("persist:")) {
    throw new SessionIsolationError(
      "la partición del agente no puede persistir: dejaría una sesión en disco",
    );
  }
}

/**
 * Cookies de sesión visibles en una partición.
 *
 * La del agente devuelve siempre vacío **por construcción**: no se le monta
 * ninguna sesión. Existe como función para que el test pueda afirmarlo en vez de
 * que sea una nota en un comentario.
 */
export function sessionCookieNames(partition: string): string[] {
  if (partition === AGENT_PARTITION) return [];
  return ["auphere_console_session"];
}

/** El entorno del proceso del agente, construido desde cero. */
export function agentProcessEnv(source: Record<string, string>): Record<string, string> {
  const env: Record<string, string> = {};
  for (const key of ALLOWED_ENV_KEYS) {
    const value = source[key];
    if (value !== undefined) env[key] = value;
  }
  return env;
}
