/**
 * Requisitos 2.1 y 2.5 (spec 002) y 8.7 (spec 010) — **la aplicación no tiene
 * autenticación propia**.
 *
 * Esto vigilaba la barra y su `preload`. La barra se retira con la spec 010, y
 * la prohibición **se traslada a la superficie que queda**: el armazón. No se
 * borra, porque es la que importa — un formulario de credenciales dentro de la
 * aplicación sería un segundo camino a la cuenta que nadie audita, con la
 * partición humana al lado.
 *
 * Y se separa en dos, porque no son la misma regla:
 *
 * * **en el `preload`**, prohibición **léxica**: ni la palabra. Es la frontera
 *   con el proceso principal, y su lista es cerrada;
 * * **en la pantalla**, prohibición de **formulario**: sin `type="password"`,
 *   sin ruta de inicio de sesión propia, sin canje de credenciales. Decir «tu
 *   sesión terminó» y ofrecer «Entrar» sí es correcto —es lo que R3.4 y R7.1
 *   piden— y esas palabras aparecen; lo que no puede haber es el formulario.
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

const APP = new URL("../src/app/", import.meta.url).pathname;
const PRELOAD = new URL("../src/electron/app-preload.ts", import.meta.url).pathname;

describe("la pantalla no tiene formulario de credenciales (8.7)", () => {
  const files = walk(APP).filter((p) => /\.tsx?$/.test(p));

  it.each(files)("%s no pide credenciales", (path) => {
    const text = readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(text).not.toMatch(/type=["']password["']/i);
    // Ni un campo que pida un código de sesión: el de emparejamiento es otra
    // cosa —ata una máquina, no da sesión— y por eso se nombra aparte.
    expect(text).not.toMatch(/autocomplete=["']current-password|new-password|one-time-code["']/i);
    // Ni una ruta de inicio de sesión propia: entrar es salir al navegador.
    expect(text).not.toMatch(/path:\s*["']\/login/);
  });

  it("entrar es el flujo por navegador, y nada más", () => {
    const entrada = readFileSync(join(APP, "routes", "sign-in.tsx"), "utf8");
    expect(entrada).toContain("bridge.signInStart()");
    expect(entrada).not.toMatch(/<form/);
  });
});

describe("el preload del armazón no nombra ninguna credencial", () => {
  it("ni login, ni sesión, ni cookie, ni token", () => {
    const text = readFileSync(PRELOAD, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(text).not.toMatch(/login|cookie|password/i);
  });

  it("y expone una lista cerrada, no un canal genérico", () => {
    // El `preload` no enumera nada: construye el puente con `buildAppBridge`,
    // que sale de la lista cerrada de `app-ipc.ts` y tiene su propio test. Un
    // `invoke(channel, payload)` suelto aquí convertiría la lista en un adorno.
    const text = readFileSync(PRELOAD, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(text).toMatch(/buildAppBridge\(ipcRenderer\)/);
    expect(text).not.toMatch(/ipcRenderer\.invoke\(/);

    const bridge = readFileSync(new URL("../src/app-bridge.ts", import.meta.url).pathname, "utf8");
    expect(bridge).toMatch(/APP_INVOKE_CHANNELS|APP_PUSH_CHANNELS/);
  });
});
