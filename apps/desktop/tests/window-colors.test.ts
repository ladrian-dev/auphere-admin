/**
 * Requisito 2.7 — el fondo de la ventana y el del sistema de diseño no se
 * separan.
 *
 * El color con el que nace la ventana no puede salir de un token: se necesita
 * antes de que haya CSS. Está escrito a mano en `window-colors.ts`, y este test
 * comprueba que sigue siendo **el mismo color** que `--background` en cada
 * tema. Sin esto, el día que alguien retoque la paleta la ventana volvería a
 * dar un destello de otro color al abrirse, que es justo lo que se arregló.
 *
 * La comparación es perceptual con un margen estrecho, porque OKLCH y sRGB no
 * redondean igual: lo que se vigila es la divergencia, no el último bit.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { contrastRatio, parseColor } from "@nexus/ui/lib/contrast";
import { describe, expect, it } from "vitest";

import { WINDOW_BACKGROUND_DARK, WINDOW_BACKGROUND_LIGHT, windowBackground } from "../src/electron/window-colors.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKENS = readFileSync(join(HERE, "..", "..", "..", "packages", "ui", "src", "styles", "tokens.css"), "utf8");

/** El valor de una variable de la paleta (`@theme`). */
function palette(name: string): string {
  const match = TOKENS.match(new RegExp(`${name}:\\s*([^;]+);`));
  if (!match?.[1]) throw new Error(`no encuentro ${name} en tokens.css`);
  return match[1].replace(/\s*\/\*.*?\*\/\s*/g, "").trim();
}

/** Dos colores «son el mismo» si su contraste entre sí es prácticamente 1. */
function mismoColor(a: string, b: string): number {
  const uno = parseColor(a);
  const otro = parseColor(b);
  if (!uno || !otro) throw new Error(`no puedo leer ${a} o ${b}`);
  return contrastRatio(uno.rgb, otro.rgb);
}

describe("el fondo de la ventana es el del tema", () => {
  it("en oscuro, el mismo que `--color-ink-surface`", () => {
    expect(mismoColor(WINDOW_BACKGROUND_DARK, palette("--color-ink-surface"))).toBeLessThan(1.1);
  });

  it("en claro, el mismo que `--color-anti-flash`", () => {
    expect(mismoColor(WINDOW_BACKGROUND_LIGHT, palette("--color-anti-flash"))).toBeLessThan(1.1);
  });

  it("y se elige por el tema activo, no por el que había al compilar", () => {
    expect(windowBackground(true)).toBe(WINDOW_BACKGROUND_DARK);
    expect(windowBackground(false)).toBe(WINDOW_BACKGROUND_LIGHT);
  });
});
