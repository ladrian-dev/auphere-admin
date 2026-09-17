/**
 * Requisitos 1.1 y 1.4 — el reparto de la ventana, y el invariante que sostiene
 * todo el armazón.
 *
 * El spike de la spec 010 demostró que arrastrar la ventana por la franja
 * superior funciona **con la consola pintada encima del panel**, y demostró por
 * qué: no hay solape de regiones de arrastre. Esa es la condición, y aquí queda
 * escrita como test, porque es exactamente lo que un refactor rompería sin
 * darse cuenta — y entonces la ventana dejaría de poder moverse, o la consola
 * se comería la franja.
 */
import { describe, expect, it } from "vitest";

import { MIN_SIDEBAR, MAX_SIDEBAR, STRIP_HEIGHT, contentRect, sidebarWidthFor } from "../src/electron/shell-layout.js";

const VENTANA = { width: 1280, height: 820 };

describe("el panel nunca invade la franja superior", () => {
  it("empieza justo debajo de la franja", () => {
    const rect = contentRect(VENTANA, 260);
    expect(rect.y).toBe(STRIP_HEIGHT);
  });

  it("y tampoco lo hace con una lista lateral absurda", () => {
    for (const ancho of [-100, 0, 5, 10_000]) {
      expect(contentRect(VENTANA, ancho).y).toBe(STRIP_HEIGHT);
    }
  });

  it("el panel empieza donde termina la lista lateral", () => {
    const rect = contentRect(VENTANA, 260);
    expect(rect.x).toBe(260);
    expect(rect.width).toBe(VENTANA.width - 260);
    expect(rect.height).toBe(VENTANA.height - STRIP_HEIGHT);
  });
});

describe("el rectángulo siempre cabe en la ventana", () => {
  it("nunca se sale ni por ancho ni por alto", () => {
    for (const ventana of [{ width: 900, height: 600 }, { width: 3840, height: 2160 }, { width: 400, height: 200 }]) {
      const rect = contentRect(ventana, 260);
      expect(rect.x + rect.width).toBeLessThanOrEqual(ventana.width);
      expect(rect.y + rect.height).toBeLessThanOrEqual(ventana.height);
    }
  });

  it("nunca devuelve medidas negativas, ni en una ventana imposible", () => {
    const rect = contentRect({ width: 0, height: 0 }, 260);
    expect(rect.width).toBeGreaterThanOrEqual(0);
    expect(rect.height).toBeGreaterThanOrEqual(0);
  });

  it("son enteros: el canal no acepta otra cosa", () => {
    const rect = contentRect({ width: 1281, height: 821 }, 261.5);
    for (const valor of [rect.x, rect.y, rect.width, rect.height]) {
      expect(Number.isInteger(valor)).toBe(true);
    }
  });
});

describe("la lista lateral se acota y se colapsa", () => {
  it("respeta el mínimo y el máximo cuando la persona la arrastra", () => {
    expect(sidebarWidthFor(VENTANA.width, 120)).toBe(MIN_SIDEBAR);
    expect(sidebarWidthFor(VENTANA.width, 900)).toBe(MAX_SIDEBAR);
    expect(sidebarWidthFor(VENTANA.width, 260)).toBe(260);
  });

  it("se colapsa sola cuando la ventana se estrecha, y entonces el panel ocupa todo", () => {
    const estrecha = 700;
    expect(sidebarWidthFor(estrecha, 260)).toBe(0);
    const rect = contentRect({ width: estrecha, height: 600 }, sidebarWidthFor(estrecha, 260));
    expect(rect.x).toBe(0);
    expect(rect.width).toBe(estrecha);
    // Y aun colapsada, la franja sigue siendo intocable.
    expect(rect.y).toBe(STRIP_HEIGHT);
  });

  it("al ensancharse vuelve a la anchura que la persona había elegido", () => {
    expect(sidebarWidthFor(1280, 300)).toBe(300);
  });
});
