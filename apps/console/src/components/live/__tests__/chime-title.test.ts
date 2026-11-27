/**
 * Spec 082 — el título con el número (3.6) y el sonido que espera al primer
 * gesto (3.5): antes no suena ni pinta un error; desde el primero, sí.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { armChime, playChime, resetChimeForTests, setSoundOn, soundOn, SOUND_KEY } from "../chime";
import { withCount } from "../title-count";

describe("withCount", () => {
  it("pone «(N) » delante y lo cambia sin acumular", () => {
    expect(withCount("Reservas · Auphere", 3)).toBe("(3) Reservas · Auphere");
    expect(withCount("(3) Reservas · Auphere", 4)).toBe("(4) Reservas · Auphere");
  });
  it("«99+» a partir de 100", () => {
    expect(withCount("Bandeja", 100)).toBe("(99+) Bandeja");
    expect(withCount("(99+) Bandeja", 99)).toBe("(99) Bandeja");
  });
  it("a cero, sin número", () => {
    expect(withCount("(7) Bandeja", 0)).toBe("Bandeja");
    expect(withCount("Bandeja", 0)).toBe("Bandeja");
  });
});

class FakeAudio {
  static made = 0;
  state: "suspended" | "running" = "running";
  currentTime = 0;
  destination = {};
  constructor() {
    FakeAudio.made += 1;
  }
  resume() {
    this.state = "running";
    return Promise.resolve();
  }
  createOscillator() {
    const node = { type: "", frequency: { value: 0 }, connect: (n: unknown) => n, start: vi.fn(), stop: vi.fn() };
    return node;
  }
  createGain() {
    return { gain: { setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn() }, connect: (n: unknown) => n };
  }
}

describe("el sonido", () => {
  afterEach(() => {
    resetChimeForTests();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("antes de que la persona toque la página no suena ni lanza (3.5)", () => {
    vi.stubGlobal("AudioContext", FakeAudio);
    const disarm = armChime();
    expect(() => playChime()).not.toThrow();
    expect(playChime()).toBe(false);
    expect(FakeAudio.made).toBe(0);
    disarm();
  });

  it("desde el primer gesto, suena", () => {
    vi.stubGlobal("AudioContext", FakeAudio);
    const disarm = armChime();
    window.dispatchEvent(new Event("pointerdown"));
    expect(playChime()).toBe(true);
    disarm();
  });

  it("encendido por defecto y se guarda en el navegador (3.4)", () => {
    expect(soundOn()).toBe(true);
    setSoundOn(false);
    expect(window.localStorage.getItem(SOUND_KEY)).toBe("off");
    expect(soundOn()).toBe(false);
    setSoundOn(true);
    expect(soundOn()).toBe(true);
  });
});
