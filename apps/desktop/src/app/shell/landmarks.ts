/**
 * Las zonas del armazón, y el salto entre ellas — spec 010, Requisito 11.
 *
 * Una ventana con franja, lista lateral y panel tiene tres zonas, y tabular de
 * una a otra puede costar treinta pulsaciones. macOS resuelve eso con **F6 y
 * ⇧F6**: saltar de zona, no recorrerla. Es la convención que la guía de
 * escritorio pide y la que espera quien no usa ratón.
 *
 * Puro y circular: desde la última se vuelve a la primera. Un salto que se
 * atasca en el extremo obliga a contar zonas hacia atrás, que es peor que no
 * tenerlo.
 */

export const LANDMARKS = ["franja", "lateral", "panel"] as const;
export type Landmark = (typeof LANDMARKS)[number];

/** La siguiente zona en la dirección dada. Sin zona conocida, la primera. */
export function nextLandmark(from: Landmark | null, direction: 1 | -1): Landmark {
  if (from === null) return LANDMARKS[0];
  const index = LANDMARKS.indexOf(from);
  const next = (index + direction + LANDMARKS.length) % LANDMARKS.length;
  return LANDMARKS[next]!;
}
