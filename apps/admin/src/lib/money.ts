/**
 * Spec 033: the panel reads and writes money in US$ cents. Pure helpers
 * shared by the money tab and its tests.
 */

/** The largest single top-up the API accepts: US$ 10 000. */
export const MAX_TOPUP_CENTS = 1_000_000;

/**
 * «50», «50,5», «50.25», «1.250,75» → cents. ``null`` when the text is not an
 * amount with at most two decimals, or is out of 1 cent … US$ 10 000.
 * Accepts the Spanish comma and the dot; a thousands separator only when the
 * other separator is the decimal one.
 */
export function parseUsdToCents(text: string): number | null {
  const raw = text.trim().replace(/\s|US\$|\$/g, "");
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
  if (!Number.isSafeInteger(cents) || cents < 1 || cents > MAX_TOPUP_CENTS) return null;
  return cents;
}

/** What each ledger entry is, in the operator's words. */
export const LEDGER_KIND_LABEL: Record<string, string> = {
  debit: "Gasto",
  credit_admin: "Recarga de Auphere",
  credit_stripe: "Compra con tarjeta",
  expiry: "Caducidad del saldo",
  opening_credit: "Apertura del libro (ajuste a favor)",
  opening_debit: "Apertura del libro (ajuste en contra)",
  allocation_legacy: "Ajuste de tope antiguo",
};

/** Kinds that add money; the rest subtract it. */
export function isCredit(kind: string): boolean {
  return kind === "credit_admin" || kind === "credit_stripe" || kind === "opening_credit";
}
