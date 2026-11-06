import type { Money } from "@/lib/backend/reservas";

/**
 * Prices of Servicios (spec 043): the API sends the ISO 4217 minor unit
 * (`amount_minor`) with its currency. CLP has no decimals, so 15000 is
 * «$15.000». Intl knows how many decimals each currency has; nothing here
 * assumes cents. This is the business's price, not Auphere's consumption: it
 * never goes through `lib/money.ts` (which is US$ cents).
 */

export type Locale = "es" | "en";

/**
 * ISO 4217, as the API's `services_catalog` has it. Not Intl: for COP or HUF it
 * says 0 decimals while ISO, and so the stored minor unit, has 2 (spec 055).
 */
const ZERO_DECIMALS = new Set(["BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"]);
const THREE_DECIMALS = new Set(["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"]);

/** How many decimals the currency's minor unit has (CLP 0, EUR 2). */
export function minorDigits(currency: string): number {
  const code = currency.toUpperCase();
  return ZERO_DECIMALS.has(code) ? 0 : THREE_DECIMALS.has(code) ? 3 : 2;
}

/** «$15.000» (es-CL reads it the same) · `null` when there is no price. */
export function formatPrice(price: Money | null | undefined, locale: Locale): string | null {
  if (!price) return null;
  const digits = minorDigits(price.currency);
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency: price.currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(
      price.amount_minor / 10 ** digits,
    );
  } catch {
    return `${price.amount_minor / 10 ** digits} ${price.currency}`;
  }
}

export type ParsedPrice = { kind: "empty" } | { kind: "ok"; minor: number } | { kind: "invalid" };

/**
 * What the business types as a price. Empty is «no cost», not zero. Thousands
 * separators are allowed (people write «15.000» in Chile); decimals only for a
 * currency that has them.
 */
export function parsePrice(raw: string, currency: string): ParsedPrice {
  const text = raw.trim().replace(/\s/g, "");
  if (text === "") return { kind: "empty" };
  const digits = minorDigits(currency);
  if (digits === 0) {
    if (!/^\d{1,3}([.,]?\d{3})*$/.test(text)) return { kind: "invalid" };
    return { kind: "ok", minor: Number(text.replace(/[.,]/g, "")) };
  }
  const m = new RegExp(`^(\\d{1,9})(?:[.,](\\d{1,${digits}}))?$`).exec(text);
  if (!m) return { kind: "invalid" };
  return { kind: "ok", minor: Number(m[1]) * 10 ** digits + Number((m[2] ?? "").padEnd(digits, "0")) };
}

/** The price as it goes back into its field. */
export function priceInput(minor: number | null | undefined, currency: string): string {
  if (minor == null) return "";
  const digits = minorDigits(currency);
  return digits === 0 ? String(minor) : (minor / 10 ** digits).toFixed(digits);
}
