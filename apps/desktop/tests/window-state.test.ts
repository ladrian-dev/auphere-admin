/**
 * Requisito 12.4 — comportarse como una aplicación: la ventana recuerda su sitio.
 *
 * Módulo puro: lee y escribe un objeto, no toca Electron. Lo que se prueba es
 * lo que hace mal casi todo el mundo — restaurar una ventana **fuera de las
 * pantallas que hay ahora**. Quien desconecta el monitor externo y abre la
 * aplicación se encuentra con una ventana que no puede alcanzar, y desde fuera
 * parece que no arrancó.
 */
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_WINDOW, MIN_WINDOW, readWindowState, rememberWindow } from "../src/window-state";

const screens = [{ x: 0, y: 0, width: 1440, height: 900 }];

describe("dónde se abre la ventana", () => {
  it("sin nada guardado, el tamaño de partida", () => {
    expect(readWindowState(null, screens)).toEqual(DEFAULT_WINDOW);
  });

  it("con algo guardado y una pantalla que lo contiene, se respeta", () => {
    const saved = { x: 100, y: 80, width: 1200, height: 800, maximised: false };
    expect(readWindowState(saved, screens)).toEqual(saved);
  });

  it("una ventana guardada fuera de las pantallas de hoy vuelve al centro", () => {
    // El monitor externo de ayer no está: restaurar en x=3000 deja la ventana
    // donde nadie puede tocarla, y parece que la aplicación no abrió.
    const saved = { x: 3000, y: 200, width: 1200, height: 800, maximised: false };
    const state = readWindowState(saved, screens);
    expect(state.x).toBeGreaterThanOrEqual(0);
    expect(state.x! + state.width).toBeLessThanOrEqual(1440);
    expect(state.width).toBe(1200);
  });

  it("una ventana más grande que la pantalla se encoge hasta caber", () => {
    const saved = { x: 0, y: 0, width: 3000, height: 2000, maximised: false };
    const state = readWindowState(saved, screens);
    expect(state.width).toBeLessThanOrEqual(1440);
    expect(state.height).toBeLessThanOrEqual(900);
  });

  it("nunca se abre más pequeña de lo usable, pero respeta lo que elegiste", () => {
    // 120×90 no es una ventana, es un error guardado: se sube al mínimo usable.
    const tiny = readWindowState({ x: 0, y: 0, width: 120, height: 90, maximised: false }, screens);
    expect(tiny.width).toBeGreaterThanOrEqual(MIN_WINDOW.width);
    expect(tiny.height).toBeGreaterThanOrEqual(MIN_WINDOW.height);
    // Y 1000×700 sí es una ventana: se respeta tal cual, aunque sea menor que
    // el tamaño de partida. Devolvérsela a 1280 sería deshacer su decisión.
    const chosen = readWindowState({ x: 0, y: 0, width: 1000, height: 700, maximised: false }, screens);
    expect(chosen.width).toBe(1000);
    expect(chosen.height).toBe(700);
  });

  it("un fichero corrupto no impide abrir", () => {
    // Lo guardado es una comodidad; si no se entiende, se ignora. Nunca es
    // motivo para que la aplicación no arranque.
    expect(readWindowState({ x: "ayer" } as never, screens)).toEqual(DEFAULT_WINDOW);
    expect(readWindowState({ width: Number.NaN, height: 10 } as never, screens)).toEqual(DEFAULT_WINDOW);
  });

  it("maximizada se recuerda como tal", () => {
    const saved = { x: 0, y: 0, width: 1200, height: 800, maximised: true };
    expect(readWindowState(saved, screens).maximised).toBe(true);
  });

  it("sin pantallas que consultar, se abre con lo de partida", () => {
    const saved = { x: 100, y: 100, width: 1200, height: 800, maximised: false };
    expect(readWindowState(saved, [])).toEqual(DEFAULT_WINDOW);
  });
});

describe("cuándo se guarda", () => {
  it("se guarda una vez, no en cada píxel del arrastre", async () => {
    vi.useFakeTimers();
    const write = vi.fn();
    const remember = rememberWindow(write, 300);
    for (let i = 0; i < 50; i++) remember({ x: i, y: 0, width: 1200, height: 800, maximised: false });
    expect(write).not.toHaveBeenCalled();
    vi.advanceTimersByTime(300);
    expect(write).toHaveBeenCalledTimes(1);
    expect(write.mock.calls[0]![0]).toMatchObject({ x: 49 });
    vi.useRealTimers();
  });

  it("guardar a la fuerza escribe ya: al cerrar no hay un después", () => {
    vi.useFakeTimers();
    const write = vi.fn();
    const remember = rememberWindow(write, 300);
    remember({ x: 10, y: 10, width: 1200, height: 800, maximised: false });
    remember.flush();
    expect(write).toHaveBeenCalledTimes(1);
    // Y no vuelve a escribir lo mismo cuando venza el temporizador.
    vi.advanceTimersByTime(300);
    expect(write).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
