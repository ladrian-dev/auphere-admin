/**
 * Requisito 6.1 — el puente es saliente, y esto lo comprueba en vez de prometerlo.
 *
 * Recorre el código fuente buscando cualquier API que ponga la máquina del partner a
 * la escucha. Un test de comportamiento no bastaría: el día que alguien añada un
 * `createServer` "solo para depurar", ningún test de mensajes lo notaría, y la
 * promesa de que instalar esto no abre un puerto en casa de nadie se rompe en
 * silencio.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = new URL("../src", import.meta.url).pathname;

/** APIs que hacen que la máquina escuche. Ninguna tiene sitio en este paquete. */
const LISTENING_APIS = [
  "createServer",
  ".listen(",
  "WebSocketServer",
  "node:dgram",
  "bonjour",
  "mdns",
];

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

  it.each(LISTENING_APIS)("ningún fichero de src usa %s", (api) => {
    const offenders = files.filter((file) => {
      const body = readFileSync(file, "utf8");
      // Se ignoran los comentarios: nombrar la prohibición al explicarla es correcto.
      const code = body.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      return code.includes(api);
    });
    expect(offenders).toEqual([]);
  });
});
