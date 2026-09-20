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
 *
 * **Por qué la muestra son los dos flujos y las dos puntas.** La primera
 * versión recogía solo stdout y solo el principio, y las dos mitades del error
 * se caían por ahí: `make`, `tsc` y `npm test` escriben el motivo del fallo en
 * **stderr**, y cuando la salida es larga lo que importa está **al final** —el
 * principio es el banner de la herramienta—. El agente recibía «código 1» y un
 * encabezado, que no da para arreglar nada: da para adivinar.
 *
 * Sigue siendo una muestra acotada: cabe un error dentro, no un `find /`.
 */
import { spawn } from "node:child_process";

/**
 * Cuánto se conserva. Suficiente para que quepa una traza de compilación
 * entera; demasiado poco para ser la transcripción de nada.
 */
export const OUTPUT_SAMPLE_LIMIT = 16_384;

/** @deprecated El nombre de cuando la muestra era solo stdout. */
export const STDOUT_SAMPLE_LIMIT = OUTPUT_SAMPLE_LIMIT;

const HALF = OUTPUT_SAMPLE_LIMIT / 2;

const mark = (omitted: number) => `\n… [recortado: ${omitted} caracteres omitidos] …\n`;

/**
 * Las dos puntas, con el hueco **dicho**. Callarlo sería peor que recortar: el
 * modelo leería el trozo como si fuera la salida entera y sacaría conclusiones
 * de un final que no ocurrió.
 *
 * La marca cuenta **dentro** del techo, no encima: así `OUTPUT_SAMPLE_LIMIT` es
 * el tamaño de lo que sale de aquí, y no hay que acordarse de sumarle un margen
 * en cada sitio por donde pasa después.
 */
export function clampSample(full: string): string {
  if (full.length <= OUTPUT_SAMPLE_LIMIT) return full;
  // Cota superior de la marca: su número nunca es mayor que la salida entera.
  const budget = OUTPUT_SAMPLE_LIMIT - mark(full.length).length;
  const head = Math.ceil(budget / 2);
  const tail = budget - head;
  return full.slice(0, head) + mark(full.length - budget) + full.slice(-tail);
}

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

    // Los dos flujos, en el orden en que llegan, que es lo que vería la
    // persona en su terminal. Se acumula entero y se recorta **al final**:
    // recortar sobre la marcha tiraría precisamente el desenlace.
    const collect = (chunk: Buffer) => {
      touchIdle();
      sample += chunk.toString();
      // Techo de memoria, muy por encima de la muestra: un comando que escupe
      // gigabytes no puede tumbar la aplicación mientras esperamos su final.
      if (sample.length > OUTPUT_SAMPLE_LIMIT * 8) {
        sample = sample.slice(0, HALF) + sample.slice(-(OUTPUT_SAMPLE_LIMIT * 4));
      }
    };
    child.stdout?.on("data", collect);
    child.stderr?.on("data", collect);

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

      resolve({
        outcome,
        exitCode,
        childrenReaped: reaped,
        // El nombre de cable se queda: `stdout_sample` ya es contrato con el
        // puente y con el panel de entorno. Lo que cambia es qué lleva dentro.
        stdoutSample: clampSample(sample),
        survivors,
      });
    };

    child.on("error", () => finish(null));
    child.on("close", (code) => finish(code));
  });
}
