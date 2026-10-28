import type { Locale } from "@/i18n/t";

/**
 * Money and numbers, exactly as the console writes them (spec 031, R4.3):
 * integer cents of USD from the API, `Intl` with the person's locale.
 * Mirrors `apps/console/src/lib/money.ts` and `@nexus/ui`'s `formatNumber`.
 */
export function formatMoney(cents: number | null | undefined, locale: Locale, currency = "USD"): string {
  if (cents == null || !Number.isFinite(cents)) return "—";
  return new Intl.NumberFormat(locale, { style: "currency", currency: known(currency) }).format(cents / 100);
}

export function formatMoneyCompact(cents: number | null | undefined, locale: Locale, currency = "USD"): string {
  if (cents == null || !Number.isFinite(cents)) return "—";
  if (Math.abs(cents) < 100_000) return formatMoney(cents, locale, currency);
  return new Intl.NumberFormat(locale, { style: "currency", currency: known(currency), notation: "compact", maximumFractionDigits: 1 }).format(
    cents / 100,
  );
}

/**
 * Spec 047: the balance says its currency (`balance.currency`), in hundredths
 * of it like the US$ of spec 027. A code `Intl` would refuse falls back to
 * US$, the console's, rather than breaking the screen.
 */
function known(currency: string): string {
  return /^[A-Z]{3}$/.test(currency) ? currency : "USD";
}

export function formatNumber(value: number | null | undefined, locale: Locale): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(locale).format(value);
}

export function clock(at: string | Date, locale: Locale): string {
  return new Date(at).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

export function shortDay(day: string, locale: Locale): string {
  // `day` is an ISO date (YYYY-MM-DD) in UTC: read it as noon UTC so no zone moves it a day.
  return new Date(`${day}T12:00:00Z`).toLocaleDateString(locale, { day: "numeric", month: "short", timeZone: "UTC" });
}
