import { describe, expect, it } from "vitest";

import { CATALOG_KEYS, catalogHref, catalogState } from "../catalog-url";

/**
 * El estado del catálogo vive en la dirección de la página (spec 018, R4.4).
 *
 * Lo que estos tests fijan es que **compartir el enlace lleva a lo mismo** y
 * que «atrás» deshace un filtro. Los dos dependen de la misma cosa: que
 * buscar, elegir pestaña y filtrar por categoría se escriban en la
 * dirección, y que nada más de lo que hay en ella se pierda por el camino.
 */

describe("catalogState · leer la dirección", () => {
  it("sin parámetros, el catálogo se ve entero", () => {
    expect(catalogState({})).toEqual({ q: "", tab: "all", category: null });
  });

  it("lee los tres gestos", () => {
    expect(catalogState({ q: "cita", tab: "active", cat: "citas" })).toEqual({
      q: "cita",
      tab: "active",
      category: "citas",
    });
  });

  it("una pestaña que no existe se lee como «todo», no rompe la pantalla", () => {
    // Un enlace compartido con una errata, o de una versión anterior, tiene
    // que seguir abriendo el catálogo.
    expect(catalogState({ tab: "activos" }).tab).toBe("all");
  });

  it("un parámetro repetido se queda con el primero, no concatena", () => {
    // `?cat=citas&cat=pedidos` llega como lista. Unirlas daría una categoría
    // que no existe y una pantalla vacía sin explicación.
    expect(catalogState({ cat: ["citas", "pedidos"] }).category).toBe("citas");
  });

  it("los espacios sobrantes no cuentan como búsqueda", () => {
    expect(catalogState({ q: "   " }).q).toBe("");
  });
});

describe("catalogHref · escribir la dirección", () => {
  const base = "/clients/demo/capabilities";

  it("un cambio conserva los otros dos gestos", () => {
    const params = new URLSearchParams({ q: "cita", cat: "citas" });
    expect(catalogHref(base, params, { tab: "active" })).toBe(
      "/clients/demo/capabilities?q=cita&cat=citas&tab=active",
    );
  });

  it("quitar un filtro lo borra de la dirección en vez de dejarlo vacío", () => {
    const params = new URLSearchParams({ cat: "citas", tab: "active" });
    expect(catalogHref(base, params, { category: null })).toBe("/clients/demo/capabilities?tab=active");
  });

  it("sin nada puesto, la dirección vuelve a ser la limpia", () => {
    const params = new URLSearchParams({ q: "x", cat: "citas", tab: "active" });
    expect(catalogHref(base, params, { q: "", category: null, tab: "all" })).toBe("/clients/demo/capabilities");
  });

  it("**no toca lo que no es suyo**", () => {
    // El filtro por sector de la spec 017 (`?all=1`) vive en la misma
    // dirección. Reconstruirla desde cero lo borraría, y el partner
    // perdería «ver todas» cada vez que escribiera una letra.
    const params = new URLSearchParams({ all: "1", cat: "citas" });
    expect(catalogHref(base, params, { q: "pedido" })).toBe(
      "/clients/demo/capabilities?all=1&cat=citas&q=pedido",
    );
  });

  it("las claves que el patrón se reserva están dichas en un sitio", () => {
    // Para que una pantalla que añada un parámetro propio sepa cuáles no
    // puede usar.
    expect([...CATALOG_KEYS]).toEqual(["q", "tab", "cat"]);
  });
});
