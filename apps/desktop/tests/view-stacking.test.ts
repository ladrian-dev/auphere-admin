/**
 * Requisito 1.3 — la consola se pinta **dentro del panel**, y se ve.
 *
 * Éste es el fallo de la 0.1.4, y merece estar escrito entero porque no se
 * parecía a un fallo: se parecía a una pantalla vacía.
 *
 * `addChildView` apila las vistas, y el último va encima. Hasta la spec 010 el
 * armazón iba arriba y **daba igual**, porque `showSurface` ocultaba la
 * pantalla al enseñar la consola: se veía una superficie o la otra.
 *
 * La spec 010 cambió las dos mitades de esa frase —la pantalla pasó a ocupar la
 * ventana entera y a **no ocultarse nunca**— y no tocó el orden. Resultado: la
 * consola quedaba debajo de un armazón opaco de pantalla completa. El panel se
 * veía **negro**, sin banda de error y sin nada que pulsar, porque el armazón no
 * pinta ahí a propósito (`panelBelongsToConsole`). Todas las pruebas en verde:
 * ninguna miraba la profundidad.
 *
 * Es un test estructural sobre el arranque —comprobarlo de verdad exigiría
 * Electron y una ventana— y se declara como tal. Lo que vigila es el
 * invariante, no la implementación: **la consola encima, y la pantalla sin
 * ocultarse**.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
/** Sin comentarios: aquí se cita el orden viejo para explicar el cambio. */
const MAIN = readFileSync(join(HERE, "..", "src", "electron", "main.ts"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/.*$/gm, "");

describe("la consola se apila ENCIMA del armazón", () => {
  it("la pantalla se añade primero y la consola después", () => {
    const app = MAIN.indexOf("addChildView(appView)");
    const consola = MAIN.indexOf("addChildView(consoleView)");
    expect(app, "no se añade la vista de la pantalla").toBeGreaterThan(-1);
    expect(consola, "no se añade la vista de la consola").toBeGreaterThan(-1);
    expect(
      consola,
      "la consola se añade ANTES que el armazón: queda debajo y el panel se ve negro",
    ).toBeGreaterThan(app);
  });

  it("y son las dos únicas vistas: la barra ya no existe", () => {
    const vistas = [...MAIN.matchAll(/addChildView\((\w+)\)/g)].map((m) => m[1]);
    expect(vistas).toEqual(["appView", "consoleView"]);
  });
});

describe("el armazón ocupa la ventana entera y no se oculta", () => {
  it("la pantalla siempre está visible: es el marco", () => {
    expect(MAIN).toMatch(/appView\.setVisible\(true\)/);
    // `setVisible(next === "app")` es justo lo que hacía que el orden diera
    // igual, y volver a ello devolvería el fallo por el otro lado.
    expect(MAIN).not.toMatch(/appView\.setVisible\(next === "app"\)/);
  });

  it("la consola aparece y desaparece, y se coloca en el panel", () => {
    expect(MAIN).toMatch(/consoleView\.setVisible\(next === "console"\)/);
    expect(MAIN).toMatch(/if \(next === "console"\) placeConsole\(\)/);
  });

  it("y la pantalla ocupa la ventana entera, sin hueco reservado para nadie", () => {
    const disposicion = MAIN.slice(MAIN.indexOf("function layout("));
    expect(disposicion.slice(0, 300)).toMatch(/appView\.setBounds\(\{ x: 0, y: 0, width, height \}\)/);
  });
});
