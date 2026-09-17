/**
 * Requisito 3.5 — cerrar la ventana no es salir.
 *
 * La contradicción era visible en la propia pantalla: el hilo vacío dice «lo
 * que le pidas sigue aunque cierres la aplicación» y, al cerrar la ventana, la
 * aplicación se cerraba entera — con ella el icono de la barra del sistema, los
 * avisos de las decisiones pendientes y el puente. Una de las dos cosas mentía.
 *
 * En macOS, además, cerrar la ventana y salir son dos gestos distintos que la
 * gente usa a propósito. Aquí se comprueba la decisión sobre el arranque, que
 * es donde vive: es un test estructural y se declara como tal.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const FUENTE = readFileSync(join(HERE, "..", "src", "electron", "main.ts"), "utf8");
/** Sin comentarios: aquí se cita el código viejo para explicar lo que cambió. */
const MAIN = FUENTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

describe("cerrar oculta; salir es otra cosa", () => {
  it("cerrar la última ventana ya no cierra la aplicación en macOS", () => {
    // `window-all-closed → app.quit()` es exactamente lo que se llevaba por
    // delante la bandeja y los avisos.
    expect(MAIN).not.toMatch(/window-all-closed["']?,\s*\(\)\s*=>\s*app\.quit\(\)/);
  });

  it("el cierre de la ventana se intercepta y se oculta", () => {
    expect(MAIN).toMatch(/window\.on\(\s*"close"/);
    expect(MAIN).toMatch(/window\.hide\(\)/);
  });

  it("y se puede volver a abrir desde el Dock", () => {
    expect(MAIN).toMatch(/app\.on\(\s*"activate"/);
  });
});

describe("salir es explícito, y avisa si hay trabajo vivo", () => {
  it("hay una orden de salir de verdad", () => {
    expect(MAIN).toMatch(/quitting\s*=\s*true/);
  });

  it("salir con trabajo vivo pregunta antes", () => {
    // La misma lectura que usa el actualizador para no instalar encima de una
    // decisión sin tomar: sesiones en vuelo y decisiones sin tomar.
    const salir = MAIN.slice(MAIN.indexOf("function quitWithWarning"));
    expect(salir).toMatch(/liveSessions/);
    expect(salir).toMatch(/pendingApprovals/);
    expect(salir).toMatch(/showMessageBoxSync/);
  });

  it("y si la persona se echa atrás, no se sale", () => {
    const salir = MAIN.slice(MAIN.indexOf("function quitWithWarning"));
    // El botón por defecto es cancelar: salir por costumbre no puede llevarse
    // por delante una decisión sin tomar.
    expect(salir).toMatch(/defaultId:\s*0/);
    expect(salir).toMatch(/cancelId:\s*0/);
  });
});
