/**
 * Spec 047 (T172): what the operator's levers share — the reason that goes to
 * the audit, who did something, and money in `amount_micros`. Pure, so it is
 * tested on its own; the API checks it all again.
 */
import { MICROS_PER_UNIT, formatMoney } from "@nexus/ui";

export type Currency = "EUR" | "USD";

/** The account's currencies (research D26): today's partners are in USD. */
export const CURRENCIES: readonly Currency[] = ["USD", "EUR"];

export const CURRENCY_NAME: Record<Currency, string> = { USD: "Dólares (USD)", EUR: "Euros (EUR)" };

/** The currency inside a sentence: «en dólares (USD)». */
export const CURRENCY_IN_TEXT: Record<Currency, string> = { USD: "dólares (USD)", EUR: "euros (EUR)" };

export const REASON_MIN = 3;
export const REASON_MAX = 300;

/** The reason goes to the audit: between 3 and 300 characters, like the API. */
export function reasonError(reason: string): string | null {
  const length = reason.trim().length;
  if (length === 0) return "Hace falta el motivo.";
  if (length < REASON_MIN) return `El motivo necesita al menos ${REASON_MIN} caracteres.`;
  if (length > REASON_MAX) return `El motivo admite como mucho ${REASON_MAX} caracteres.`;
  return null;
}

/**
 * Who did it, in a few words. The API writes `operator:{email}` for Auphere,
 * `console:{email}` for a person of the partner and `companion:{user_id}` when
 * the Companion did it on their behalf.
 */
export function actorLabel(actor: string | null | undefined): string {
  if (!actor) return "—";
  const [kind, ...rest] = actor.split(":");
  const who = rest.join(":");
  if (!who) return actor;
  if (kind === "operator" || kind === "console") return who;
  if (kind === "companion") return `Companion (${who.slice(0, 8)})`;
  return actor;
}

/**
 * «50», «50,5», «50.25», «1.250,75» → micros (hundred-thousandths of the
 * currency: 50 → 5_000_000). Zero is a valid cap. `null` when the text is not
 * an amount with at most two decimals.
 */
export function parseAmountToMicros(text: string): number | null {
  const raw = text.trim().replace(/\s|US\$|USD|EUR|\$|€/gi, "");
  if (!raw) return null;
  let normalised: string;
  if (raw.includes(",") && raw.includes(".")) {
    // The last separator is the decimal one.
    const decimalComma = raw.lastIndexOf(",") > raw.lastIndexOf(".");
    normalised = decimalComma ? raw.replace(/\./g, "").replace(",", ".") : raw.replace(/,/g, "");
  } else {
    normalised = raw.replace(",", ".");
  }
  if (!/^\d+(\.\d{1,2})?$/.test(normalised)) return null;
  const [whole, frac = ""] = normalised.split(".");
  const cents = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  const micros = cents * (MICROS_PER_UNIT / 100);
  return Number.isSafeInteger(micros) ? micros : null;
}

/** Micros of a known currency, as the console writes money: «50,00 USD», «1.234,50 €». */
export function formatMicros(micros: number | null | undefined, currency: Currency): string {
  if (micros === null || micros === undefined) return formatMoney(null, currency);
  return formatMoney(micros / MICROS_PER_UNIT, currency);
}

const EDIT = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false });

/** Micros as the amount field shows them to edit: 5_000_000 → «50,00» (what `parseAmountToMicros` reads). */
export function microsToInput(micros: number): string {
  return EDIT.format(micros / MICROS_PER_UNIT);
}

const PLAIN = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 5, useGrouping: true });

/** The amount alone, with up to five decimals so a difference of one micro shows. */
export function formatMicrosPlain(micros: number | null | undefined): string {
  if (micros === null || micros === undefined || !Number.isFinite(micros)) return "—";
  return PLAIN.format(micros / MICROS_PER_UNIT);
}

/**
 * The ledger's differences: exact to the micro and in the currency the API
 * names (the bag's or the account's), with the console's symbol — «€» for the
 * euro, the code for anything else.
 */
export function formatMicrosExact(micros: number | null | undefined, currency: string): string {
  const plain = formatMicrosPlain(micros);
  if (plain === "—") return plain;
  return `${plain}\u00a0${currency === "EUR" ? "€" : currency}`;
}
