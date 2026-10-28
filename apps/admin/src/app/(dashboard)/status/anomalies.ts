/**
 * Spec 047 (T172; requisitos 54.9, 43.9 y 2.6): how the operator reads the
 * anomalies on Estado — the router's, the ledger's and Meta's. Pure, so it is
 * tested on its own.
 */
import type { RouterAnomalies } from "@/lib/backend-models";
import type { LedgerDiff, MetaDiff, Reconciliations } from "@/lib/backend-levers";
import { formatMicrosExact } from "@/lib/levers";

/** The periods the page offers; the API accepts 1 to 90 days. */
export const DAY_OPTIONS = [1, 7, 30, 90] as const;
export const DEFAULT_DAYS = 7;

/** `?days=` → one of the offered periods; anything else is the default. */
export function parseDays(raw: string | string[] | undefined): number {
  const value = Number(Array.isArray(raw) ? raw[0] : raw);
  return (DAY_OPTIONS as readonly number[]).includes(value) ? value : DEFAULT_DAYS;
}

/** The router reads a moment, not a number of days. */
export function sinceFor(days: number, now: Date = new Date()): string {
  return new Date(now.getTime() - days * 86_400_000).toISOString();
}

export function daysLabel(days: number): string {
  return days === 1 ? "Último día" : `Últimos ${days} días`;
}

/**
 * One difference of the ledger, in words, exact to the micro and in its
 * currency: a bag's is the bag's, the account's is the account's.
 */
export function ledgerExplain(diff: LedgerDiff): { what: string; detail: string } {
  const money = (micros: number) => formatMicrosExact(micros, diff.currency);
  if (diff.kind === "bag") {
    const last = diff.last_entry === null ? "sin asientos" : `el último asiento dice ${money(diff.last_entry)}`;
    return {
      what: diff.tenant_name ? `Bolsa de ${diff.tenant_name}` : "Bolsa de un cliente",
      detail: `Saldo guardado ${money(diff.balance)}; la suma de sus asientos da ${money(diff.entries)} y ${last}.`,
    };
  }
  return {
    what: "Cuenta del partner",
    detail: `El libro de la cuenta sacó ${money(diff.ledger)} para las bolsas; los traspasos dicen ${money(diff.transfers)}.`,
  };
}

/** `diff = meta_count − stored_count`: positive, messages Meta delivered that are not stored. */
export function metaExplain(row: MetaDiff): string {
  if (row.diff > 0) return row.diff === 1 ? "Falta 1 mensaje por guardar" : `Faltan ${row.diff} mensajes por guardar`;
  const extra = -row.diff;
  return extra === 1 ? "Hay 1 mensaje guardado de más" : `Hay ${extra} mensajes guardados de más`;
}

export type AnomalyTotals = {
  reserve: number;
  noModel: number;
  waiting: number;
  ledger: number;
  meta: number;
};

/** The figures of the summary; a source that could not be read counts as `null`. */
export function anomalyTotals(
  router: RouterAnomalies | null,
  recon: Pick<Reconciliations, "ledger" | "meta"> | null,
): { [K in keyof AnomalyTotals]: number | null } {
  return {
    reserve: router ? router.items.filter((a) => a.kind === "reserve_model").length : null,
    noModel: router ? router.items.filter((a) => a.kind === "no_model").length : null,
    waiting: router ? router.waiting_no_model.reduce((n, w) => n + w.conversations, 0) : null,
    ledger: recon ? recon.ledger.length : null,
    meta: recon ? recon.meta.length : null,
  };
}
