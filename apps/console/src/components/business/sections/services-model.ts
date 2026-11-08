import { formatAmount } from "@/lib/amount";
import type { Price } from "@/lib/backend/business-sections";
import { DURATION_MAX, DURATION_MIN, DURATION_STEP } from "@/lib/business-rules";

/**
 * El modelo de Servicios — spec 047 (T060, requisitos 11.1 y 11.7). Puro.
 *
 * Spec 056 (requisitos 5.2 y 13): las duraciones salen de `lib/business-rules.ts`
 * (las de la API, la ficha y Reservas) y el dinero se escribe y se lee con
 * `lib/amount.ts`, el único formato de la consola: el del idioma de la persona.
 */

/** Duración de un servicio reservable: de 5 a 480 min, en pasos de 5. */
export const DURATIONS: readonly number[] = Array.from(
  { length: (DURATION_MAX - DURATION_MIN) / DURATION_STEP + 1 },
  (_, i) => DURATION_MIN + i * DURATION_STEP,
);

/** «Gratis», «Sin precio» o el importe en el idioma de la persona («15.000 CLP», «15,50 €»). */
export function priceText(price: Price, currency: string, locale: string, words: { free: string; none: string }): string {
  if (price.kind === "free") return words.free;
  if (price.kind === "none" || price.amount_minor == null) return words.none;
  return formatAmount({ amount_minor: price.amount_minor, currency }, locale);
}

/** ¿El mismo precio? (para mandar solo lo que cambió). */
export function samePrice(a: Price, b: Price): boolean {
  return a.kind === b.kind && (a.kind !== "amount" || a.amount_minor === b.amount_minor);
}

export type PriceChoice = Price["kind"];

/**
 * Spec 055 (requisito 7.4): los servicios agrupados por categoría, por orden
 * alfabético y «Sin categoría» al final (`category: null`). Sin ninguna
 * categoría, un solo grupo: la lista se ve como siempre.
 */
export function byCategory<T extends { category?: string | null }>(items: readonly T[], locale: string): { category: string | null; items: T[] }[] {
  const groups = new Map<string | null, T[]>();
  for (const item of items) {
    const key = item.category || null;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  const named = [...groups.keys()].filter((k): k is string => k !== null).sort((a, b) => a.localeCompare(b, locale, { sensitivity: "base" }));
  return [...named, ...(groups.has(null) ? [null] : [])].map((category) => ({ category, items: groups.get(category) ?? [] }));
}

/** Las categorías que ya usa el negocio, para sugerirlas al escribir. */
export function categoriesOf(items: readonly { category?: string | null; archived?: boolean }[], locale: string): string[] {
  const seen = new Map<string, string>();
  for (const item of items) if (item.category && !item.archived && !seen.has(item.category.toLocaleLowerCase(locale))) seen.set(item.category.toLocaleLowerCase(locale), item.category);
  return [...seen.values()].sort((a, b) => a.localeCompare(b, locale, { sensitivity: "base" }));
}
