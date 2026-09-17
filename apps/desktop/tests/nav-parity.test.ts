/**
 * Requisito 1.2 — integrar la consola no puede dejar ninguna sección fuera de
 * alcance.
 *
 * Cuando la ventana esconde la barra lateral de la consola y pone la suya, la
 * lista lateral de la aplicación pasa a ser **el único camino** a lo que se
 * administra. Si la consola ofrece diez entradas y la aplicación conoce cinco,
 * cinco áreas se vuelven inalcanzables sin que ningún test se entere.
 *
 * Esto pasó de verdad: la primera versión de la lista canónica tenía cinco
 * entradas. El test lee la navegación **real** de la consola y la compara, para
 * que el día que alguien añada una sección allí, esto se ponga rojo aquí.
 *
 * Se lee el fichero en vez de importarlo porque `apps/console` no es una
 * dependencia de este paquete, y no debe serlo: la aplicación sigue a la
 * consola, no al revés.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { CONSOLE_SECTIONS } from "../src/sections.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const NAV = join(HERE, "..", "..", "console", "src", "components", "shell", "nav.ts");

/** `{ href, permission }` por cada entrada declarada en la consola. */
function navegacionDeLaConsola(): Array<{ href: string; permission: string | null }> {
  const source = readFileSync(NAV, "utf8");
  const items: Array<{ href: string; permission: string | null }> = [];
  for (const match of source.matchAll(/\{\s*href:\s*"([^"]+)"[^}]*?\}/g)) {
    const block = match[0];
    const href = match[1] ?? "";
    const permission = block.match(/permission:\s*"([^"]+)"/)?.[1] ?? null;
    items.push({ href, permission });
  }
  return items;
}

describe("la lista lateral llega a todo lo que la consola ofrece", () => {
  const consola = navegacionDeLaConsola();

  it("el fichero de navegación de la consola se puede leer", () => {
    // Si la consola mueve este fichero, este test tiene que romperse y no
    // pasar en silencio dando por buena una lista que ya no compara nada.
    expect(consola.length).toBeGreaterThan(5);
  });

  it("cada entrada de la consola tiene su sección en el armazón", () => {
    const rutasDelArmazon = CONSOLE_SECTIONS.map((s) => s.path);
    for (const item of consola) {
      expect(rutasDelArmazon, `la consola ofrece ${item.href} y el armazón no lo lista`).toContain(item.href);
    }
  });

  it("el armazón no se inventa secciones que la consola no tiene", () => {
    const rutasDeLaConsola = consola.map((i) => i.href);
    for (const section of CONSOLE_SECTIONS) {
      expect(rutasDeLaConsola, `el armazón lista ${section.path} y la consola no lo ofrece`).toContain(section.path);
    }
  });

  it("y respeta el mismo permiso que la consola", () => {
    for (const item of consola) {
      const section = CONSOLE_SECTIONS.find((s) => s.path === item.href);
      expect(section?.permission ?? null, `permiso distinto para ${item.href}`).toBe(item.permission);
    }
  });
});

describe("las rutas se traducen a secciones sin inventar", () => {
  it("la portada es exacta y no se lleva por delante a las demás", async () => {
    const { sectionOfPath } = await import("../src/sections.js");
    expect(sectionOfPath("/")).toBe("inicio");
    expect(sectionOfPath("/usage")).toBe("consumo");
    // La navegación dentro de una sección sigue marcando esa sección.
    expect(sectionOfPath("/clients/cultor-barber/channels")).toBe("clientes");
    expect(sectionOfPath("/usage?from=hoy")).toBe("consumo");
  });

  it("una ruta desconocida no marca nada", async () => {
    const { sectionOfPath } = await import("../src/sections.js");
    expect(sectionOfPath("/algo-que-no-existe")).toBeNull();
    expect(sectionOfPath("no-es-una-ruta")).toBeNull();
  });
});

describe("sólo se aceptan secciones de la lista", () => {
  it("las de operar y las de administrar valen; lo inventado no", async () => {
    const { isSection, isConsoleSection } = await import("../src/sections.js");
    expect(isSection("hoy")).toBe(true);
    expect(isSection("facturacion")).toBe(true);
    expect(isSection("lo-que-sea")).toBe(false);
    expect(isConsoleSection("hoy")).toBe(false);
    expect(isConsoleSection("consumo")).toBe(true);
  });

  it("las secciones que ve una persona dependen de su permiso", async () => {
    const { consoleSectionsFor } = await import("../src/sections.js");
    const sinPermisos = consoleSectionsFor([]).map((s) => s.key);
    // La portada no pide permiso; todo lo demás sí.
    expect(sinPermisos).toEqual(["inicio"]);

    const conConsumo = consoleSectionsFor(["usage:read"]).map((s) => s.key);
    expect(conConsumo).toEqual(["inicio", "consumo"]);
  });
});
