/**
 * Spec 038: the periods of the Consumo view. Pure, so it is tested alone.
 * «Este mes» is the calendar month (the clients' cap is monthly too, spec 033).
 */
export type Period = "month" | "7" | "30" | "90";

export const PERIODS: Array<{ key: Period; label: string }> = [
  { key: "month", label: "Este mes" },
  { key: "7", label: "7 días" },
  { key: "30", label: "30 días" },
  { key: "90", label: "90 días" },
];

export function parsePeriod(raw: string | undefined): Period {
  return PERIODS.some((p) => p.key === raw) ? (raw as Period) : "month";
}

export function periodQuery(p: Period): { days?: number; month?: boolean } {
  return p === "month" ? { month: true } : { days: Number(p) };
}

/** US$ from a decimal string, with cents; tiny model costs keep 4 decimals. */
export function formatUsd(value: string | number): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  const digits = n !== 0 && Math.abs(n) < 1 ? 4 : 2;
  return new Intl.NumberFormat("es", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: digits }).format(n);
}
