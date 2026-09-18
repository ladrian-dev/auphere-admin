/**
 * Requisitos 12.5 y 12.6 — el armazón usa los tokens del sistema y nada más.
 *
 * **Era el test de la barra de 44 px**, que se retira con la spec 010: lo que
 * vigilaba —que nadie escriba un color suelto en la superficie propia de la
 * aplicación— sigue haciendo falta, y ahora la superficie propia es el armazón.
 *
 * Las dos prohibiciones concretas vienen de la revisión del diseño v3 (§7):
 * `--color-fg-subtle` a 0,5 no llega a AA para texto que haya que leer, y
 * `--color-status-warning` con texto claro encima tampoco.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const APP_DIR = new URL("../src/app/", import.meta.url).pathname;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

/** Lo que pinta el armazón, sin la hoja de tokens ni los catálogos de texto. */
function sources(): { path: string; text: string }[] {
  return walk(APP_DIR)
    .filter((p) => /\.(tsx?|html|css)$/.test(p) && !p.endsWith("tokens.css") && !p.endsWith("styles.css"))
    .map((path) => ({ path, text: readFileSync(path, "utf8") }));
}

describe("el armazón y los tokens (12.5, 12.6)", () => {
  it("el armazón existe, y la barra ya no", () => {
    expect(existsSync(APP_DIR)).toBe(true);
    expect(sources().length).toBeGreaterThan(0);
    // La superficie que esta spec retira. Un directorio que vuelve a aparecer
    // es una barra que vuelve, y esto se entera.
    expect(existsSync(new URL("../src/bar/", import.meta.url).pathname)).toBe(false);
  });

  it("ningún color hex, rgb ni hsl", () => {
    for (const { path, text } of sources()) {
      const limpio = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
      expect(limpio, path).not.toMatch(/#[0-9a-fA-F]{3,8}\b(?![\w-])/);
      expect(limpio, path).not.toMatch(/\b(rgb|hsl)a?\(/);
    }
  });

  it("el texto sutil no se usa para texto que haya que leer", () => {
    for (const { path, text } of sources()) {
      expect(text, path).not.toContain("--color-fg-subtle");
    }
  });

  it("el aviso nunca lleva texto claro encima", () => {
    for (const { path, text } of sources()) {
      const blocks = text.split("}");
      for (const block of blocks) {
        if (!block.includes("--color-status-warning")) continue;
        expect(block, path).not.toMatch(/color:\s*var\(--color-(bone|anti-flash|bg)/);
      }
    }
  });

  it("los tokens viajan con la aplicación, no se descargan", () => {
    // La pantalla los importa por Vite; la barra no podía y por eso había un
    // guion que los copiaba a mano. Con la barra retirada, el guion sobra.
    const estilos = readFileSync(new URL("../src/app/styles.css", import.meta.url), "utf8");
    expect(estilos).toContain('@import "@nexus/ui/tokens.css"');
    for (const { path, text } of sources()) {
      expect(text, path).not.toMatch(/https?:\/\/[^"' ]+\.css/);
    }
  });

  it("y el build ya no copia nada de una barra que no existe", () => {
    const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
    expect(String(pkg.scripts.build)).not.toContain("copy-bar-assets");
    expect(String(pkg.scripts.build)).not.toContain("copy-tokens");
  });
});
