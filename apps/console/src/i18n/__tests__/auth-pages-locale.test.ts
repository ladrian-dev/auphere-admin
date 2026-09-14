import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Las páginas de `(auth)` no pueden fijar el idioma a mano — spec 006.
 *
 * El fallo, visto en staging: `/signup` salía **en dos idiomas a la vez**.
 * «Crea tu cuenta.» arriba y *Continue*, *Already have an account?*,
 * *Continue with Google* debajo.
 *
 * La causa es que una página tiene dos mitades y cada una decidía por su
 * cuenta. La mitad cliente lee el `LocaleProvider` del layout, que resuelve
 * bien (cookie → cuenta → `Accept-Language`, español por defecto). La mitad
 * servidor llamaba a `getT("es")`, y ese argumento **no es «renderiza en
 * español»**: es `accountLocale`, el idioma de la cuenta del principal. Las
 * 20+ páginas de `(console)` le pasan `principal.locale` porque tienen
 * principal; las de `(auth)` no tienen ninguno, así que le colaban el literal.
 *
 * Con `getT()` sin argumento, `getLocale(undefined)` cae a la cookie y al
 * `Accept-Language` — la misma cadena que usa el layout. Las dos mitades
 * vuelven a estar de acuerdo.
 *
 * Es una prueba sobre el código fuente y no sobre el render a propósito: lo
 * que se vigila es una regla («aquí no se fija el idioma»), y renderizar un
 * Server Component para descubrirlo costaría mucho más y diría menos.
 */
const AUTH_DIR = join(import.meta.dirname, "..", "..", "app", "(auth)");


function pagesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return pagesUnder(full);
    return entry === "page.tsx" ? [full] : [];
  });
}

describe("las páginas de (auth)", () => {
  const pages = pagesUnder(AUTH_DIR);

  it("hay páginas que comprobar (si no, esta prueba no vigila nada)", () => {
    expect(pages.length).toBeGreaterThan(0);
  });

  it.each(pages.map((p) => [p.slice(p.indexOf("(auth)")).split("\\").join("/"), p] as const))(
    "%s no fija el idioma a mano",
    (_label, path) => {
      const src = readFileSync(path, "utf8");
      const hardcoded = src.match(/getT\(\s*["'](es|en)["']\s*\)/g);
      expect(
        hardcoded,
        `fija el idioma con ${hardcoded?.[0]}: la mitad servidor quedaría en un ` +
          `idioma y la mitad cliente en otro. Usa getT() sin argumento.`,
      ).toBeNull();
    },
  );
});
