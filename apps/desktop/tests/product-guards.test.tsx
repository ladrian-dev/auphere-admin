// @vitest-environment jsdom
/**
 * Requisitos 9.10, 8.7 y 12 — las guardas de producto.
 *
 * Tres promesas que no se pueden dejar a la disciplina de quien escribe la
 * siguiente pantalla, porque romperlas no se nota hasta que ya está publicado:
 *
 * * **ninguna vista pide ni muestra datos de tarjeta** (R9.10). Cobrar ocurre
 *   en el navegador, en el proveedor de pago, y la aplicación no toca eso ni de
 *   lejos;
 * * **ningún formulario de credenciales propio** (R8.7). Se entra por el
 *   navegador; un campo de contraseña aquí sería una segunda forma de entrar
 *   que nadie audita;
 * * **ninguna dirección escrita a mano** donde debería haber una sección. Las
 *   rutas de la consola salen de `sections.ts`, que es la lista cerrada.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = join(HERE, "..", "src", "app");

function vistas(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return vistas(full);
    return name.endsWith(".tsx") ? [full] : [];
  });
}

/** El código de cada vista, sin comentarios: aquí se explica lo prohibido. */
const VISTAS = vistas(APP).map((file) => ({
  file,
  code: readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, ""),
}));

describe("ningún dato de tarjeta, en ninguna vista (9.10)", () => {
  const TARJETA = /\b(cardNumber|card_number|cvc|cvv|expiry|numero_de_tarjeta|autocomplete="cc-)/i;

  it("no hay ni un campo que huela a tarjeta", () => {
    const culpables = VISTAS.filter((v) => TARJETA.test(v.code)).map((v) => v.file);
    expect(culpables, `vistas con datos de tarjeta:\n${culpables.join("\n")}`).toHaveLength(0);
  });

  it("y ninguna vista carga el script de un proveedor de pago", () => {
    const culpables = VISTAS.filter((v) => /js\.stripe\.com|@stripe\//.test(v.code)).map((v) => v.file);
    expect(culpables).toHaveLength(0);
  });
});

describe("ningún formulario de credenciales propio (8.7)", () => {
  it("no hay ni un campo de contraseña", () => {
    const culpables = VISTAS.filter((v) => /type="password"/.test(v.code)).map((v) => v.file);
    expect(culpables, `vistas con contraseña:\n${culpables.join("\n")}`).toHaveLength(0);
  });

  it("ni un campo que pida un código de un solo uso de la sesión", () => {
    // El código de **emparejamiento** sí existe y es otra cosa: no da sesión,
    // ata una máquina. Lo que no puede haber es un segundo camino a la cuenta.
    const culpables = VISTAS.filter((v) => /autocomplete="one-time-code"/.test(v.code)).map((v) => v.file);
    expect(culpables).toHaveLength(0);
  });
});

describe("las rutas de la consola salen de la lista cerrada", () => {
  /** Las que sí pueden escribirse: no son secciones. */
  const PERMITIDAS = new Set(["/", "/workstation", "/billing"]);

  it("ninguna vista inventa una ruta de consola", () => {
    const sueltas: string[] = [];
    for (const { file, code } of VISTAS) {
      for (const match of code.matchAll(/openConsole\(\{\s*path:\s*"([^"`]+)"/g)) {
        if (!PERMITIDAS.has(match[1]!)) sueltas.push(`${file}: ${match[1]}`);
      }
    }
    expect(sueltas, `rutas escritas a mano:\n${sueltas.join("\n")}`).toHaveLength(0);
  });
});

describe("ninguna vista pinta un color suelto", () => {
  it("no hay hex ni rgb en el marcado", () => {
    const sueltas: string[] = [];
    for (const { file, code } of VISTAS) {
      for (const match of code.matchAll(/#[0-9a-fA-F]{3,8}\b|rgba?\(/g)) sueltas.push(`${file}: ${match[0]}`);
    }
    expect(sueltas, `colores sueltos:\n${sueltas.join("\n")}`).toHaveLength(0);
  });
});
