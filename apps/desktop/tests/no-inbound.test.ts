/**
 * Requisito 6 — el puente es saliente, y esto lo comprueba en vez de prometerlo.
 *
 * Recorre el código fuente buscando cualquier API que ponga la máquina del partner a
 * la escucha. Un test de comportamiento no bastaría: el día que alguien añada un
 * `createServer` "solo para depurar", ningún test de mensajes lo notaría, y la
 * promesa de que instalar esto no abre un puerto en casa de nadie se rompe en
 * silencio.
 *
 * ── Enmienda del 2026-09-15 (spec 009) ───────────────────────────────────
 *
 * Antes la respuesta era «ninguno». Ahora es **exactamente uno**, el del
 * retorno del inicio de sesión (RFC 8252), y **sigue siendo ninguno para todo
 * lo demás**. Esa diferencia es todo el valor de este fichero: si se hubiera
 * relajado a «los que hagan falta», el `createServer` "solo para depurar"
 * volvería a colarse en silencio, que es justo lo que vino a impedir.
 *
 * Las cuatro condiciones del criterio 6.5 se comprueban una por una abajo.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = new URL("../src", import.meta.url).pathname;

/** APIs que hacen que la máquina escuche. Ninguna tiene sitio en este paquete… */
const LISTENING_APIS = [
  "createServer",
  ".listen(",
  "WebSocketServer",
  "node:dgram",
  "bonjour",
  "mdns",
];

/** …salvo este fichero, y sólo él: el retorno del inicio de sesión (6.5). */
const LOOPBACK_SERVER = "loopback-login.ts";

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return full.endsWith(".ts") ? [full] : [];
  });
}

describe("el puente nunca escucha (Requisito 6.1)", () => {
  const files = sourceFiles(SRC);

  it("hay código fuente que revisar", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(LISTENING_APIS)("ningún fichero de src usa %s, salvo el del retorno", (api) => {
    const offenders = files.filter((file) => {
      if (file.endsWith(LOOPBACK_SERVER)) return false;
      const body = readFileSync(file, "utf8");
      // Se ignoran los comentarios: nombrar la prohibición al explicarla es correcto.
      const code = body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      return code.includes(api);
    });
    expect(offenders).toEqual([]);
  });

  it("la excepción es UNA, y existe", () => {
    // Si alguien borra el fichero, la excepción deja de estar justificada y hay
    // que quitarla del test. Si alguien añade un segundo, el `it.each` de arriba
    // lo caza.
    const excepciones = files.filter((f) => f.endsWith(LOOPBACK_SERVER));
    expect(excepciones).toHaveLength(1);
  });
});

/**
 * Las cuatro condiciones del criterio 6.5, sobre el único oyente permitido.
 *
 * Se recorre el fuente y no se levanta el servidor a propósito: lo que hay que
 * impedir es que alguien **escriba** `0.0.0.0` o un puerto fijo, y eso se ve en
 * el texto. Un test de comportamiento pasaría con un servidor que escucha bien
 * hoy y mal tras un refactor de una línea.
 */
describe("el único oyente cumple las cuatro condiciones (6.5)", () => {
  const file = sourceFiles(SRC).find((f) => f.endsWith(LOOPBACK_SERVER));
  const code = file
    ? readFileSync(file, "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "")
    : "";

  it("escucha en 127.0.0.1 y en ninguna interfaz de red", () => {
    expect(code).toContain("127.0.0.1");
    expect(code).not.toContain("0.0.0.0");
    // Nada de puerto fijo. `[1-9]` y no `\d`: `listen(0, …)` es justamente la
    // forma correcta de pedir uno efímero, y prohibirla prohibiría el acierto.
    expect(code).not.toMatch(/listen\(\s*[1-9]/);
  });

  it("deja el puerto al sistema operativo", () => {
    // `listen(0, …)` es cómo se pide un puerto efímero.
    expect(code).toMatch(/listen\(\s*0\s*,/);
  });

  it("se cierra: hay un `close` para cuando termina o caduca", () => {
    expect(code).toMatch(/\.close\(/);
  });

  it("comprueba el `state` antes de canjear nada", () => {
    expect(code).toContain("state");
  });
});
