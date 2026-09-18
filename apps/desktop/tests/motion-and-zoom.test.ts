/**
 * Requisito 11 — movimiento reducido y zoom del contenido.
 *
 * Dos cosas que se degradan solas si nadie las vigila:
 *
 * * **`prefers-reduced-motion`**. Quien lo activa no lo hace por gusto: hay
 *   personas a las que una animación les produce mareo. Una sola clase de
 *   animación sin guardar es suficiente para arruinarlo;
 * * **el zoom del contenido al 200 %** (WCAG 1.4.4). En una aplicación de
 *   escritorio no hay barra del navegador donde ampliar: si la aplicación no lo
 *   ofrece en su menú, no existe.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { readdirSync, statSync } from "node:fs";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "src");

/** Todos los `.tsx` de la pantalla. */
function vistas(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return vistas(full);
    return name.endsWith(".tsx") ? [full] : [];
  });
}

describe("nada se mueve si la persona pidió que no (2.3.3)", () => {
  it("ninguna animación va sin su guarda", () => {
    const sueltas: string[] = [];
    for (const fichero of vistas(join(SRC, "app"))) {
      const codigo = readFileSync(fichero, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
      // `animate-*` sin `motion-safe:` delante se ejecuta siempre.
      for (const match of codigo.matchAll(/(\S*)animate-[a-z-]+/g)) {
        if (!match[1]?.endsWith("motion-safe:")) sueltas.push(`${fichero}: ${match[0]}`);
      }
    }
    expect(sueltas, `animaciones sin guarda:\n${sueltas.join("\n")}`).toHaveLength(0);
  });

  it("y los tokens lo apagan en un solo sitio, para las tres superficies", () => {
    // Vive en `@nexus/ui`, que es lo que comparten la pantalla, la consola y el
    // panel: repetirlo por superficie es cómo una se queda sin la guarda.
    const tokens = readFileSync(join(SRC, "..", "..", "..", "packages", "ui", "src", "styles", "tokens.css"), "utf8");
    expect(tokens).toMatch(/prefers-reduced-motion/);
  });
});

describe("el contenido se amplía desde el menú (1.4.4)", () => {
  const MAIN = readFileSync(join(SRC, "electron", "main.ts"), "utf8");

  it("hay órdenes de aumentar, reducir y volver al tamaño real", () => {
    for (const orden of ["zoomIn", "zoomOut", "zoomReset"]) {
      expect(MAIN, `falta ${orden}`).toMatch(new RegExp(`m\\.${orden}\\b`));
    }
  });

  it("y amplían **las dos vistas**, no sólo la que tiene el foco", () => {
    // Los `role` de Electron amplían el `webContents` enfocado. Con el armazón
    // y la consola en la misma ventana, eso deja la mitad pequeña.
    expect(MAIN).toMatch(/setZoomLevel/);
    const bloque = MAIN.slice(MAIN.indexOf("const applyZoom"));
    expect(bloque.slice(0, 400)).toMatch(/appView/);
    expect(bloque.slice(0, 400)).toMatch(/consoleView/);
  });
});
