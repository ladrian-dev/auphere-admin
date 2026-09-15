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

  /**
   * **Ocho desde la spec 009, y sigue siendo una lista cerrada.**
   *
   * Eran seis. `showApp` y `redeemCode` entran porque la barra no puede cambiar
   * de superficie ni entregar un código sin un canal al proceso principal — que
   * es justo el propósito de no dárselo, y por eso la ampliación se argumenta en
   * `specs/009-…/contracts/bar-preload.md` en vez de darse por hecha.
   *
   * Lo que **no** cambia es la prohibición de abajo: ninguna de las ocho toca
   * `login`, `session`, `cookie` ni `token`. `redeemCode` entrega ocho
   * caracteres que una persona tecleó y recibe un estado; quien habla con la
   * plataforma es el principal. La aplicación sigue sin autenticación propia
   * (Requisitos 2.1 y 2.5 de la spec 002).
   */
  const CONTRATO = [
    "getState",
    "onState",
    "pair",
    "unpair",
    "pickDirectory",
    "openInBrowser",
    "showApp",
    "redeemCode",
  ];

  it("el preload expone exactamente las ocho funciones del contrato", () => {
    const text = readFileSync(PRELOAD, "utf8");
    for (const fn of CONTRATO) {
      expect(text).toContain(`${fn}:`);
    }
    expect(text).not.toMatch(/login|session|cookie|token/i);
  });

  /**
   * Que estén las ocho no impide que haya una novena. Este caso es el que
   * mantiene la lista **cerrada** mañana: cuenta las claves que el objeto
   * expone y las compara con el contrato, en vez de comprobar sólo presencia.
   */
  it("no expone ninguna función que el contrato no declare", () => {
    const text = readFileSync(PRELOAD, "utf8");
    // Las claves de primer nivel de `const api = { … }`, que es lo que
    // `exposeInMainWorld` publica. A dos espacios exactos: lo de dentro de
    // `onState` va a cuatro y no cuenta.
    const cuerpo = text.slice(text.indexOf("const api = {"), text.indexOf("exposeInMainWorld"));
    const expuestas = [...cuerpo.matchAll(/^ {2}(\w+):/gm)].map((m) => m[1]);
    expect(expuestas.length).toBeGreaterThan(0);
    expect([...expuestas].sort()).toEqual([...CONTRATO].sort());
  });
});
