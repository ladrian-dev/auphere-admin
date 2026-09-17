/**
 * Requisito 12.7 (spec 002) — la consola reconoce a la cáscara en UN sitio.
 *
 * El acoplamiento es mínimo y está vigilado: `isDesktopShell` se importa
 * exactamente una vez fuera de su módulo, en la página de canales, para
 * esconder la conexión de Meta y decir «continúa en el navegador». Una
 * segunda bifurcación exige su propia spec, y este test es la puerta.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { DESKTOP_SHELL_UA_TOKEN, isDesktopShellUserAgent } from "../shell-ua";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (name === "node_modules" || name === ".next") return [];
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

describe("isDesktopShellUserAgent", () => {
  it("reconoce el sufijo que la cáscara añade, y nada más", () => {
    expect(isDesktopShellUserAgent(`Mozilla/5.0 Chrome/132 ${DESKTOP_SHELL_UA_TOKEN}0.2.0`)).toBe(true);
    expect(isDesktopShellUserAgent("Mozilla/5.0 Chrome/132 Electron/44.3.0")).toBe(false);
    expect(isDesktopShellUserAgent(null)).toBe(false);
    expect(isDesktopShellUserAgent(undefined)).toBe(false);
  });
});

describe("las bifurcaciones por cáscara están contadas", () => {
  it("`@/lib/shell` se importa sólo donde una spec lo justificó", () => {
    const src = `${resolve(process.cwd(), "src")}/`;
    const importers = walk(src)
      .filter((p) => /\.(ts|tsx)$/.test(p) && !p.includes("__tests__") && !p.endsWith("/lib/shell.ts") && !p.endsWith("/lib/shell-ua.ts"))
      .filter((p) => /from ["']@\/lib\/shell["']/.test(readFileSync(p, "utf8")));
    /*
     * Dos, y cada una con su razón escrita:
     *
     * * `channels/page.tsx` (spec 002 R12.7) — conectar canales de Meta no
     *   funciona dentro de la ventana, así que se manda al navegador.
     * * `(console)/layout.tsx` (spec 010) — el modo embebido: dentro de la
     *   aplicación la consola no pinta su armazón, porque lo pone la ventana.
     *
     * El test sigue existiendo para lo mismo que antes: que una tercera
     * bifurcación no entre sin que nadie la discuta.
     */
    expect(importers.map((p) => p.replace(src, "")).sort()).toEqual([
      "app/(console)/layout.tsx",
      "app/(console)/clients/[ref]/channels/page.tsx",
    ].sort());
  });
});
