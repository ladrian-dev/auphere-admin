/**
 * La parte del líquido de Entrar que no necesita WebGL — spec 066, requisito 2.
 *
 * El puntero, el «dedo invisible» que lo mueve cuando nadie toca, la cola de
 * ondas y el tamaño del lienzo. Va aparte para poder probarla sin GPU: lo que se
 * ve depende del shader, pero cuándo se mueve, cuánto y hacia dónde se decide
 * aquí.
 *
 * Las coordenadas son las del shader: 0–1 en los dos ejes y la `y` hacia arriba.
 */

/** Sin tocar durante este tiempo, el dedo invisible toma el mando (R2.2). */
export const IDLE_AFTER_S = 2.5;
/** Cuántas ondas caben a la vez (R2.3). Tiene que coincidir con `W[4]` del shader. */
export const MAX_WAVES = 4;
/** Lo que vive una onda en el shader. Más vieja, no se pinta. */
export const WAVE_LIFE_S = 3.2;
/** El instante que pinta el cuadro quieto (R2.6): uno de los que mejor se ve. */
export const STILL_T = 6;

export type Pointer = {
  x: number;
  y: number;
  /** A dónde va. */
  tx: number;
  ty: number;
  /** Energía (0–1): cuánto deforma y cuánto ilumina. */
  e: number;
  te: number;
  /** Último instante en que lo movió una persona. */
  touched: number;
};

/** `[x, y, nació, fuerza]`, como lo lee el shader. */
export type Wave = [number, number, number, number];

export type LiquidState = { ptr: Pointer; waves: Wave[]; nextAuto: number };

export function initialState(): LiquidState {
  return {
    ptr: { x: 0.72, y: 0.62, tx: 0.72, ty: 0.62, e: 0, te: 0, touched: -1e9 },
    waves: [],
    nextAuto: 2.5,
  };
}

/** Una onda nueva. La más vieja sale si ya hay cuatro. */
export function addWave(s: LiquidState, x: number, y: number, at: number, strength: number): void {
  s.waves.push([x, y, at, strength]);
  while (s.waves.length > MAX_WAVES) s.waves.shift();
}

/** El puntero de una persona: lo lleva ahí, con toda la energía (R2.2). */
export function touch(s: LiquidState, x: number, y: number, at: number): void {
  s.ptr.tx = clamp01(x);
  s.ptr.ty = clamp01(y);
  s.ptr.te = 1;
  s.ptr.touched = at;
}

/**
 * Avanza un cuadro. `rand` se inyecta para que el test sea determinista.
 *
 * - Sin nadie, el dedo invisible traza una curva lenta y cada 4–6 s abre una
 *   onda suave (R2.1).
 * - Con alguien, la energía baja despacio si deja de moverse.
 * - El puntero y la energía se acercan a su objetivo con un suavizado
 *   exponencial: no salta aunque el ratón salte.
 */
export function step(s: LiquidState, t: number, dt: number, rand: () => number = Math.random): void {
  const p = s.ptr;
  if (t - p.touched > IDLE_AFTER_S) {
    p.tx = 0.55 + 0.32 * Math.sin(t * 0.23) + 0.1 * Math.sin(t * 0.61);
    p.ty = 0.6 + 0.26 * Math.cos(t * 0.19) + 0.08 * Math.sin(t * 0.47);
    p.te = 0.55;
    if (t > s.nextAuto) {
      addWave(s, 0.2 + rand() * 0.6, 0.45 + rand() * 0.45, t, 0.55);
      s.nextAuto = t + 4 + rand() * 2;
    }
  } else {
    p.te = Math.max(0, p.te - dt * 0.5);
  }
  const k = 1 - Math.exp(-dt * 6);
  p.x += (p.tx - p.x) * k;
  p.y += (p.ty - p.y) * k;
  p.e += (p.te - p.e) * (1 - Math.exp(-dt * 4));
}

/** Las ondas como las pide el shader: 4 × vec4, con huecos que no se pintan. */
export function wavesUniform(s: LiquidState): Float32Array {
  const out = new Float32Array(MAX_WAVES * 4);
  for (let i = 0; i < MAX_WAVES; i++) {
    const w = s.waves[i] ?? [0, 0, -99, 0];
    out.set(w, i * 4);
  }
  return out;
}

/**
 * El tamaño del lienzo: la mitad de los píxeles de la caja, con la densidad
 * limitada a 2 (R2.4). El líquido es blando: a media resolución no se nota y
 * pinta cuatro veces menos.
 */
export function canvasSize(cssW: number, cssH: number, dpr: number): [number, number] {
  const d = Math.min(2, dpr > 0 ? dpr : 1) * 0.5;
  return [Math.max(2, Math.round(cssW * d)), Math.max(2, Math.round(cssH * d))];
}

/**
 * Cuadros lentos seguidos: si la máquina no puede, el líquido se queda quieto
 * en lugar de arrastrar la página (plan, «Rendimiento»).
 */
export const SLOW_FRAME_MS = 50;
export const SLOW_FRAMES_TO_STILL = 30;

export function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}
