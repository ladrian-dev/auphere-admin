/**
 * Las cuentas puras del dinero de la consola nueva (spec 047, T159): leer lo que
 * se escribe en un campo de importe, escribir un importe en `es-ES`, el cambio
 * del BCE, el recibo de «Asignar saldo» con «Faltan» y el aviso ámbar, y las
 * columnas de «Gasto por día». Sin React y sin la API: se prueban solas.
 *
 * Las cifras de verdad las pone la API (requisito 46.7); lo que se calcula aquí
 * es la vista previa que se enseña antes de confirmar.
 */
import { formatMoney, MICROS_PER_UNIT, type BlockChartColumn } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";
import type { Currency, MigrationProposal, Money, Receipt, UsageDaily, UsageLine } from "@/lib/backend/money-types";

export type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Una centésima de la moneda en cien milésimas. */
const MICROS_PER_CENT = MICROS_PER_UNIT / 100;
/** El importe más alto que se puede escribir: 9.999.999,99. */
export const MAX_AMOUNT_MICROS = 999_999_999 * MICROS_PER_CENT;
/** «Avisarme cuando le quede menos del 20 %» y el aviso ámbar de la cuenta (45.4). */
export const LOW_SHARE = 0.2;
/** Las cantidades rápidas del modal, en la moneda de la bolsa (45.2). */
export const QUICK_AMOUNTS = [10, 20, 50, 100] as const;
/** «Pedir saldo» admite una nota de hasta 280 caracteres (45.7). */
export const REQUEST_NOTE_MAX = 280;

export const money = (amountMicros: number, currency: Currency): Money => ({ amount_micros: Math.trunc(amountMicros), currency });
export const units = (n: number) => Math.round(n * MICROS_PER_UNIT);

// ── leer un importe ────────────────────────────────────────────────────────

export type ParsedAmount = { kind: "empty" } | { kind: "invalid" } | { kind: "ok"; micros: number };

/**
 * Lo que la persona escribe en «Otra cantidad», en cien milésimas. Admite coma
 * o punto decimal, hasta dos decimales, y los puntos de miles de `es-ES`
 * («1.234,50»). Un punto seguido de tres cifras es de miles, no decimal. Vacío
 * no es cero, y no hay signo: lo que se resta se elige con la acción, no con
 * un menos.
 */
export function parseAmount(raw: string): ParsedAmount {
  const text = raw.replace(/[\s  ]/g, "");
  if (text === "") return { kind: "empty" };
  let whole: string;
  let frac = "";
  const grouped = /^(\d{1,3}(?:\.\d{3})+)(?:,(\d{1,2}))?$/.exec(text);
  const plain = /^(\d{1,7})(?:[.,](\d{1,2}))?$/.exec(text);
  if (grouped) {
    whole = grouped[1]!.replaceAll(".", "");
    frac = grouped[2] ?? "";
  } else if (plain) {
    whole = plain[1]!;
    frac = plain[2] ?? "";
  } else {
    return { kind: "invalid" };
  }
  if (whole.length > 7) return { kind: "invalid" };
  const cents = Number(whole) * 100 + Number(frac.padEnd(2, "0"));
  return { kind: "ok", micros: cents * MICROS_PER_CENT };
}

/** Un importe como se edita en un campo: «25,50». */
export function amountInputValue(micros: number): string {
  return (Math.max(0, micros) / MICROS_PER_UNIT).toFixed(2).replace(".", ",");
}

// ── escribir un importe ────────────────────────────────────────────────────

/**
 * «1.234,50 €» · «60,00 USD» (45.9). Los saldos se redondean hacia abajo y el
 * gasto al céntimo más cercano (43.10): un saldo nunca promete un céntimo que
 * no hay.
 */
export function moneyText(value: Money | null | undefined, round: "down" | "nearest" = "nearest"): string {
  if (!value) return formatMoney(null, "EUR");
  const cents = value.amount_micros / MICROS_PER_CENT;
  const rounded = round === "down" ? Math.floor(cents + 1e-9) : Math.round(cents);
  return formatMoney(rounded / 100, value.currency);
}

/** El mismo formato, para un número suelto en cien milésimas (los ejes de la gráfica). */
export function microsText(micros: number, currency: Currency): string {
  return formatMoney(Math.round(micros / MICROS_PER_CENT) / 100, currency);
}

// ── el cambio del BCE ──────────────────────────────────────────────────────

/** Cuántos dólares vale un euro, desde un cambio de `from` a `to`. */
export function eurUsdOf(rate: string | number, from: Currency, to: Currency): number | null {
  const r = typeof rate === "number" ? rate : Number(rate);
  if (!Number.isFinite(r) || r <= 0 || from === to) return null;
  return from === "EUR" ? r : 1 / r;
}

/** Un importe al otro lado del cambio, con el euro como base (como el BCE). */
export function convertMicros(micros: number, from: Currency, to: Currency, eurUsd: number): number {
  if (from === to) return micros;
  return Math.round(from === "EUR" ? micros * eurUsd : micros / eurUsd);
}

const RATE = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const FX_DATE = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** «26 oct 2026», para el día del cambio. */
export function fxDateText(date: string | null): string | null {
  if (!date) return null;
  const d = new Date(`${date}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : FX_DATE.format(d);
}

/** «1 € = 1,0852 USD · BCE 26 oct 2026». */
export function fxLine(t: T, eurUsd: number, date: string | null): string {
  const day = fxDateText(date);
  const rate = RATE.format(eurUsd);
  return day ? t("money.fx.line", { rate, date: day }) : t("money.fx.lineNoDate", { rate });
}

/** La línea del BCE del recibo de la API; `null` si la bolsa y la cuenta van en la misma moneda. */
export function receiptFxLine(t: T, receipt: Receipt): string | null {
  const eurUsd = eurUsdOf(receipt.fx.rate, receipt.debited_from_account.currency, receipt.assigned.currency);
  return eurUsd == null ? null : fxLine(t, eurUsd, receipt.fx.date);
}

// ── el recibo de «Asignar saldo» ───────────────────────────────────────────

export type AssignPreview = {
  /** El saldo de la bolsa antes y después, en su moneda. */
  before: Money;
  assigned: Money;
  after: Money;
  /** Lo que sale de la cuenta, en la moneda de la cuenta. */
  debit: Money;
  /** Lo que queda en la cuenta; nunca menos de cero en la vista previa. */
  left: Money;
  /** «Faltan {importe}» (45.3), en la moneda de la cuenta; `null` si llega. */
  missing: Money | null;
  /** La cuenta se queda con menos del 20 % de lo que tenía (45.4). */
  lowAccount: boolean;
  /** El cambio usado, si las monedas son distintas. */
  eurUsd: number | null;
};

/**
 * La vista previa del recibo. Si la bolsa y la cuenta van en monedas distintas
 * hace falta el cambio del día; sin él no hay vista previa (`null`), igual que
 * la API no deja asignar sin cambio.
 */
export function assignPreview(input: { amountMicros: number; bag: Money; available: Money; eurUsd: number | null }): AssignPreview | null {
  const { amountMicros, bag, available } = input;
  const cross = bag.currency !== available.currency;
  if (cross && input.eurUsd == null) return null;
  const debitMicros = cross ? convertMicros(amountMicros, bag.currency, available.currency, input.eurUsd!) : amountMicros;
  const leftMicros = available.amount_micros - debitMicros;
  const missing = leftMicros < 0 ? money(-leftMicros, available.currency) : null;
  return {
    before: bag,
    assigned: money(amountMicros, bag.currency),
    after: money(bag.amount_micros + amountMicros, bag.currency),
    debit: money(debitMicros, available.currency),
    left: money(Math.max(0, leftMicros), available.currency),
    missing,
    lowAccount: !missing && amountMicros > 0 && leftMicros < LOW_SHARE * available.amount_micros,
    eurUsd: cross ? input.eurUsd : null,
  };
}

/** «Recargar mi cuenta» lleva a comprar lo que falta, en unidades enteras hacia arriba. */
export function rechargeHref(missing: Money): string {
  const whole = Math.max(1, Math.ceil(missing.amount_micros / MICROS_PER_UNIT));
  return `/billing?recargar=${whole}`;
}

/** El aviso final (45.5): «Asignados 20,00 USD a Flor y Encanto. En tu cuenta quedan 221,48 €.» */
export function assignedText(t: T, receipt: Receipt, name: string): string {
  return t("money.assign.done", { amount: moneyText(receipt.assigned), name, left: moneyText(receipt.account_left, "down") });
}

// ── «Pedir saldo» ──────────────────────────────────────────────────────────

const RELATIVE = new Intl.RelativeTimeFormat("es-ES", { numeric: "always" });

/** «Pedido hace 5 minutos» · «Pedido hace un momento» · «Pedido hoy» si no se sabe cuándo (45.7). */
export function requestedText(t: T, at: number | null, now: number = Date.now()): string {
  if (at == null) return t("money.request.today");
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 60) return t("money.request.justNow");
  const minutes = Math.round(seconds / 60);
  const ago = minutes < 60 ? RELATIVE.format(-minutes, "minute") : RELATIVE.format(-Math.round(minutes / 60), "hour");
  return t("money.request.ago", { ago });
}

/** La nota de «Pedir saldo»: lo que queda por escribir y si se pasa. */
export function noteProblem(note: string): "too_long" | null {
  return note.trim().length > REQUEST_NOTE_MAX ? "too_long" : null;
}

// ── las partidas y la gráfica ──────────────────────────────────────────────

export const LINE_LABEL: Record<UsageLine, MessageKey> = {
  conversations: "money.line.conversations",
  meta: "money.line.meta",
  build: "money.line.build",
  companion: "money.line.companion",
};

/** Lo que la gráfica enseña sin filtro: lo que sale del dinero del partner (46.1). */
export const PARTNER_PAYS: readonly UsageLine[] = ["conversations", "companion"];

export function parseLine(raw: string | undefined): UsageLine | null {
  return raw === "conversations" || raw === "meta" || raw === "build" || raw === "companion" ? raw : null;
}

export function parseDays(raw: string | undefined): 7 | 30 | 90 {
  const n = Number(raw);
  return n === 7 || n === 90 ? n : 30;
}

const DAY_LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" });
const DAY_SHORT = new Intl.DateTimeFormat("es-ES", { weekday: "short", timeZone: "UTC" });

/** Las series de la gráfica: la partida elegida o, sin filtro, las dos que paga el partner. */
export function chartLines(daily: Pick<UsageDaily, "lines">, line: UsageLine | null): UsageLine[] {
  if (line) return [line];
  return PARTNER_PAYS.filter((l) => daily.lines.includes(l));
}

/**
 * Las columnas de la gráfica de bloques: un día por columna, el valor de cada
 * partida en cien milésimas. La etiqueta del eje es el día del mes («27»), el
 * día de la semana con 7 días, y «Hoy» en la última.
 */
export function chartColumns(t: T, daily: UsageDaily, lines: readonly UsageLine[]): BlockChartColumn[] {
  const n = daily.days.length;
  return daily.days.map((day, i) => {
    const d = new Date(`${day}T00:00:00Z`);
    const label = i === n - 1 ? t("money.chart.today") : n <= 7 ? DAY_SHORT.format(d) : String(d.getUTCDate());
    const title = DAY_LONG.format(d);
    return {
      key: day,
      label,
      title: title.charAt(0).toUpperCase() + title.slice(1),
      values: lines.map((l) => daily.series[l]?.[i] ?? 0),
    };
  });
}

export type ChartRow = { day: string; title: string; values: number[]; total: number };

/** La tabla equivalente de la gráfica (para lectores de pantalla y para comprobar las cuentas). */
export function chartTable(t: T, daily: UsageDaily, lines: readonly UsageLine[]): ChartRow[] {
  return chartColumns(t, daily, lines).map((c) => {
    const values = c.values ?? [];
    return { day: c.key, title: c.title, values, total: values.reduce((a, b) => a + b, 0) };
  });
}

/** El total del periodo de lo que enseña la gráfica. */
export function chartTotal(daily: UsageDaily, lines: readonly UsageLine[]): number {
  return lines.reduce((sum, l) => sum + (daily.series[l] ?? []).reduce((a, b) => a + b, 0), 0);
}

/** «Construcción y pruebas»: qué parte del tope va gastada (0 a 1, o `null` sin tope). */
export function buildShare(spent: Money, cap: Money | null | undefined): number | null {
  if (!cap || cap.amount_micros <= 0) return null;
  return Math.min(1, Math.max(0, spent.amount_micros / cap.amount_micros));
}

/** Los días que le quedan a una bolsa, como se leen: «Unos 4 días». */
export function daysText(t: T, days: number | null): string {
  if (days == null) return t("money.days.unknown");
  const n = Math.max(0, Math.round(days));
  return n === 1 ? t("money.days.one") : t("money.days.many", { n });
}

// ── «Repartir tu saldo en bolsas» (55.3) ───────────────────────────────────

/** Hay un reparto por confirmar: topes de antes y aún sin bolsas. */
export function migrationPending(p: MigrationProposal | null | undefined): boolean {
  return Boolean(p && p.confirmed_at == null && p.clients.length > 0);
}

/** El total de la propuesta, por moneda (hoy la API la manda en USD). */
export function proposalTotals(p: MigrationProposal): Money[] {
  const by = new Map<Currency, number>();
  for (const c of p.clients) by.set(c.amount.currency, (by.get(c.amount.currency) ?? 0) + c.amount.amount_micros);
  return [...by.entries()].map(([cur, micros]) => money(micros, cur));
}

/**
 * Lo ajustado en el asistente: solo lo que cambió respecto a la propuesta va en
 * `adjust` (en cien milésimas de la moneda de la cuenta); lo que no se lee como
 * importe no se manda. `total` suma lo que quedará repartido.
 */
export function migrationAdjust(p: MigrationProposal, values: Record<string, string>): { adjust: Record<string, number>; invalid: string[]; total: number } {
  const adjust: Record<string, number> = {};
  const invalid: string[] = [];
  let total = 0;
  for (const c of p.clients) {
    const raw = values[c.ref];
    const parsed = raw === undefined ? ({ kind: "ok", micros: c.amount.amount_micros } as const) : parseAmount(raw);
    if (parsed.kind !== "ok") {
      invalid.push(c.ref);
      continue;
    }
    total += parsed.micros;
    // La propuesta se enseña con dos decimales (hacia abajo): solo cuenta como
    // ajuste lo que se aparta de lo que se ve.
    const shown = Math.floor(c.amount.amount_micros / MICROS_PER_CENT) * MICROS_PER_CENT;
    if (parsed.micros !== shown) adjust[c.ref] = parsed.micros;
    else total += c.amount.amount_micros - parsed.micros;
  }
  return { adjust, invalid, total };
}

// ── los errores ────────────────────────────────────────────────────────────

export type Failed = { ok: false; status: number; message: string; code?: string | null; info?: Record<string, unknown> };

/** Lo que falta según la API (409 `insufficient_account`): `{missing_micros, currency}`. */
export function missingOf(res: Failed): Money | null {
  if (res.code !== "insufficient_account" || !res.info) return null;
  const micros = Number(res.info.missing_micros);
  const cur = res.info.currency === "EUR" || res.info.currency === "USD" ? res.info.currency : null;
  return Number.isFinite(micros) && micros > 0 && cur ? money(micros, cur) : null;
}

/**
 * La frase de un error de dinero. La API nombra el caso y la pantalla escribe la
 * frase (principio III): nunca el mensaje crudo del backend. `currency` es la de
 * la bolsa, para decir hasta cuánto se puede devolver.
 */
export function moneyErrorText(t: T, res: Failed, currency?: Currency): string {
  switch (res.code) {
    case "insufficient_account": {
      const missing = missingOf(res);
      return missing ? t("money.receipt.missing", { amount: moneyText(missing) }) : t("money.error.insufficient");
    }
    case "bag_below_spent": {
      const micros = Number(res.info?.available_micros);
      return Number.isFinite(micros) && currency
        ? t("money.error.bag_below_spent", { amount: moneyText(money(micros, currency), "down") })
        : t("money.error.bag_below_spent.generic");
    }
    case "currency_mismatch":
      return t("money.error.currency_mismatch");
    case "bags_not_active":
      return t("money.error.bags_not_active");
    case "fx_unavailable":
      return t("money.error.fx_unavailable");
    case "invalid_amount":
      return t("money.amount.positive");
    case "request_already_sent_today":
      return t("money.request.already");
    case "can_assign":
      return t("money.request.canAssign");
    default:
      if (res.status === 401 || res.status === 403) return t("common.forbidden");
      if (res.status === 404) return t("money.error.notFound");
      return t("money.error.generic");
  }
}

/** Una clave para que un reintento no aparte dos veces (`Idempotency-Key`). */
export function newIdempotencyKey(prefix: string): string {
  const uuid = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${uuid}`;
}
