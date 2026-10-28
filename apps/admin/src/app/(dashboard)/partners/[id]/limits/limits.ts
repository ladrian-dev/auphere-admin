/**
 * Spec 047 (T172; requisitos 43.1, 46.5 y 54.5): the words and the rules of a
 * partner's «Construcción y pruebas» cap and of its account currency. Pure, so
 * it is tested on its own; the API checks it all again
 * (`api/admin/partner_money.py`).
 */
import type { AccountCurrencyChange, BuildBudget } from "@/lib/backend-levers";
import { CURRENCY_IN_TEXT, formatMicros, parseAmountToMicros, reasonError, type Currency } from "@/lib/levers";

export const BUDGET_ERRORS: Record<string, string> = {
  // The form sends the account's currency; this only happens if it changed meanwhile.
  currency_mismatch: "La moneda de la cuenta acaba de cambiar. Recarga la página y vuelve a guardar el tope.",
  unknown_partner: "Ese partner no existe.",
};

export const CURRENCY_ERRORS: Record<string, string> = {
  no_account: "Este partner todavía no tiene cuenta de saldo: no hay nada que convertir.",
  fx_unavailable: "No hay cambio del BCE para hoy. Vuelve a intentarlo más tarde.",
  unknown_partner: "Ese partner no existe.",
};

export type BudgetInput = { amount: string; currency: Currency; reason: string };

export type BudgetCheck =
  | { ok: true; cap: { amount_micros: number; currency: Currency }; reason: string }
  | { ok: false; errors: { amount?: string; reason?: string } };

/** The cap is money with at most two decimals (zero stops building); never tokens. */
export function checkBudget(input: BudgetInput): BudgetCheck {
  const errors: { amount?: string; reason?: string } = {};
  const micros = parseAmountToMicros(input.amount);
  if (!input.amount.trim()) errors.amount = "Escribe el tope.";
  else if (micros === null) errors.amount = "Escribe un importe con dos decimales como mucho, por ejemplo 50 o 49,90.";
  const why = reasonError(input.reason);
  if (why) errors.reason = why;
  if (errors.amount || errors.reason || micros === null) return { ok: false, errors };
  return { ok: true, cap: { amount_micros: micros, currency: input.currency }, reason: input.reason.trim() };
}

export const BUDGET_STATE: Record<BuildBudget["state"], { label: string; tone: "positive" | "warning" | "danger" }> = {
  ok: { label: "Con margen", tone: "positive" },
  warning: { label: "Cerca del tope", tone: "warning" },
  exhausted: { label: "Agotada", tone: "danger" },
};

/** «Octubre de 2026: gastado 12,30 USD de 50,00 USD.» */
export function budgetSummary(budget: BuildBudget): string {
  const month = monthLabel(budget.month);
  return `${month.charAt(0).toUpperCase()}${month.slice(1)}: gastado ${formatMicros(
    budget.spent.amount_micros,
    budget.spent.currency,
  )} de ${formatMicros(budget.cap.amount_micros, budget.cap.currency)}.`;
}

/** The other currency: the account only has euros or dollars. */
export function otherCurrency(currency: Currency): Currency {
  return currency === "USD" ? "EUR" : "USD";
}

const MONTH = new Intl.DateTimeFormat("es", { month: "long", year: "numeric", timeZone: "UTC" });

/** `2026-10-01` → «octubre de 2026». */
export function monthLabel(isoDate: string): string {
  const d = new Date(`${isoDate.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? isoDate : MONTH.format(d);
}

/** What the operator is about to do, said before doing it. */
export function currencyConfirmText(to: Currency): string {
  return (
    `La cuenta pasa a ${CURRENCY_IN_TEXT[to]}. Se convierte el saldo que le queda (lo comprado, lo incluido ` +
    "y el límite de crédito) y el tope de «Construcción y pruebas» de este mes, al cambio del BCE de hoy, " +
    "y queda un asiento con el cambio aplicado. Volver a la moneda de antes es otra conversión."
  );
}

/** What happened, in one sentence. */
export function currencyResultText(result: AccountCurrencyChange): string {
  if (!result.changed) return `La cuenta ya estaba en ${result.currency}: no se convirtió nada.`;
  const rate = result.fx ? Number(result.fx.rate).toLocaleString("es-ES", { maximumFractionDigits: 6 }) : null;
  const when = result.fx?.date ? ` del ${result.fx.date}` : "";
  const balance =
    result.purchased_micros !== undefined
      ? ` Saldo comprado que queda: ${formatMicros(result.purchased_micros, result.currency)}.`
      : "";
  return `Cuenta convertida de ${result.from ?? "—"} a ${result.currency}${rate ? ` a ${rate} (BCE${when})` : ""}.${balance}`;
}
