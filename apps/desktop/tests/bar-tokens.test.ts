/**
 * Requisitos 12.5 y 12.6 — la barra usa los tokens del sistema y nada más.
 *
 * Se escribe **antes** de que la barra tenga estilos, para que el primer color
 * suelto que alguien escriba se ponga rojo. Dos prohibiciones concretas salen de
 * la revisión del diseño v3 (§7): `--color-fg-subtle` a 0,5 no llega a AA para
 * texto que haya que leer, y `--color-status-warning` con texto claro encima
 * tampoco.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const BAR_DIR = new URL("../src/bar/", import.meta.url).pathname;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

function sources(): { path: string; text: string }[] {
  return walk(BAR_DIR)
    .filter((p) => /\.(ts|html|css)$/.test(p) && !p.endsWith("tokens.css"))
    .map((path) => ({ path, text: readFileSync(path, "utf8") }));
}

describe("la barra del puesto y los tokens (12.5, 12.6)", () => {
  it("la barra existe", () => {
    expect(existsSync(BAR_DIR)).toBe(true);
    expect(sources().length).toBeGreaterThan(0);
  });

  it("ningún color hex, rgb ni hsl fuera de tokens.css", () => {
    for (const { path, text } of sources()) {
      expect(text, path).not.toMatch(/#[0-9a-fA-F]{3,8}\b(?![\w-])/);
      expect(text, path).not.toMatch(/\b(rgb|hsl)a?\(/);
    }
  });

  it("el texto sutil no se usa para texto que haya que leer", () => {
    for (const { path, text } of sources()) {
      expect(text, path).not.toContain("--color-fg-subtle");
    }
  });

  it("el aviso nunca lleva texto claro encima", () => {
    for (const { path, text } of sources()) {
      // Una regla que ponga `background: var(--color-status-warning)` y un color
      // de texto claro en el mismo bloque es lo que falla el contraste.
      const blocks = text.split("}");
      for (const block of blocks) {
        if (!block.includes("--color-status-warning")) continue;
        expect(block, path).not.toMatch(/color:\s*var\(--color-(bone|anti-flash|bg)/);
      }
    }
  });

  it("la copia de tokens es CSS que un navegador entiende: la paleta va en :root, no en @theme", () => {
    const copied = join(BAR_DIR, "tokens.css");
    if (!existsSync(copied)) return; // se genera en el build; sin build no hay nada que afirmar
    const css = readFileSync(copied, "utf8");
    expect(css).toMatch(/^:root \{$/m);
    expect(css).not.toMatch(/^@theme \{$/m);
  });

  it("los tokens llegan copiados en el build, no descargados", () => {
    const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
    expect(String(pkg.scripts.build)).toContain("copy-tokens");
    for (const { path, text } of sources()) {
      expect(text, path).not.toMatch(/https?:\/\/[^"' ]+\.css/);
    }
  });
});
