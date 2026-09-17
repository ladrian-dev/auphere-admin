/**
 * Requisitos 1.6 y 1.10 — la ruta canónica y el historial.
 *
 * Lo que este módulo sostiene es que «dónde estoy» sea **una sola cosa**: la
 * lista lateral la marca, el historial la recorre, la búsqueda de acciones
 * navega a ella y al reabrir la aplicación se vuelve a ella. Antes no existía
 * el concepto: la vista era un estado suelto de React y reabrir la aplicación
 * siempre te dejaba en el mismo sitio.
 */
import { describe, expect, it } from "vitest";

import {
  back,
  canGoBack,
  canGoForward,
  current,
  forward,
  go,
  initialHistory,
  restoredSection,
} from "../src/app/shell/navigation.js";

describe("ir y volver", () => {
  it("empieza donde se le diga y sin nada detrás", () => {
    const h = initialHistory("hoy");
    expect(current(h)).toBe("hoy");
    expect(canGoBack(h)).toBe(false);
    expect(canGoForward(h)).toBe(false);
  });

  it("ir a otra sección deja algo detrás", () => {
    const h = go(initialHistory(), "consumo");
    expect(current(h)).toBe("consumo");
    expect(canGoBack(h)).toBe(true);
  });

  it("atrás vuelve, y adelante rehace", () => {
    const h = go(go(initialHistory(), "consumo"), "facturacion");
    const atras = back(h);
    expect(current(atras)).toBe("consumo");
    expect(current(forward(atras))).toBe("facturacion");
  });

  it("atrás en el principio no se queda en un limbo", () => {
    const h = initialHistory();
    expect(current(back(h))).toBe("hoy");
    expect(back(h)).toEqual(h);
  });

  it("adelante sin nada delante tampoco", () => {
    const h = go(initialHistory(), "consumo");
    expect(forward(h)).toEqual(h);
  });
});

describe("los bordes que hacen dudar de si el botón funciona", () => {
  it("ir a donde ya estás no añade una entrada", () => {
    const h = go(initialHistory("hoy"), "hoy");
    expect(h.entries).toHaveLength(1);
    expect(canGoBack(h)).toBe(false);
  });

  it("navegar después de volver atrás corta lo que había delante", () => {
    const h = go(go(initialHistory(), "consumo"), "facturacion");
    const ramificado = go(back(h), "equipo");
    expect(current(ramificado)).toBe("equipo");
    expect(canGoForward(ramificado)).toBe(false);
    expect(ramificado.entries).toEqual(["hoy", "consumo", "equipo"]);
  });
});

describe("al reabrir se vuelve donde estabas (1.10)", () => {
  it("se restaura la última sección", () => {
    expect(restoredSection("consumo")).toBe("consumo");
  });

  it("la primera vez se empieza en Hoy", () => {
    expect(restoredSection(undefined)).toBe("hoy");
  });

  it("una preferencia vieja que ya no existe no lleva a ninguna parte rara", () => {
    // Si mañana desaparece una sección, lo guardado no puede dejar la
    // aplicación abriendo algo que no existe.
    expect(restoredSection("una-seccion-retirada")).toBe("hoy");
    expect(restoredSection(42)).toBe("hoy");
  });
});
