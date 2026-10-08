import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Spec 030 (R2.2, R2.4, R3.4): ninguna página de la consola queda sin dueño.
 *
 * Con la consola lite hay dos tipos de persona y cada página es de uno de los
 * dos. La API es la autoridad —una persona de cliente recibe 403 en todas las
 * rutas del partner—, pero una página que no se guarda pintaría su armazón y
 * sus errores a quien no le toca. Este barrido lee cada `page.tsx` del grupo
 * `(console)` y falla si no llama a `requirePartnerPrincipal` o a
 * `requireClientPrincipal`: una página nueva que se olvide entra en rojo el
 * mismo día, no cuando un cliente la encuentre.
 */
const CONSOLE = join(import.meta.dirname, "..", "(console)");

function pages(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return entry === "__tests__" ? [] : pages(full);
    return entry === "page.tsx" ? [full] : [];
  });
}

describe("guardas de página", () => {
  const all = pages(CONSOLE);

  it("encuentra las páginas (si esto baja a cero, el barrido dejó de mirar)", () => {
    expect(all.length).toBeGreaterThan(20);
  });

  it("cada página de la consola dice de quién es", () => {
    const unguarded = all.filter((file) => {
      const src = readFileSync(file, "utf8");
      // Los alias viejos (`/tools`, `/skills`…) solo redirigen a una página
      // guardada y no leen nada: no tienen nada que guardar.
      if (/permanentRedirect\(/.test(src) && !src.includes("@/lib/backend")) return false;
      return !/require(Partner|Client)Principal\(/.test(src);
    });
    expect(unguarded.map((f) => relative(CONSOLE, f))).toEqual([]);
  });
});
