/**
 * Spec 004 · R7.2 — el panel de operador SIGUE enseñando las cifras absolutas.
 *
 * Es la mitad que se olvida. R7.1 quita la cifra del pool de la pantalla del
 * **partner**: ve una barra y una fecha, y así el tamaño del pool deja de ser
 * un compromiso público. Pero Auphere necesita el número para diagnosticar,
 * conciliar una factura y decidir precios — si se aplicara el mismo recorte
 * aquí, el recorte se comería la capacidad de operar.
 *
 * Estructural sobre el fuente y no de render: la pantalla es un server
 * component que va a buscar datos, y lo que hay que impedir es una edición
 * concreta —cambiar las cifras por un porcentaje— que un test de render no
 * distinguiría de un cambio de maquetación.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const PAGE = join(__dirname, "..", "page.tsx");

describe("panel de operador · wallet (spec 004, R7.2)", () => {
  const source = readFileSync(PAGE, "utf8");

  it("pinta el saldo incluido como cifra, no como porcentaje", () => {
    expect(source).toContain("wallet.included_remaining");
    expect(source).toMatch(/fmt\(wallet\.included_remaining\)/);
  });

  it("pinta el saldo comprado como cifra", () => {
    // R7.6: además, lo comprado NUNCA se abstrae en ninguna superficie. Es
    // dinero que el partner pagó y tiene derecho a verificar.
    expect(source).toContain("wallet.purchased_remaining");
    expect(source).toMatch(/fmt\(wallet\.purchased_remaining\)/);
  });

  it("no sustituye las cifras por la proporción del partner", () => {
    expect(source).not.toContain("included_percent_used");
  });
});
