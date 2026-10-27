/**
 * Spec 047 (R47.8, R47.9, R47.10) — el sistema visual de la consola nueva,
 * medido sobre `tokens.css`.
 *
 * - El botón primario pasa al verde profundo con texto claro: el diseño apunta
 *   a unos 6,8:1 y el mínimo es 4,5:1.
 * - `bg-primary` lee `--color-primary` y shadcn lee `--primary`: los dos tienen
 *   que ser el mismo color en los dos temas, o el botón cambia según quién lo
 *   pinte.
 * - Las dos series de las gráficas de bloques se ven sobre el fondo y sobre la
 *   tarjeta (3:1, WCAG 1.4.11) y no son el mismo verde.
 * - El vidrio solo existe como utilidad de la capa flotante, se lee encima de
 *   cualquier cosa y pasa a sólido con «Reducir transparencia».
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { contrastRatio, luminance, over, parseColor, type Color } from "../../lib/contrast.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKENS = readFileSync(join(HERE, "..", "..", "styles", "tokens.css"), "utf8");

function blockAt(start: number): Map<string, string> {
  const open = TOKENS.indexOf("{", start);
  let depth = 1;
  let i = open + 1;
  while (depth > 0 && i < TOKENS.length) {
    if (TOKENS[i] === "{") depth += 1;
    if (TOKENS[i] === "}") depth -= 1;
    i += 1;
  }
  const body = TOKENS.slice(open + 1, i - 1).replace(/\/\*[\s\S]*?\*\//g, "");
  const out = new Map<string, string>();
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out.set(m[1]!, m[2]!.trim());
  return out;
}

function block(selector: RegExp): Map<string, string> {
  const start = TOKENS.search(selector);
  if (start < 0) throw new Error(`no encuentro el bloque ${selector}`);
  return blockAt(start);
}

const theme = block(/@theme\s*\{/);
const light = block(/^:root \{/m);
const dark = block(/^\[data-theme="dark"\] \{/m);

function resolve(name: string, scope: Map<string, string>): Color {
  const seen = new Set<string>();
  let value = scope.get(name) ?? theme.get(name);
  while (value && value.startsWith("var(")) {
    const next = value.match(/var\((--[\w-]+)/)?.[1];
    if (!next || seen.has(next)) break;
    seen.add(next);
    value = scope.get(next) ?? theme.get(next);
  }
  const color = value ? parseColor(value) : null;
  if (!color) throw new Error(`no puedo resolver ${name} (${value ?? "sin valor"})`);
  return color;
}

const opaque = (c: Color) => over({ ...c, alpha: 1 }, { r: 1, g: 1, b: 1 });

describe("el primario es el verde profundo (R47.8)", () => {
  it("en claro, el botón primario es oscuro y su texto claro, con al menos 6,5:1", () => {
    const bg = opaque(resolve("--primary", light));
    const fg = opaque(resolve("--primary-foreground", light));
    expect(luminance(bg), "el relleno del primario tiene que ser el verde profundo, no el de marca").toBeLessThan(0.2);
    expect(luminance(fg), "el texto sobre el primario es claro").toBeGreaterThan(0.6);
    expect(Number(contrastRatio(fg, bg).toFixed(2))).toBeGreaterThanOrEqual(6.5);
  });

  it.each([
    ["claro", light],
    ["oscuro", dark],
  ])("en %s, `--color-primary` (Tailwind) y `--primary` (shadcn) son el mismo color", (_n, scope) => {
    expect(opaque(resolve("--color-primary", scope))).toEqual(opaque(resolve("--primary", scope)));
  });

  // `bg-primary` y `bg-primary-deep` van juntos en la consola de hoy: dos
  // tramos del gasto, la ocupación normal y la de más del 85 %. Con el primario
  // ya profundo, «deep» tiene que seguir siendo más oscuro o las dos se pintan igual.
  it.each([
    ["claro", light],
    ["oscuro", dark],
  ])("en %s, `primary-deep` sigue siendo distinto y más oscuro que el primario", (_n, scope) => {
    const primary = opaque(resolve("--color-primary", scope));
    const deep = opaque(resolve("--color-primary-deep", scope));
    expect(luminance(deep)).toBeLessThan(luminance(primary));
    expect(contrastRatio(primary, deep)).toBeGreaterThanOrEqual(1.4);
  });

  it("el punto positivo sigue siendo el verde de marca: el primario profundo no arrastra a los estados", () => {
    expect(theme.get("--color-status-positive")).toBe("var(--color-mountain-meadow)");
  });
});

describe("las series de las gráficas de bloques (R47.10)", () => {
  it.each([
    ["claro", light],
    ["oscuro", dark],
  ])("en %s, cada serie se ve sobre el fondo y sobre la tarjeta (3:1)", (_n, scope) => {
    for (const series of ["--color-series-1", "--color-series-2"]) {
      for (const surface of ["--background", "--card"]) {
        const ratio = contrastRatio(opaque(resolve(series, scope)), opaque(resolve(surface, scope)));
        expect(Number(ratio.toFixed(2)), `${series} sobre ${surface}`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it.each([
    ["claro", light],
    ["oscuro", dark],
  ])("en %s, las dos series no son el mismo verde", (_n, scope) => {
    const ratio = contrastRatio(opaque(resolve("--color-series-1", scope)), opaque(resolve("--color-series-2", scope)));
    expect(ratio).toBeGreaterThanOrEqual(1.4);
  });

  it("la pista (los cuadros vacíos) existe en los dos temas", () => {
    expect(light.get("--color-series-track") ?? theme.get("--color-series-track")).toBeDefined();
    expect(dark.get("--color-series-track")).toBeDefined();
  });
});

describe("el vidrio, solo en la capa flotante (R47.9)", () => {
  it("es una utilidad del sistema con desenfoque", () => {
    const at = TOKENS.search(/@utility glass\s*\{/);
    expect(at, "falta `@utility glass` en tokens.css").toBeGreaterThan(-1);
    const body = TOKENS.slice(at, TOKENS.indexOf("\n}", at));
    expect(body).toMatch(/backdrop-filter:/);
    expect(body).toMatch(/var\(--glass-bg\)/);
  });

  it.each([
    ["claro", light],
    ["oscuro", dark],
  ])("en %s, el texto se lee sobre el vidrio encima del fondo y encima de un botón primario", (_n, scope) => {
    const glass = resolve("--glass-bg", scope);
    expect(glass.alpha, "el vidrio es translúcido").toBeLessThan(1);
    for (const backdrop of ["--background", "--card", "--primary"]) {
      const surface = over(glass, opaque(resolve(backdrop, scope)));
      const ratio = contrastRatio(opaque(resolve("--popover-foreground", scope)), surface);
      expect(Number(ratio.toFixed(2)), `texto sobre vidrio encima de ${backdrop}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("con «Reducir transparencia» pasa a sólido y sin desenfoque", () => {
    const at = TOKENS.search(/@media \(prefers-reduced-transparency: reduce\)/);
    expect(at, "falta el bloque prefers-reduced-transparency").toBeGreaterThan(-1);
    const rules = blockAt(at);
    expect(rules.get("--glass-blur")).toBe("0px");
    const solid = rules.get("--glass-bg");
    expect(solid, "el vidrio se sustituye por la superficie opaca").toBe("var(--popover)");
  });
});

describe("las medidas del marco nuevo son tokens (R47.1)", () => {
  it("el menú plegado mide 64 px", () => {
    expect(theme.get("--size-nav-collapsed")).toBe("64px");
    expect(theme.get("--size-nav")).toMatch(/^\d+px$/);
  });

  it("el punto de ruptura del marco deja la barra superior hasta 900 px", () => {
    // 56,3125 rem = 901 px: `max-shell:` es «ancho < 901 px», es decir, hasta 900.
    expect(theme.get("--breakpoint-shell")).toBe("56.3125rem");
  });
});
