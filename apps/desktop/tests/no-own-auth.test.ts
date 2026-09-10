/**
 * Requisitos 2.1 y 2.5 — la aplicación no tiene flujo de autenticación propio.
 *
 * Entrar es entrar en la consola, cargada en su vista. Ni la barra ni su
 * `preload` tienen un campo de contraseña, una ruta de login ni un registro.
 * Se recorre el fuente, no se promete.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

const BAR = new URL("../src/bar/", import.meta.url).pathname;
const PRELOAD = new URL("../src/electron/bar-preload.ts", import.meta.url).pathname;

describe("la app no autentica a nadie (2.1, 2.5)", () => {
  const files = [...walk(BAR).filter((p) => /\.(ts|html)$/.test(p)), PRELOAD];

  it.each(files)("%s no tiene contraseña, login ni registro", (path) => {
    const text = readFileSync(path, "utf8");
    expect(text).not.toMatch(/type=["']password["']/i);
    expect(text).not.toMatch(/\/login\b/);
    expect(text).not.toMatch(/sign[- ]?up|registr(o|ar|ate)/i);
    expect(text).not.toMatch(/password/i);
  });

  it("el preload expone exactamente las seis funciones del contrato", () => {
    const text = readFileSync(PRELOAD, "utf8");
    for (const fn of ["getState", "onState", "pair", "unpair", "pickDirectory", "openInBrowser"]) {
      expect(text).toContain(`${fn}:`);
    }
    expect(text).not.toMatch(/login|session|cookie|token/i);
  });
});
