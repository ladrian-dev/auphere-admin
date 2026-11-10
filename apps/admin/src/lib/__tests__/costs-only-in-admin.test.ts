/**
 * Spec 047 (T172, requisito 54.11): solo el panel de operador enseña costes.
 *
 * Coste es lo que a Auphere le cuesta cada llamada (el precio del proveedor, el
 * techo por llamada y por turno del router, el coste estimado de la vista
 * previa, el coste interno de Consumo). El partner y el cliente ven dinero —lo
 * que pagan—, nunca eso.
 *
 * Estructural sobre el fuente, como `operator-sees-figures.test.ts`: lo que hay
 * que impedir es que un campo de coste de la API llegue a una pantalla del
 * partner o del cliente, y eso se ve en el código antes que en un render. La
 * primera prueba ata la lista a campos que existen de verdad (el admin los lee);
 * la segunda recorre la consola, la app, el escritorio y los paquetes de UI.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const REPO = join(__dirname, "..", "..", "..", "..", "..");
const ADMIN = join(REPO, "apps", "admin", "src");

/** The API's cost fields and the panel's cost formatter. */
const COST_TERMS = [
  "internal_cost_usd",
  "estimated_cost_micros",
  "max_cost_per_call_micros",
  "turn_cost_ceiling_micros",
  "current_price",
  "meter_weights",
  "formatCostUsd",
] as const;

/** Where partners and clients look. */
const SURFACES = [
  "apps/console/src",
  "apps/mobile/src",
  "apps/desktop/src",
  "packages/ui/src",
  "packages/companion-ui/src",
] as const;

const SKIP_DIRS = new Set(["node_modules", ".next", "dist", "build", "__tests__"]);
const THIS_FILE = __filename;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return SKIP_DIRS.has(name) ? [] : walk(full);
    if (!/\.(ts|tsx|js|jsx|mjs)$/.test(name) || /\.(test|spec|stories)\.[tj]sx?$/.test(name)) return [];
    return [full];
  });
}

/** Code only: a comment that says «never `internal_cost_usd`» is history, not a use. */
function code(text: string): string {
  return text
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, "").replace(/^\s*(\/\*\*?|\*).*$/, ""))
    .join("\n");
}

describe("solo el admin enseña costes (spec 047, 54.11)", () => {
  it("el admin lee cada campo de coste de la lista (la lista no se inventa)", () => {
    const sources = walk(ADMIN)
      .filter((f) => f !== THIS_FILE)
      .map((f) => code(readFileSync(f, "utf8")))
      .join("\n");
    for (const term of COST_TERMS) expect(sources, term).toContain(term);
  });

  it("ninguna pantalla del partner ni del cliente los nombra", () => {
    const present = SURFACES.filter((s) => existsSync(join(REPO, s)));
    // The partner console must be there, or this test proves nothing.
    expect(present).toContain("apps/console/src");
    const offences: string[] = [];
    for (const surface of present) {
      for (const file of walk(join(REPO, surface))) {
        const text = code(readFileSync(file, "utf8"));
        for (const term of COST_TERMS) {
          if (text.includes(term)) offences.push(`${relative(REPO, file)}: ${term}`);
        }
      }
    }
    expect(offences).toEqual([]);
  });
});
