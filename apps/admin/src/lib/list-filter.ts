/**
 * Spec 031 (R4.2, R5.2): the filter every list of the panel uses — a free
 * text that matches any of the row's words, accent- and case-insensitive,
 * plus exact-match facets. Pure, so the lists and their tests share it.
 */
export function fold(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

export function filterRows<T>(
  rows: readonly T[],
  query: string,
  text: (row: T) => (string | null | undefined)[],
  facets: { value: string; of: (row: T) => string | null | undefined }[] = [],
): T[] {
  const q = fold(query);
  return rows.filter((row) => {
    for (const f of facets) {
      if (f.value && (f.of(row) ?? "") !== f.value) return false;
    }
    if (!q) return true;
    return fold(text(row).filter(Boolean).join(" ")).includes(q);
  });
}
