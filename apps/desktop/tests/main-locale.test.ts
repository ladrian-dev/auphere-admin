/**
 * Requisito 12.2 — **el proceso principal habla el idioma de la cuenta**.
 *
 * Es la mitad que se olvida siempre, porque no se ve en ninguna pantalla de
 * React: los menús, los diálogos nativos, el texto de la bandeja del sistema,
 * los avisos y la página de vuelta del navegador los pinta el principal, y cada
 * uno tenía su propio criterio — o ninguno.
 *
 * El síntoma que dejó la investigación: un menú en español dentro de una
 * aplicación en inglés, con etiquetas de Electron en el idioma del sistema.
 * Tres idiomas en la misma ventana.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { MENU_CATALOGUES } from "../src/menu-copy.js";
import { trayTooltip } from "../src/tray-badge.js";
import { returnPage } from "../src/loopback-login.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const MAIN = readFileSync(join(HERE, "..", "src", "electron", "main.ts"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/.*$/gm, "");

describe("todo lo del principal pregunta por el idioma de la cuenta", () => {
  it("el menú", () => {
    expect(MAIN).toMatch(/menuCopy\(appLocale\(\)\)/);
  });

  it("los diálogos nativos: salir con trabajo vivo usa el mismo catálogo", () => {
    expect(MAIN).toMatch(/quitWithWarning\(m\)/);
  });

  it("el texto de la bandeja del sistema", () => {
    expect(MAIN).toMatch(/trayTooltip\([^)]*appLocale\(\)/);
  });

  it("los avisos del sistema", () => {
    expect(MAIN).toMatch(/lang: appLocale\(\)/);
  });

  it("y el selector nativo de carpetas", () => {
    expect(MAIN).toMatch(/menuCopy\(appLocale\(\)\)\.pickDirectory/);
  });
});

describe("y ninguna de esas piezas tiene texto suelto", () => {
  it("las dos lenguas del menú tienen exactamente las mismas claves", () => {
    expect(Object.keys(MENU_CATALOGUES.es).sort()).toEqual(Object.keys(MENU_CATALOGUES.en).sort());
  });

  it("ninguna entrada del menú se quedó sin traducir", () => {
    for (const [clave, texto] of Object.entries(MENU_CATALOGUES.en)) {
      expect(texto, `«${clave}» sigue en español`).not.toBe(
        MENU_CATALOGUES.es[clave as keyof typeof MENU_CATALOGUES.es],
      );
    }
  });

  it("la bandeja del sistema habla las dos", () => {
    const uno = [{ level: "critico" as const, can_decide: true }];
    expect(trayTooltip(uno, "es")).toMatch(/espera tu decisión/);
    expect(trayTooltip(uno, "en")).toMatch(/waiting for your decision/);
  });

  it("y la página de vuelta del navegador dice las dos a la vez", () => {
    // El navegador es de la persona: su idioma no tiene por qué ser el de la
    // cuenta, así que ahí no se elige — se dicen las dos.
    const page = returnPage(true);
    expect(page).toMatch(/volver a Auphere/);
    expect(page).toMatch(/go back to Auphere/i);
  });
});
