/**
 * Requisito 15.4 y 4.3 — sin puente, `reconectando` y sin herramientas locales.
 *
 * El estado ya lo calculaba `OutboundBridge`, pero **no tenía pantalla donde
 * vivir**: por eso T050 quedó a medias. Aquí se le da su sitio y se ata a la
 * consecuencia que importa — mientras el puente no está, las herramientas locales
 * **no se ofrecen**. Un catálogo que las ofrece cuando no hay puente invita al
 * agente a afirmar resultados de comandos que nunca corrieron.
 */
import { describe, expect, it } from "vitest";

import { localToolsAvailable, statusLabel } from "../src/link-state.js";

describe("lo que se muestra (15.4)", () => {
  it("conectando y reconectando son estados, no errores", () => {
    expect(statusLabel("conectando").tone).toBe("estado");
    expect(statusLabel("reconectando").tone).toBe("estado");
  });

  it("`reconectando` se distingue del primer arranque", () => {
    expect(statusLabel("reconectando").key).not.toBe(statusLabel("conectando").key);
  });

  it("ningún estado del puente se pinta como error", () => {
    for (const s of ["conectando", "conectado", "reconectando"] as const) {
      expect(statusLabel(s).tone).not.toBe("error");
    }
  });
});

describe("y lo que se puede hacer mientras tanto (4.2, 15.4)", () => {
  it("sin puente no hay herramientas locales", () => {
    expect(localToolsAvailable("conectando", "presente")).toBe(false);
    expect(localToolsAvailable("reconectando", "presente")).toBe(false);
  });

  it("con puente pero sin dispositivo, tampoco", () => {
    expect(localToolsAvailable("conectado", "ausente")).toBe(false);
  });

  it("hacen falta las dos cosas", () => {
    expect(localToolsAvailable("conectado", "presente")).toBe(true);
  });
});
