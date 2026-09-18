/**
 * Requisito 10.4 — al llegar desde un aviso del sistema, la decisión que lo
 * produjo **se ve y tiene el foco**.
 *
 * Lo que pasaba (anexo 04, `main.ts:344-348`): el clic llevaba a Pendientes y
 * **no restauraba la ventana**. Con la ventana oculta —que desde R3.5 es lo
 * normal al cerrarla— no ocurría nada visible en absoluto. Y aun apareciendo,
 * la lista se abría por el principio: con nueve tarjetas, encontrar la del
 * aviso era cosa tuya.
 *
 * Es un test estructural sobre el pegamento del proceso principal; lo que se
 * ve en pantalla se comprueba en `inbox-context.test.tsx`.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const MAIN = readFileSync(join(HERE, "..", "src", "electron", "main.ts"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/.*$/gm, "");

/** Lo que hace el clic de un aviso, entero. */
const alPulsar = MAIN.slice(MAIN.indexOf("applyNotificationEffects("), MAIN.indexOf("rememberNotificationAttempt,"));

describe("el aviso trae la ventana al frente", () => {
  it("la muestra, que es lo que faltaba con la ventana oculta", () => {
    expect(alPulsar).toMatch(/window\.show\(\)/);
  });

  it("y la pone delante de la aplicación que tenga el foco", () => {
    // En macOS `show()` no roba el foco a otra aplicación: eso es `app.focus`.
    expect(alPulsar).toMatch(/app\.focus\(\{ steal: true \}\)/);
  });

  it("lleva a Pendientes, que es donde vive lo que lo produjo", () => {
    expect(alPulsar).toMatch(/showSection\("pendientes"\)/);
  });

  it("y dice **cuál**: sin eso la lista se abre por el principio", () => {
    expect(alPulsar).toMatch(/app:inbox\.focus/);
    expect(alPulsar).toMatch(/action_id: actionId/);
  });
});

describe("y el orden importa", () => {
  it("primero se ve la ventana, después se elige la sección", () => {
    // Al revés, la sección cambia sobre una ventana que nadie está mirando y
    // el armazón mide el panel con la ventana todavía oculta.
    expect(alPulsar.indexOf("window.show()")).toBeLessThan(alPulsar.indexOf('showSection("pendientes")'));
  });
});
