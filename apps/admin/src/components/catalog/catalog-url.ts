import type { CatalogTab } from "@nexus/ui";

/**
 * Spec 035: a catalog's state lives in the page address (`q`, `tab`, `cat`),
 * the same three keys as the partner console (spec 018 R4.4), so a shared
 * link opens the same view and «atrás» undoes a filter.
 */
export type CatalogState = { q: string; tab: CatalogTab; category: string | null };

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

export function catalogState(params: RawParams): CatalogState {
  const tab = one(params.tab) === "active" ? "active" : "all";
  const category = one(params.cat).trim();
  return { q: one(params.q).trim(), tab, category: category === "" ? null : category };
}

/** The address after changing one gesture; other parameters are kept. */
export function catalogHref(base: string, current: string, next: Partial<CatalogState>): string {
  const out = new URLSearchParams(current);
  const set = (key: string, value: string) => (value === "" ? out.delete(key) : out.set(key, value));
  if (next.q !== undefined) set("q", next.q.trim());
  if (next.tab !== undefined) set("tab", next.tab === "active" ? "active" : "");
  if (next.category !== undefined) set("cat", next.category ?? "");
  const qs = out.toString();
  return qs ? `${base}?${qs}` : base;
}
