/**
 * El color de fondo de la ventana nativa — spec 010, Requisito 2.7.
 *
 * Electron necesita este color **antes de que exista ninguna hoja de estilos**:
 * es lo que se ve entre que la ventana aparece y la vista pinta. Por eso es el
 * único sitio de la aplicación donde un color se escribe a mano en vez de salir
 * de un token.
 *
 * Y por eso `tests/window-colors.test.ts` lo compara con `tokens.css`: la
 * duplicación es inevitable, pero la **divergencia** no. Si alguien cambia el
 * fondo del sistema de diseño y no cambia esto, el test lo dice; si no, la
 * ventana volvería a dar un destello de otro color al abrirse, que es
 * exactamente el defecto que esta spec arregla.
 */

/* eslint-disable nexus-ui/no-raw-colors -- ver la cabecera: aquí no hay CSS todavía. */

/** `--background` del tema oscuro (`--color-ink-surface`), en sRGB. */
export const WINDOW_BACKGROUND_DARK = "#101512";

/** `--background` del tema claro (`--color-anti-flash`), en sRGB. */
export const WINDOW_BACKGROUND_LIGHT = "#f1f7f6";

/* eslint-enable nexus-ui/no-raw-colors */

export function windowBackground(dark: boolean): string {
  return dark ? WINDOW_BACKGROUND_DARK : WINDOW_BACKGROUND_LIGHT;
}
