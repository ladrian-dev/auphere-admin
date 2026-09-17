/**
 * Requisitos 1.7 y 1.9 — el menú es el índice de lo que la aplicación hace, y
 * los atajos del sistema se respetan.
 *
 * Dos cosas que se degradan solas si nadie las vigila:
 *
 * 1. **un atajo estándar reasignado** deja a la persona con una aplicación que
 *    responde distinto a lo que responde el resto del sistema operativo, que es
 *    peor que no tener atajo;
 * 2. **una acción sin orden de menú** es una acción que sólo conoce quien la
 *    escribió: el menú es donde se descubren, y donde llega quien no usa ratón.
 *
 * Es un test estructural sobre la plantilla del menú —construirla de verdad
 * exigiría Electron— y se declara como tal.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { MENU_CATALOGUES, menuCopy } from "../src/menu-copy.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const MAIN = readFileSync(join(HERE, "..", "src", "electron", "main.ts"), "utf8");

/** Los aceleradores que la plantilla del menú declara. */
function accelerators(): string[] {
  return [...MAIN.matchAll(/accelerator:\s*"([^"]+)"/g)].map((m) => m[1]!);
}

describe("los atajos del sistema no se reutilizan para otra cosa", () => {
  const usados = accelerators();

  it("los que la aplicación declara tienen el significado que el sistema les da", () => {
    // ⌘, son los ajustes y ⌘N es «nuevo»: es lo que hacen aquí. Lo que no puede
    // pasar es que ⌘W cierre otra cosa o que ⌘Q haga algo distinto de salir.
    const esperados = new Set(["CommandOrControl+,", "CommandOrControl+N", "CommandOrControl+B"]);
    for (const atajo of usados) {
      expect(esperados.has(atajo), `${atajo} no está entre los previstos`).toBe(true);
    }
  });

  it("no se reasignan los reservados del sistema", () => {
    const reservados = ["CommandOrControl+W", "CommandOrControl+Q", "CommandOrControl+M", "CommandOrControl+H"];
    for (const reservado of reservados) {
      expect(usados, `${reservado} está reasignado`).not.toContain(reservado);
    }
  });

  it("ya no existen los de cambiar de superficie", () => {
    // ⌘1 y ⌘2 cambiaban entre «Equipo» y «Consola». Esa distinción desaparece
    // para la persona con la spec 010: ahora se eligen secciones.
    expect(usados).not.toContain("CommandOrControl+1");
    expect(usados).not.toContain("CommandOrControl+2");
    expect(MAIN).not.toMatch(/label: "Consola"/);
  });
});

describe("todo lo del armazón tiene su orden de menú", () => {
  it("las órdenes que la guía de escritorio pide están en la plantilla", () => {
    for (const clave of ["settings", "checkUpdates", "toggleSidebar", "zoomIn", "zoomOut", "zoomReset", "fullscreen", "newTeammate"] as const) {
      expect(MAIN, `falta la orden ${clave}`).toMatch(new RegExp(`m\\.${clave}\\b`));
    }
  });

  it("y los menús que siempre tienen que estar, también", () => {
    expect(MAIN).toMatch(/role: "windowMenu"/);
    expect(MAIN).toMatch(/role: "help"/);
  });
});

describe("el menú habla el idioma de la cuenta (12.2)", () => {
  it("las dos lenguas tienen exactamente las mismas claves", () => {
    expect(Object.keys(MENU_CATALOGUES.es).sort()).toEqual(Object.keys(MENU_CATALOGUES.en).sort());
  });

  it("ninguna entrada se quedó sin traducir", () => {
    for (const [clave, texto] of Object.entries(MENU_CATALOGUES.en)) {
      expect(texto, `«${clave}» sigue en español`).not.toBe(MENU_CATALOGUES.es[clave as keyof typeof MENU_CATALOGUES.es]);
    }
  });

  it("y se elige por idioma, con el español como recurso", () => {
    expect(menuCopy("en").view).toBe("View");
    expect(menuCopy("es").view).toBe("Ver");
  });
});
