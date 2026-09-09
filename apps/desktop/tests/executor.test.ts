/**
 * Techos de ejecución — Requisito 12.
 *
 * En macOS y Windows no hay cgroups, y el propio sustrato avisa de que ahí no
 * impone techos de fork-bomb ni de memoria. Así que los pone el producto.
 *
 * Dos límites distintos a propósito: **un proceso que tarda no es un proceso
 * colgado**. El absoluto caza al que se desboca; el de inactividad caza al que
 * se quedó esperando algo que no va a llegar. Con un solo número habría que
 * elegir entre matar builds legítimos o no cazar cuelgues nunca.
 *
 * Se usa `/bin/sh` para montar árboles de procesos. En producción no estaría en
 * ninguna lista blanca, pero un programa que sí lo esté —`npm`, `make`— lanza
 * hijos igual, y es ese árbol el que hay que recoger.
 */
import { describe, expect, it } from "vitest";

import { runContained } from "../src/executor.js";

const alive = (pid: number) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

describe("límite absoluto de reloj (12.1, 12.2)", () => {
  it("un comando que termina a tiempo se completa", async () => {
    const result = await runContained({
      executable: "/bin/sh",
      args: ["-c", "exit 0"],
      cwd: process.cwd(),
      timeoutMs: 5_000,
    });
    expect(result.outcome).toBe("completada");
    expect(result.exitCode).toBe(0);
  });

  it("un comando que no termina se corta al vencer el límite", async () => {
    const result = await runContained({
      executable: "/bin/sh",
      args: ["-c", "sleep 30"],
      cwd: process.cwd(),
      timeoutMs: 300,
    });
    expect(result.outcome).toBe("expirada");
  });

  it("el código de salida real llega cuando lo hay", async () => {
    const result = await runContained({
      executable: "/bin/sh",
      args: ["-c", "exit 7"],
      cwd: process.cwd(),
      timeoutMs: 5_000,
    });
    expect(result.exitCode).toBe(7);
  });
});

describe("el árbol entero, no solo el padre (12.2, 12.3)", () => {
  it("los hijos que sobreviven al padre se recogen", async () => {
    const result = await runContained({
      executable: "/bin/sh",
      args: ["-c", "sleep 30 & sleep 30 & echo $!; wait"],
      cwd: process.cwd(),
      timeoutMs: 400,
    });
    expect(result.outcome).toBe("expirada");
    expect(result.childrenReaped).toBeGreaterThan(0);
    // El nieto que el padre dejó atrás tampoco sigue vivo.
    const straggler = Number.parseInt(result.stdoutSample.trim(), 10);
    if (Number.isFinite(straggler)) {
      await new Promise((r) => setTimeout(r, 150));
      expect(alive(straggler)).toBe(false);
    }
  });
});

describe("límite de inactividad (12.5)", () => {
  it("un proceso que no dice nada durante demasiado tiempo se considera colgado", async () => {
    const result = await runContained({
      executable: "/bin/sh",
      args: ["-c", "sleep 30"],
      cwd: process.cwd(),
      timeoutMs: 30_000,
      idleTimeoutMs: 300,
    });
    expect(result.outcome).toBe("terminada");
  });

  it("un proceso lento pero vivo NO se mata por inactividad", async () => {
    const result = await runContained({
      executable: "/bin/sh",
      args: ["-c", "for i in 1 2 3 4 5; do echo tic; sleep 0.1; done"],
      cwd: process.cwd(),
      timeoutMs: 30_000,
      idleTimeoutMs: 400,
    });
    expect(result.outcome).toBe("completada");
  });
});

describe("la salida no se guarda (§III, Requisito 8)", () => {
  it("solo se conserva una muestra acotada, no la transcripción", async () => {
    const result = await runContained({
      executable: "/bin/sh",
      args: ["-c", "for i in $(seq 1 5000); do echo linea-larguisima-$i; done"],
      cwd: process.cwd(),
      timeoutMs: 10_000,
    });
    expect(result.stdoutSample.length).toBeLessThanOrEqual(2048);
  });
});
