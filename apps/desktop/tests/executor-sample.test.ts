/**
 * La muestra tiene que servir para diagnosticar — Requisito 12, segunda mitad.
 *
 * El ejecutor recogía **solo stdout** y **solo los primeros 2 KB**. Las dos
 * decisiones juntas dejaban fuera justo lo que hace falta:
 *
 * - un `make`, un `npm test` o un `tsc` que fallan escriben el motivo por
 *   **stderr**, que no se recogía en absoluto — `child.stderr` solo servía para
 *   reiniciar el reloj de inactividad;
 * - y cuando la salida es larga, lo que importa está **al final**, no en los
 *   primeros 2 KB, que son el banner de la herramienta.
 *
 * El agente recibía «salió con código 1» y el principio de un banner. Con eso
 * no se arregla nada: se adivina.
 *
 * Sigue siendo una **muestra acotada y no persistida** (§III). Lo que cambia es
 * que ahora cabe un error dentro.
 */
import { describe, expect, it } from "vitest";

import { OUTPUT_SAMPLE_LIMIT, runContained } from "../src/executor.js";

const sh = (script: string) => ({
  executable: "/bin/sh",
  args: ["-c", script],
  cwd: process.cwd(),
  timeoutMs: 10_000,
});

describe("stderr es la mitad que faltaba", () => {
  it("recoge lo que el programa escribe en stderr", async () => {
    const r = await runContained(sh("echo 'error: undeclared' 1>&2; exit 1"));

    expect(r.exitCode).toBe(1);
    expect(r.stdoutSample).toContain("undeclared");
  });

  it("conserva los dos flujos, no uno u otro", async () => {
    const r = await runContained(sh("echo salida-normal; echo salida-de-error 1>&2"));

    expect(r.stdoutSample).toContain("salida-normal");
    expect(r.stdoutSample).toContain("salida-de-error");
  });
});

describe("cuando la salida es larga, se conserva el final", () => {
  it("el final sobrevive: es donde está el motivo del fallo", async () => {
    // Mucho ruido y, al final, la línea que importa.
    const r = await runContained(
      sh("for i in $(seq 1 4000); do echo 'compilando modulo ruidoso'; done; echo 'FALLO: symbol not found' 1>&2"),
    );

    expect(r.stdoutSample.length).toBeGreaterThan(2048);
    expect(r.stdoutSample).toContain("FALLO: symbol not found");
  });

  it("y no crece sin límite", async () => {
    const r = await runContained(sh("for i in $(seq 1 20000); do echo 'ruido ruido ruido'; done"));

    expect(r.stdoutSample.length).toBeLessThanOrEqual(OUTPUT_SAMPLE_LIMIT);
  });

  it("dice que ha recortado, en vez de fingir que eso es todo", async () => {
    const r = await runContained(sh("for i in $(seq 1 20000); do echo 'ruido ruido ruido'; done"));

    expect(r.stdoutSample).toMatch(/recortad|omitid|…/i);
  });
});
