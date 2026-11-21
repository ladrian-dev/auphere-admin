/**
 * Spec 073 (4.1): el buscador de Negocio. Puro. Sin tildes ni mayúsculas, para que
 * «laser» encuentre «Depilación láser».
 */
export function normalizeText(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

/** ¿Alguno de los textos lleva lo buscado? Sin nada buscado, todo coincide. */
export function matchesText(query: string, ...fields: (string | null | undefined)[]): boolean {
  const q = normalizeText(query);
  if (!q) return true;
  return fields.some((f) => (f ? normalizeText(f).includes(q) : false));
}
