/**
 * Spec 078, requisito 4: después del login, el panel solo vuelve a una ruta
 * suya. `?from=` lo pone el middleware, pero cualquiera puede escribir un
 * enlace al login con el `from` que quiera.
 */
import { describe, expect, it } from "vitest";

import { safeRedirect } from "../safe-redirect";

describe("safeRedirect (spec 078, requisito 4)", () => {
  it.each([
    ["/tenants", "/tenants"],
    ["/partners/abc/money?tab=wallet", "/partners/abc/money?tab=wallet"],
    ["/tenants#top", "/tenants#top"],
  ])("deja pasar una ruta del panel: %s", (from, expected) => {
    expect(safeRedirect(from)).toBe(expected);
  });

  it.each([
    ["sin valor", undefined],
    ["vacío", ""],
    ["otro sitio con //", "//otro-sitio.example"],
    ["otro sitio con barra invertida", "/\\otro-sitio.example"],
    ["una URL absoluta", "https://otro-sitio.example/tenants"],
    ["un esquema", "javascript:alert(1)"],
    ["una ruta relativa", "tenants"],
  ])("vuelve a /tenants con %s", (_label, from) => {
    expect(safeRedirect(from)).toBe("/tenants");
  });
});
