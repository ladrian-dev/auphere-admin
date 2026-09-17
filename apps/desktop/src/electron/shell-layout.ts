/**
 * El reparto de la ventana — spec 010, Requisitos 1.1 y 1.4.
 *
 * Módulo puro: recibe medidas, devuelve medidas. Lo usa el proceso principal
 * para colocar la vista de la consola dentro del panel de contenido.
 *
 * **El invariante que sostiene el armazón**: el panel empieza *debajo* de la
 * franja superior y nunca la invade. La franja es de la vista de la aplicación
 * y es la única con región de arrastre; si otra vista se le pusiera encima,
 * la ventana dejaría de poder moverse por ahí (es el fallo conocido de Electron
 * con regiones de arrastre en vistas apiladas). El spike de la Fase 0 confirmó
 * que, sin solape, arrastrar funciona con la consola pintada en el panel.
 *
 * Todo sale entero y no negativo porque el canal no acepta otra cosa: un
 * rectángulo con decimales o con lados negativos se rechaza antes de llegar.
 */

/** Alto de la franja superior, en píxeles lógicos. */
export const STRIP_HEIGHT = 52;

/** Anchos de la lista lateral. Fuera de este rango, se acota. */
export const MIN_SIDEBAR = 220;
export const MAX_SIDEBAR = 320;

/**
 * Por debajo de este ancho de ventana la lista lateral se colapsa sola. No es
 * una preferencia de la persona: es que no cabe. Al ensancharse vuelve al ancho
 * que ella había elegido, que se guarda aparte.
 */
export const COLLAPSE_BELOW = 900;

export type Size = { width: number; height: number };
export type Rect = { x: number; y: number; width: number; height: number };

const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);
const whole = (value: number): number => Math.max(0, Math.round(value));

/**
 * El ancho real de la lista lateral: el que pidió la persona, acotado, o cero
 * si la ventana es demasiado estrecha para tenerla.
 */
export function sidebarWidthFor(windowWidth: number, preferred: number): number {
  if (windowWidth < COLLAPSE_BELOW) return 0;
  return whole(clamp(preferred, MIN_SIDEBAR, MAX_SIDEBAR));
}

/**
 * Dónde se pinta el panel de contenido: a la derecha de la lista lateral y
 * debajo de la franja. Es el rectángulo que recibe la vista de la consola.
 */
export function contentRect(window: Size, sidebarWidth: number): Rect {
  const width = whole(window.width);
  const height = whole(window.height);
  const sidebar = whole(clamp(sidebarWidth, 0, width));
  return {
    x: sidebar,
    y: Math.min(STRIP_HEIGHT, height),
    width: Math.max(0, width - sidebar),
    height: Math.max(0, height - STRIP_HEIGHT),
  };
}
