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

import { MAX_TIMEOUT_MS, runExecuteMessage } from "../src/local-runner.js";

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

describe("la salida no viaja (§III)", () => {
  it("el resultado dice qué pasó, no qué dijo el comando", async () => {
    const result = await runExecuteMessage(
      message({ args: ["-c", "echo secreto-del-cliente"] }),
      workdir,
    );
    expect(JSON.stringify(result)).not.toContain("secreto-del-cliente");
    expect(Object.keys(result)).not.toContain("stdoutSample");
  });
});
