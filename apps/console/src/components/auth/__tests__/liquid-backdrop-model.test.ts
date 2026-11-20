import { describe, expect, it } from "vitest";

import {
  IDLE_AFTER_S,
  MAX_WAVES,
  addWave,
  canvasSize,
  initialState,
  step,
  touch,
  wavesUniform,
} from "../liquid-backdrop-model";

describe("el líquido de Entrar, sin GPU (spec 066, R2)", () => {
  it("el puntero se acerca a donde está la persona con suavizado, sin saltar (R2.2)", () => {
    const s = initialState();
    touch(s, 0.1, 0.1, 10);
    const before = s.ptr.x;
    step(s, 10.016, 0.016);
    expect(s.ptr.x).toBeLessThan(before);
    expect(s.ptr.x).toBeGreaterThan(0.1);
    for (let i = 1; i <= 20; i++) step(s, 10.016 + i * 0.016, 0.016);
    // Se ilumina por donde pasa…
    expect(s.ptr.e).toBeGreaterThan(0.3);
    for (let i = 21; i <= 120; i++) step(s, 10.016 + i * 0.016, 0.016);
    expect(s.ptr.x).toBeCloseTo(0.1, 2);
    // …y se apaga despacio si deja de moverse.
    expect(s.ptr.e).toBeLessThan(0.3);
  });

  it("sin tocar 2,5 s, el dedo invisible toma el mando y abre ondas solo (R2.1)", () => {
    const s = initialState();
    touch(s, 0.1, 0.1, 0);
    step(s, IDLE_AFTER_S - 0.1, 0.016, () => 0.5);
    expect(s.ptr.tx).toBe(0.1);
    step(s, IDLE_AFTER_S + 0.6, 0.016, () => 0.5);
    expect(s.ptr.tx).not.toBe(0.1);
    expect(s.ptr.te).toBeCloseTo(0.55);
    expect(s.waves).toHaveLength(1);
    // La siguiente, entre 4 y 6 s después.
    expect(s.nextAuto).toBeGreaterThanOrEqual(IDLE_AFTER_S + 0.6 + 4);
    expect(s.nextAuto).toBeLessThanOrEqual(IDLE_AFTER_S + 0.6 + 6);
  });

  it("caben cuatro ondas: la quinta echa a la más vieja (R2.3)", () => {
    const s = initialState();
    for (let i = 0; i < 6; i++) addWave(s, i / 10, 0.5, i, 1);
    expect(s.waves).toHaveLength(MAX_WAVES);
    expect(s.waves[0]?.[0]).toBeCloseTo(0.2);
    const u = wavesUniform(s);
    expect(u).toHaveLength(16);
  });

  it("los huecos de la cola no se pintan: nacen en un pasado lejano", () => {
    const u = wavesUniform(initialState());
    expect(u[2]).toBe(-99);
  });

  it("el lienzo va a media resolución, con la densidad limitada a 2 (R2.4)", () => {
    expect(canvasSize(800, 600, 1)).toEqual([400, 300]);
    expect(canvasSize(800, 600, 2)).toEqual([800, 600]);
    expect(canvasSize(800, 600, 3)).toEqual([800, 600]);
    expect(canvasSize(0, 0, 0)).toEqual([2, 2]);
  });

  it("el puntero nunca sale del panel", () => {
    const s = initialState();
    touch(s, -3, 4, 1);
    expect([s.ptr.tx, s.ptr.ty]).toEqual([0, 1]);
  });
});
