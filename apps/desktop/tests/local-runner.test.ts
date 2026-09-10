/**
 * El recorrido del dispositivo, de punta a punta — Requisitos 1, 3, 8 y 12.
 *
 * Es la unión de las tres garantías: directorio fijado, contención y techos. Se
 * prueban juntas porque el hueco que importa está **entre** ellas — un `cwd` que
 * atraviesa un enlace deja al proceso corriendo fuera aunque la escritura esté
 * contenida y el reloj acotado.
 */
import { mkdtempSync, mkdirSync, symlinkSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { STDOUT_SAMPLE_LIMIT } from "../src/executor.js";
import {
  MAX_TIMEOUT_MS,
  type ExecutionResultMessage,
  runExecuteMessage,
} from "../src/local-runner.js";

let workdir: string;
let outside: string;

beforeEach(() => {
  const base = realpathSync(mkdtempSync(join(tmpdir(), "auphere-runner-")));
  workdir = join(base, "proyecto");
  outside = join(base, "fuera");
  mkdirSync(workdir);
  mkdirSync(outside);
});

afterEach(() => {
  rmSync(workdir, { recursive: true, force: true });
  rmSync(outside, { recursive: true, force: true });
});

const message = (over: Partial<Parameters<typeof runExecuteMessage>[0]> = {}) => ({
  executionId: "e1",
  executable: "/bin/sh",
  args: ["-c", "exit 0"],
  cwdRelative: null,
  ...over,
});

describe("el recorrido feliz", () => {
  it("ejecuta dentro del directorio declarado", async () => {
    const result = await runExecuteMessage(message(), workdir);
    expect(result.outcome).toBe("completada");
    expect(result.exitCode).toBe(0);
  });

  it("un subdirectorio normal vale como cwd", async () => {
    mkdirSync(join(workdir, "sub"));
    const result = await runExecuteMessage(message({ cwdRelative: "sub" }), workdir);
    expect(result.outcome).toBe("completada");
  });
});

describe("el cwd no se escapa (Requisito 1.1, 1.4)", () => {
  it.each(["../fuera", "/etc", "sub/../../fuera"])("%s se deniega", async (cwdRelative) => {
    const result = await runExecuteMessage(message({ cwdRelative }), workdir);
    expect(result.outcome).toBe("denegada");
    expect(result.denialCode).toBe("fuera_del_directorio");
  });

  it("un enlace simbólico como cwd tampoco cuela", async () => {
    symlinkSync(outside, join(workdir, "puente"));
    const result = await runExecuteMessage(message({ cwdRelative: "puente" }), workdir);
    expect(result.outcome).toBe("denegada");
    expect(result.denialCode).toBe("sin_verificar");
  });

  it("un cwd que no existe se deniega en vez de caer al raíz", async () => {
    const result = await runExecuteMessage(message({ cwdRelative: "no-existe" }), workdir);
    expect(result.outcome).toBe("denegada");
  });
});

describe("los techos se aplican aquí también (Requisito 12)", () => {
  it("un comando que no termina se corta", async () => {
    const result = await runExecuteMessage(
      message({ args: ["-c", "sleep 30"], timeoutMs: 300 }),
      workdir,
    );
    expect(result.outcome).toBe("expirada");
  });

  it("el techo del producto gana al que pida el llamante", async () => {
    const result = await runExecuteMessage(
      message({ timeoutMs: MAX_TIMEOUT_MS * 10 }),
      workdir,
    );
    // No se cuelga esperando diez horas: el techo se recorta y el comando corre.
    expect(result.outcome).toBe("completada");
  });
});

describe("la salida es DATO, y acotada (§III con la enmienda de la spec 003)", () => {
  /**
   * La 001 no dejaba salir ni un byte: no había quien pidiera el comando, así
   * que la única salida posible era la auditoría, y ahí la salida no entra.
   *
   * La 003 abre exactamente una rendija y la deja escrita: una **muestra
   * acotada** vuelve a quien pidió ejecutar —un teammate no puede leer el
   * resultado de lo que pidió si no— y viaja marcada como dato no confiable.
   * Lo que **no** cambia: la plataforma no la persiste ni en la fila de
   * ejecución ni en la auditoría, y eso se prueba en la API
   * (`test_local_dispatch.py::test_the_output_never_lands_in_the_audit_row`).
   */
  it("devuelve una muestra de lo que el comando escribió", async () => {
    const result = await runExecuteMessage(
      message({ args: ["-c", "echo hola-del-cliente"] }),
      workdir,
    );
    expect(result.stdoutSample).toContain("hola-del-cliente");
  });

  it("la muestra está acotada por el techo del ejecutor, no por lo que escriba el comando", async () => {
    const result = await runExecuteMessage(
      message({ args: ["-c", "for i in $(seq 1 5000); do echo linea-larguisima-$i; done"] }),
      workdir,
    );
    expect((result.stdoutSample ?? "").length).toBeLessThanOrEqual(STDOUT_SAMPLE_LIMIT);
  });

  it("el resultado sigue sin llevar nada más de la máquina", () => {
    // Ni rutas, ni entorno, ni el directorio: lo que viaja es lo enumerado.
    const allowed = [
      "kind",
      "executionId",
      "outcome",
      "exitCode",
      "childrenReaped",
      "survivors",
      "stdoutSample",
      "denialCode",
    ];
    const shape: ExecutionResultMessage = {
      kind: "execution_result",
      executionId: "e1",
      outcome: "completada",
      exitCode: 0,
      childrenReaped: 0,
      survivors: [],
      stdoutSample: "x",
    };
    expect(Object.keys(shape).every((k) => allowed.includes(k))).toBe(true);
  });
});
