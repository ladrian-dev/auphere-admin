/**
 * Requisitos 2.3 y 1.10 — un solo tema para toda la ventana, y volver donde
 * estabas.
 *
 * El defecto que esto cierra se podía ver: la pantalla y la barra seguían al
 * sistema operativo y la consola tenía su propio selector, así que dentro de la
 * misma ventana se podía tener media aplicación en claro y media en oscuro.
 *
 * Aquí se comprueba la parte que se puede comprobar sin abrir una ventana: que
 * la preferencia es **una**, que sobrevive a un fichero raro y que lo guardado
 * se acota igual que lo acota el armazón.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_SHELL_PREFS,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  mergeShellPrefs,
  normaliseShellPrefs,
} from "../src/shell-prefs.js";

describe("el tema es una sola preferencia", () => {
  it("por defecto lo decide el sistema operativo", () => {
    expect(DEFAULT_SHELL_PREFS.theme).toBe("system");
    expect(normaliseShellPrefs(undefined).theme).toBe("system");
  });

  it("acepta los tres valores y ninguno más", () => {
    for (const theme of ["system", "light", "dark"] as const) {
      expect(normaliseShellPrefs({ theme }).theme).toBe(theme);
    }
    expect(normaliseShellPrefs({ theme: "morado" }).theme).toBe("system");
    expect(normaliseShellPrefs({ theme: 3 }).theme).toBe("system");
  });

  it("elegirlo no borra lo demás", () => {
    const antes = normaliseShellPrefs({ sidebarWidth: 280, section: "consumo" });
    const despues = mergeShellPrefs(antes, { theme: "dark" });
    expect(despues).toEqual({ theme: "dark", sidebarWidth: 280, section: "consumo", silenceAviso: false });
  });
});

describe("la ventana vuelve como la dejaste (1.10)", () => {
  it("guarda la última sección", () => {
    expect(normaliseShellPrefs({ section: "facturacion" }).section).toBe("facturacion");
  });

  it("y sin nada guardado empieza en Hoy", () => {
    expect(normaliseShellPrefs({}).section).toBe("hoy");
  });
});

describe("un fichero de preferencias raro no tumba el arranque", () => {
  it("lo que no se entiende vuelve a su valor por defecto", () => {
    expect(normaliseShellPrefs("no soy un objeto")).toEqual(DEFAULT_SHELL_PREFS);
    expect(normaliseShellPrefs(null)).toEqual(DEFAULT_SHELL_PREFS);
    expect(normaliseShellPrefs({ sidebarWidth: "ancha" }).sidebarWidth).toBe(MIN_SIDEBAR_WIDTH);
  });

  it("el ancho se acota igual que lo acota el armazón", () => {
    expect(normaliseShellPrefs({ sidebarWidth: 10 }).sidebarWidth).toBe(MIN_SIDEBAR_WIDTH);
    expect(normaliseShellPrefs({ sidebarWidth: 9999 }).sidebarWidth).toBe(MAX_SIDEBAR_WIDTH);
  });

  it("cero se respeta: es la lista lateral colapsada, no un error", () => {
    expect(normaliseShellPrefs({ sidebarWidth: 0 }).sidebarWidth).toBe(0);
  });
});
