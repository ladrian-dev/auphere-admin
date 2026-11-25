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

/**
 * Spec 073 (4.3): las columnas que no dicen nada porque son iguales en todos. Sin
 * precio en ninguno, sin reserva en ninguno o el mismo agente para todos: la
 * tabla las quita y una línea lo dice una vez. Con un solo servicio no se resume.
 */
export function unusedColumns(items: readonly { price: { kind: string; amount_minor?: number }; bookable: boolean; used_by: { id: string; name: string }[] }[]): {
  price: boolean;
  booking: boolean;
  /** El agente (o los agentes) que los ofrece a todos; `null` si no es el mismo. */
  agent: string | null;
} {
  if (items.length < 2) return { price: false, booking: false, agent: null };
  const price = items.every((s) => s.price.kind === "none");
  const booking = items.every((s) => !s.bookable);
  const key = (s: (typeof items)[number]) => s.used_by.map((a) => a.id).sort().join(",");
  const first = items[0]!;
  const same = first.used_by.length > 0 && items.every((s) => key(s) === key(first));
  return { price, booking, agent: same ? first.used_by.map((a) => a.name).join(", ") : null };
}

/** Spec 073 (4.2): con más de 12 servicios, los grupos empiezan plegados salvo el primero. */
export const FOLD_AFTER = 12;

export function openGroupsByDefault(groups: readonly { category: string | null; items: readonly unknown[] }[]): Set<string | null> {
  const total = groups.reduce((n, g) => n + g.items.length, 0);
  if (total <= FOLD_AFTER) return new Set(groups.map((g) => g.category));
  return new Set(groups.slice(0, 1).map((g) => g.category));
}
