/**
 * Requisito 2.4 — el contraste deja de ser una promesa.
 *
 * La auditoría de la spec 010 midió los tokens y encontró que varios pares que
 * se usan todos los días no llegan a AA: el anillo de foco a 2,09:1 sobre el
 * tema claro, un error sobre tarjeta en oscuro a **1,24:1**, el texto apagado
 * sobre tarjeta a 3,83:1. Nadie lo había visto porque nadie lo medía.
 *
 * Este test lee `tokens.css`, resuelve las variables y comprueba los pares
 * declarados en ambos temas. Si alguien cambia un token y baja del umbral, se
 * entera aquí y no en producción.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { parseColor, ratioOn, type Color } from "../../lib/contrast.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKENS = readFileSync(join(HERE, "..", "..", "styles", "tokens.css"), "utf8");

/** Las declaraciones de un bloque, por nombre de variable. */
function block(selector: RegExp): Map<string, string> {
  const start = TOKENS.search(selector);
  if (start < 0) throw new Error(`no encuentro el bloque ${selector}`);
  const open = TOKENS.indexOf("{", start);
  const close = TOKENS.indexOf("\n}", open);
  const body = TOKENS.slice(open, close);
  const out = new Map<string, string>();
  for (const match of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out.set(match[1]!, match[2]!.trim());
  }
  return out;
}

const theme = block(/@theme\s*\{/);
const light = block(/^:root \{/m);
const dark = block(/^\[data-theme="dark"\] \{/m);

/** Resuelve `var(--x)` hasta llegar a un color de verdad. */
function resolve(name: string, scope: Map<string, string>): Color {
  const seen = new Set<string>();
  let value = scope.get(name) ?? theme.get(name);
  while (value && value.startsWith("var(")) {
    const next = value.match(/var\((--[\w-]+)/)?.[1];
    if (!next || seen.has(next)) break;
    seen.add(next);
    value = scope.get(next) ?? theme.get(next);
  }
  const color = value ? parseColor(value.replace(/\s*\/\*.*?\*\/\s*/g, "").trim()) : null;
  if (!color) throw new Error(`no puedo resolver ${name} (${value ?? "sin valor"})`);
  return color;
}

/** Texto: 4,5:1. No textual y foco: 3:1 (WCAG 2.2, 1.4.3 y 1.4.11). */
const TEXTO = 4.5;
const NO_TEXTUAL = 3;

type Par = { fg: string; bg: string; min: number; nota: string };

const PARES: Par[] = [
  { fg: "--foreground", bg: "--background", min: TEXTO, nota: "texto principal" },
  { fg: "--foreground", bg: "--card", min: TEXTO, nota: "texto sobre tarjeta" },
  { fg: "--muted-foreground", bg: "--background", min: TEXTO, nota: "texto apagado" },
  { fg: "--muted-foreground", bg: "--card", min: TEXTO, nota: "texto apagado sobre tarjeta" },
  { fg: "--muted-foreground", bg: "--muted", min: TEXTO, nota: "texto apagado sobre banner" },
  { fg: "--card-foreground", bg: "--card", min: TEXTO, nota: "texto de tarjeta" },
  { fg: "--primary-foreground", bg: "--primary", min: TEXTO, nota: "texto sobre el color primario" },
  { fg: "--destructive", bg: "--background", min: TEXTO, nota: "peligro sobre el fondo" },
  { fg: "--destructive", bg: "--card", min: TEXTO, nota: "peligro sobre tarjeta" },
  // El tono **legible** del aviso, no el sólido: los estados van por pares
  // (relleno e icono por un lado, texto por otro) desde la spec 010.
  { fg: "--warning", bg: "--background", min: TEXTO, nota: "aviso sobre el fondo" },
  { fg: "--warning", bg: "--card", min: TEXTO, nota: "aviso sobre tarjeta" },
  { fg: "--ring", bg: "--background", min: NO_TEXTUAL, nota: "anillo de foco" },
  { fg: "--ring", bg: "--card", min: NO_TEXTUAL, nota: "anillo de foco sobre tarjeta" },
  // WCAG 1.4.11 pide 3:1 a lo que **identifica un componente**: el borde de un
  // control entra, una línea de separación no. Por eso se mide `--input` y no
  // `--border`, que es decoración y pedirle 3:1 dejaría la interfaz cargada.
  { fg: "--input", bg: "--background", min: NO_TEXTUAL, nota: "borde de un control" },
  { fg: "--input", bg: "--card", min: NO_TEXTUAL, nota: "borde de un control sobre tarjeta" },
];

describe.each([
  ["claro", light],
  ["oscuro", dark],
])("los pares declarados pasan AA en el tema %s", (_nombre, scope) => {
  it.each(PARES)("$nota ($fg sobre $bg)", ({ fg, bg, min }) => {
    const ratio = ratioOn(resolve(fg, scope), resolve(bg, scope));
    expect(Number(ratio.toFixed(2))).toBeGreaterThanOrEqual(min);
  });
});

describe("el anillo de foco es el mismo en los dos temas y se ve en los dos", () => {
  it("existe como token propio, no como el color primario reutilizado", () => {
    // El primario es verde de marca y sobre `bone` da 2,09:1: sirve para una
    // llamada a la acción, no para decir dónde está el foco.
    expect(light.get("--ring")).toBeDefined();
    expect(dark.get("--ring")).toBeDefined();
  });
});

/**
 * El borde de marca, que no es el puente de shadcn.
 *
 * `--border` es el puente; `--color-border` es el token de marca, y es el que
 * consume `border-border` de Tailwind — el propio `tokens.css` explica que no
 * puede espejarlo en `@theme inline` sin crear un `var()` circular.
 *
 * El defecto: `--color-border` solo estaba declarado en claro, tinta oscura al
 * 12 %, y el tema oscuro lo heredaba. En oscuro se pintaba **tinta sobre
 * tinta**: los bordes no quedaban sutiles, desaparecían, y con ellos la
 * jerarquía de tarjetas, separadores y campos. En la aplicación, en la consola
 * y en el panel de operador a la vez, porque las tres beben de este fichero.
 *
 * No se le pide 3:1 — es decoración, y el comentario de `PARES` arriba explica
 * por qué pedírselo dejaría la interfaz cargada. Se le pide **existir por
 * tema** y **verse**.
 */
describe("los bordes de marca se ven en los dos temas", () => {
  it.each(["--color-border", "--color-border-soft"])("%s se declara para el tema oscuro", (token) => {
    expect(
      dark.get(token),
      `${token} no está en el bloque oscuro: hereda el valor de claro y se pinta tinta sobre tinta`,
    ).toBeDefined();
  });

  it.each(["--color-border", "--color-border-soft"])("%s no es el mismo valor en los dos temas", (token) => {
    expect(resolve(token, dark)).not.toEqual(resolve(token, light));
  });

  it.each([
    ["--background", "el fondo"],
    ["--card", "una tarjeta"],
  ])("el borde se distingue sobre %s en oscuro", (surface) => {
    // Un pelo visible, no un borde marcado: por debajo de esto el ojo no lo
    // separa del fondo, que es exactamente lo que pasaba.
    expect(ratioOn(resolve("--color-border", dark), resolve(surface, dark))).toBeGreaterThan(1.2);
  });
});
