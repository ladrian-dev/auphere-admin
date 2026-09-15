/**
 * Contra QUIÉN canjea la cáscara — spec 009, Requisito 4.
 *
 * Una prueba sobre el texto de `main.ts`, como `no-inbound` y
 * `packaging-config`, y por la misma razón: lo que falló no fue una función,
 * fue **a qué origen apunta una URL**, y eso no se puede observar sin arrancar
 * Electron.
 *
 * El fallo que fija: la cáscara canjeaba en `${API_URL}/console/auth/session-code/redeem`.
 * Esa ruta de la API exige la credencial de servicio del BFF, que la cáscara no
 * tiene **y no puede tener** (la consola nunca guarda una credencial de
 * backend, y CI lo comprueba). Staging contestaba `401 Missing bearer token`.
 *
 * El canje va por la consola porque es el único sitio que tiene esa credencial
 * y a la vez puede devolver la cookie de sesión, que es lo que la aplicación
 * mira para saber que ya está dentro.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const main = readFileSync(new URL("../src/electron/main.ts", import.meta.url), "utf8");

describe("el canje del inicio de sesión", () => {
  it("va contra la consola", () => {
    expect(main).toContain("${CONSOLE_URL}/api/desktop/redeem");
  });

  it("NO va contra la API: allí hace falta la credencial de servicio del BFF", () => {
    expect(main).not.toContain("session-code/redeem");
    expect(main).not.toMatch(/API_URL\}\/console\/auth/);
  });

  it("manda el código y el verifier de PKCE, y nada más", () => {
    const cuerpo = main.match(/JSON\.stringify\(\{[^}]*code[^}]*\}\)/);
    expect(cuerpo).not.toBeNull();
    expect(cuerpo?.[0]).toContain("code: returned.code");
    expect(cuerpo?.[0]).toContain("code_verifier: verifier");
  });

  it("usa el fetch de la partición humana, que es quien guarda la cookie", () => {
    expect(main).toMatch(/session\s*\n?\s*\.fromPartition\(HUMAN_PARTITION\)\s*\n?\s*\.fetch\(/);
  });
});
