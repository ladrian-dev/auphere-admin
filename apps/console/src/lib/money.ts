/**
 * Spec 027: the partner reads and writes money. The API sends and receives
 * integer cents of USD; the console never sees credits and never knows the
 * rate. These two functions are the only place money is formatted or parsed.
 */

export type Locale = "es" | "en";

/** Cents as the partner reads them: «12,35 US$» (es) · «$12.35» (en). */
export function formatMoney(cents: number | null | undefined, locale: Locale = "es"): string {
  if (cents == null || !Number.isFinite(cents)) return "—";
  return new Intl.NumberFormat(locale, { style: "currency", currency: "USD" }).format(cents / 100);
}

/** Compact for tight cards: «1,2 mil US$». Below 1 000 US$ it is the full amount. */
export function formatMoneyCompact(cents: number | null | undefined, locale: Locale = "es"): string {
  if (cents == null || !Number.isFinite(cents)) return "—";
  if (Math.abs(cents) < 100_000) return formatMoney(cents, locale);
  return new Intl.NumberFormat(locale, { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(cents / 100);
}

export type ParsedMoney = { kind: "empty" } | { kind: "money"; cents: number } | { kind: "invalid" };

/**
 * What the partner types in an amount field, as cents. Comma or point,
 * up to two decimals, no sign, no thousands separators. Empty is not zero
 * (QA-26: Number("") === 0 was a bug); an explicit 0 is a valid 0.
 */
export function parseMoney(raw: string): ParsedMoney {
  const text = raw.trim();
  if (text === "") return { kind: "empty" };
  const m = /^(\d{1,7})(?:[.,](\d{1,2}))?$/.exec(text);
  if (!m) return { kind: "invalid" };
  const cents = Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
  return { kind: "money", cents };
}

/** Cents as the partner edits them in a field: «25,50» (es) · «25.50» (en). */
export function moneyInputValue(cents: number, locale: Locale = "es"): string {
  const text = (Math.max(0, cents) / 100).toFixed(2);
  return locale === "es" ? text.replace(".", ",") : text;
}
