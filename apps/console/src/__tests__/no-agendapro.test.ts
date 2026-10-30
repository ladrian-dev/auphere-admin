import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Spec 048 (requisito 1.1; T016): la consola no ofrece AgendaPro. Ni su
 * tarjeta, ni «Enlazar la agenda», ni su acción, ni su cliente de la API, ni
 * sus textos. Reservas (spec 043) es la agenda del negocio.
 *
 * Barre el código de la consola (sin los tests, que pueden nombrarlo para
 * decir que ya no está) y las historias de `@nexus/ui`.
 */
const CONSOLE = join(import.meta.dirname, "..");
const UI_STORIES = join(CONSOLE, "..", "..", "..", "packages", "ui", "src", "stories");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return entry === "__tests__" || entry === "node_modules" ? [] : files(full);
    return /\.(ts|tsx|mjs)$/.test(entry) ? [full] : [];
  });
}

describe("spec 048 · sin AgendaPro", () => {
  it("ningún archivo de la consola ni historia de @nexus/ui nombra AgendaPro", () => {
    const offenders = [...files(CONSOLE), ...files(UI_STORIES)]
      .filter((file) => /agenda[\s_-]?pro/i.test(readFileSync(file, "utf8")))
      .map((file) => relative(join(CONSOLE, "..", "..", ".."), file));
    expect(offenders).toEqual([]);
  });
});
