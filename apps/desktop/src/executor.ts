/**
 * Ejecución acotada en la máquina del partner — Requisito 12.
 *
 * **Por qué dos límites y no uno.** Un proceso que tarda no es un proceso
 * colgado. El límite absoluto caza al que se desboca; el de inactividad caza al
 * que se quedó esperando algo que no va a llegar. Con un solo número habría que
 * elegir entre matar builds legítimos o no cazar cuelgues nunca.
 *
 * **Por qué el grupo de procesos y no el PID.** Un `npm` lanza un `node`, que
 * lanza otra cosa. Matar al padre deja el árbol vivo — y la evaluación observó
 * exactamente eso en el sustrato: *«Retained tracking for N live child PID(s)
 * that survived teardown»*. Por eso se arranca con `detached` (grupo propio) y
 * se mata el grupo entero con `kill(-pid)`.
 *
 * **Por qué no se guarda la salida.** Es contenido leído (§III) y el hilo de un
 * teammate no transcribe texto de cliente final. Se conserva una muestra acotada
 * para poder diagnosticar, no la transcripción.
 */
import { spawn } from "node:child_process";

/** Suficiente para ver qué pasó; demasiado poco para ser una transcripción. */
export const STDOUT_SAMPLE_LIMIT = 2048;

export type Outcome = "completada" | "expirada" | "terminada" | "denegada";

export type RunRequest = {
  executable: string;
  args: string[];
  cwd: string;
  /** Límite absoluto de reloj (Requisito 12.1). */
  timeoutMs: number;
  /** Sin salida durante este tiempo = colgado (Requisito 12.5). */
  idleTimeoutMs?: number;
};

export type RunResult = {
  outcome: Outcome;
  exitCode: number | null;
  childrenReaped: number;
  /** Muestra acotada. **No** es la salida del comando. */
  stdoutSample: string;
  /** Procesos que no se pudieron terminar: se **nombran** (Requisito 12.4). */
  survivors: number[];
};

function groupIsAlive(pid: number): boolean {
  try {
    process.kill(-pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** Mata el grupo entero y cuenta lo que había que recoger. */
function reapGroup(pid: number, signal: NodeJS.Signals): number {
  try {
    process.kill(-pid, signal);
    return 1;
  } catch {
    return 0;
  }
}

export async function runContained(request: RunRequest): Promise<RunResult> {
  const { executable, args, cwd, timeoutMs, idleTimeoutMs } = request;

  return await new Promise<RunResult>((resolve) => {
    const child = spawn(executable, args, {
      cwd,
      // Grupo propio: lo que se mata después es el árbol, no una hoja.
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let sample = "";
    let outcome: Outcome = "completada";
    let reaped = 0;
    let settled = false;

    const absolute = setTimeout(() => {
      outcome = "expirada";
      reaped += reapGroup(child.pid ?? 0, "SIGKILL");
    }, timeoutMs);

    let idle: NodeJS.Timeout | undefined;
    const touchIdle = () => {
      if (idleTimeoutMs === undefined) return;
      if (idle) clearTimeout(idle);
      idle = setTimeout(() => {
        outcome = "terminada";
        reaped += reapGroup(child.pid ?? 0, "SIGKILL");
      }, idleTimeoutMs);
    };
    touchIdle();

    const collect = (chunk: Buffer) => {
      touchIdle();
      if (sample.length < STDOUT_SAMPLE_LIMIT) {
        sample = (sample + chunk.toString()).slice(0, STDOUT_SAMPLE_LIMIT);
      }
    };
    child.stdout?.on("data", collect);
    child.stderr?.on("data", touchIdle);

    const finish = (exitCode: number | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(absolute);
      if (idle) clearTimeout(idle);

      // Barrido final: lo que quede del grupo se recoge aunque el padre haya
      // terminado bien. Un hijo huérfano en la máquina de otra persona no es
      // un detalle: es un proceso que nadie sabe que está ahí.
      const pid = child.pid ?? 0;
      const survivors: number[] = [];
      if (pid && groupIsAlive(pid)) {
        reaped += reapGroup(pid, "SIGKILL");
        if (groupIsAlive(pid)) survivors.push(pid);
      }

      resolve({ outcome, exitCode, childrenReaped: reaped, stdoutSample: sample, survivors });
    };

    child.on("error", () => finish(null));
    child.on("close", (code) => finish(code));
  });
}
