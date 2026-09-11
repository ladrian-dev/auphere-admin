/**
 * Dónde se abre la ventana — spec 003, Requisito 12.4.
 *
 * Una aplicación de escritorio recuerda dónde la dejaste. Lo que aquí importa
 * no es guardar, que es trivial, sino **no restaurar donde no se puede ver**:
 * quien cerró la aplicación en un monitor que hoy no está no debe encontrarse
 * una ventana fuera de pantalla, que desde fuera es idéntico a que no arranque.
 *
 * Todo lo que decide vive aquí, sin Electron delante, para poder probarlo: la
 * cáscara solo le pasa lo guardado y las pantallas que hay.
 */

export type WindowState = {
  x?: number;
  y?: number;
  width: number;
  height: number;
  maximised: boolean;
};

export type ScreenArea = { x: number; y: number; width: number; height: number };

/** El tamaño de partida. También el repliegue cuando lo guardado no sirve. */
export const DEFAULT_WINDOW: WindowState = { width: 1280, height: 820, maximised: false };

/** Lo más pequeña que puede abrirse y seguir siendo usable: tres columnas.
 *  No es el tamaño de partida — quien encogió la ventana a 1200 la quiere a
 *  1200, y devolvérsela a 1280 sería deshacerle la decisión. */
export const MIN_WINDOW = { width: 900, height: 600 } as const;

const isFiniteNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function isSane(saved: unknown): saved is WindowState {
  if (!saved || typeof saved !== "object") return false;
  const s = saved as Record<string, unknown>;
  if (!isFiniteNumber(s.width) || !isFiniteNumber(s.height)) return false;
  if (s.x !== undefined && !isFiniteNumber(s.x)) return false;
  if (s.y !== undefined && !isFiniteNumber(s.y)) return false;
  return true;
}

/** ¿Se ve al menos una esquina de la ventana en alguna pantalla? */
function visibleIn(state: WindowState, screens: ScreenArea[]): boolean {
  if (state.x === undefined || state.y === undefined) return false;
  return screens.some(
    (s) =>
      state.x! + state.width > s.x &&
      state.x! < s.x + s.width &&
      state.y! + state.height > s.y &&
      state.y! < s.y + s.height,
  );
}

/**
 * Lo guardado, corregido contra las pantallas de hoy.
 *
 * Reglas, en este orden: lo que no se entiende se ignora; lo que no cabe se
 * encoge; lo que no se ve se centra; lo que es demasiado pequeño para usarse
 * vuelve al tamaño de partida.
 */
export function readWindowState(saved: unknown, screens: ScreenArea[]): WindowState {
  if (!isSane(saved) || screens.length === 0) return { ...DEFAULT_WINDOW };
  const screen = screens[0]!;
  const width = Math.min(Math.max(saved.width, MIN_WINDOW.width), screen.width);
  const height = Math.min(Math.max(saved.height, MIN_WINDOW.height), screen.height);
  const candidate: WindowState = {
    ...saved,
    width,
    height,
    maximised: saved.maximised === true,
  };
  if (visibleIn(candidate, screens)) return candidate;
  return {
    x: Math.round(screen.x + (screen.width - width) / 2),
    y: Math.round(screen.y + (screen.height - height) / 2),
    width,
    height,
    maximised: candidate.maximised,
  };
}

export type Remember = ((state: WindowState) => void) & { flush: () => void };

/**
 * Guarda **una vez** cuando la ventana deja de moverse.
 *
 * Arrastrar una ventana produce decenas de eventos por segundo; escribir en
 * cada uno es una escritura en disco por píxel. `flush` existe para el cierre,
 * donde no hay un «después» en el que vencer el temporizador.
 */
export function rememberWindow(write: (state: WindowState) => void, waitMs = 400): Remember {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending: WindowState | null = null;

  const save = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (pending === null) return;
    const state = pending;
    pending = null;
    write(state);
  };

  const remember = ((state: WindowState) => {
    pending = state;
    if (timer) clearTimeout(timer);
    timer = setTimeout(save, waitMs);
  }) as Remember;
  remember.flush = save;
  return remember;
}
