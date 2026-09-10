/**
 * Requisitos 12.7 y 14.1 — ninguna ventana de la aplicación sin barra de direcciones.
 */
import { describe, expect, it } from "vitest";

import { decideWindowOpen, navigationAllowed } from "../src/window-open-policy.js";

const CONSOLE = "https://console.auphere.com";

describe("window.open dentro de la cáscara", () => {
  it("una https ajena se abre en el navegador del sistema, nunca en la app", () => {
    expect(decideWindowOpen("https://business.facebook.com/x", CONSOLE)).toEqual({
      action: "open_external",
      url: "https://business.facebook.com/x",
    });
  });

  it("el propio origen de la consola también sale fuera: la ventana es una sola", () => {
    expect(decideWindowOpen(`${CONSOLE}/clients/x`, CONSOLE).action).toBe("open_external");
  });

  it("http, file, javascript y basura se deniegan", () => {
    for (const bad of ["http://evil.example", "file:///etc/passwd", "javascript:alert(1)", "no es una url"]) {
      expect(decideWindowOpen(bad, CONSOLE)).toEqual({ action: "deny" });
    }
  });
});

describe("navegación de la vista de la consola", () => {
  it("solo dentro del origen de la consola", () => {
    expect(navigationAllowed(`${CONSOLE}/login`, CONSOLE)).toBe(true);
    expect(navigationAllowed("https://otro.example/", CONSOLE)).toBe(false);
    expect(navigationAllowed("garbage", CONSOLE)).toBe(false);
  });
});
