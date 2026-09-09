/**
 * El eslabón del dispositivo: de un mensaje `execute` a un `execution_result`.
 *
 * Aquí se juntan las tres garantías que hasta ahora vivían sueltas —el
 * directorio fijado, la contención y los techos— y esa unión es el punto:
 * cada una por separado deja un hueco que la siguiente tapa.
 *
 * **Lo que este módulo NO hace, a propósito**: no decide si el comando está
 * permitido. Eso es del gate, en la plataforma, donde está la lista blanca del
 * tenant y la aprobación durable. El dispositivo ejecuta lo que ya se decidió —
 * poner esa decisión aquí la dejaría en la máquina del partner, que es
 * exactamente donde no puede estar.
 */
import { ContainmentError, resolveDirInside } from "./containment.js";
import { runContained, type Outcome } from "./executor.js";

export const DEFAULT_TIMEOUT_MS = 600_000;
export const MAX_TIMEOUT_MS = 3_600_000;
export const DEFAULT_IDLE_TIMEOUT_MS = 300_000;

export type ExecuteMessage = {
  executionId: string;
  executable: string;
  args: string[];
  cwdRelative: string | null;
  timeoutMs?: number;
};

export type ExecutionResultMessage = {
  kind: "execution_result";
  executionId: string;
  outcome: Outcome;
  exitCode: number | null;
  childrenReaped: number;
  /** Presente solo cuando se denegó aquí. Código cerrado, no prosa. */
  denialCode?: "fuera_del_directorio" | "sin_verificar";
  survivors: number[];
};

/** El techo del tenant no puede subir por encima del techo del producto. */
function boundedTimeout(requested: number | undefined): number {
  if (requested === undefined) return DEFAULT_TIMEOUT_MS;
  return Math.min(Math.max(requested, 1), MAX_TIMEOUT_MS);
}

export async function runExecuteMessage(
  message: ExecuteMessage,
  workdir: string,
): Promise<ExecutionResultMessage> {
  let cwd: string;
  try {
    cwd = await resolveDirInside(workdir, message.cwdRelative);
  } catch (err) {
    // Falla cerrado, y distingue los dos motivos: salirse del directorio no es
    // lo mismo que no poder comprobarlo, y la auditoría quiere saber cuál fue.
    const denialCode =
      err instanceof ContainmentError && /fuera del directorio/.test(err.message)
        ? "fuera_del_directorio"
        : "sin_verificar";
    return {
      kind: "execution_result",
      executionId: message.executionId,
      outcome: "denegada",
      exitCode: null,
      childrenReaped: 0,
      denialCode,
      survivors: [],
    };
  }

  const result = await runContained({
    executable: message.executable,
    args: message.args,
    cwd,
    timeoutMs: boundedTimeout(message.timeoutMs),
    idleTimeoutMs: DEFAULT_IDLE_TIMEOUT_MS,
  });

  // La salida NO viaja: el resultado dice qué pasó, no qué dijo el comando.
  return {
    kind: "execution_result",
    executionId: message.executionId,
    outcome: result.outcome,
    exitCode: result.exitCode,
    childrenReaped: result.childrenReaped,
    survivors: result.survivors,
  };
}
