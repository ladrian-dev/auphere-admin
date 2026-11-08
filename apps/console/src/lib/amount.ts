import { AMOUNT_MAX_MINOR, type RuleCode } from "@/lib/business-rules";

/**
 * Un solo formato de dinero — spec 056 (requisito 13, D9). Los importes llegan
 * de la API en la unidad menor de su moneda (`amount_minor`, ISO 4217) y se
 * enseñan con **el idioma de la persona**, con Intl: «10,00 US$» en español,
 * «$10.00» en inglés. En español Intl no agrupa cuatro cifras («1500,00 €»): es
 * el formato del idioma, no un fallo. Los campos aceptan coma o punto y enseñan
 * el separador del idioma.
 *
 * `lib/money.ts` (el saldo del partner, céntimos de US$) delega aquí. Puro.
 */

export type AmountValue = { amount_minor: number; currency: string };
export type ParsedAmount = { kind: "empty" } | { kind: "ok"; minor: number } | { kind: "invalid"; code: Extract<RuleCode, "price_invalid" | "amount_too_large"> };

/**
 * ISO 4217, como la tiene la API (`services_catalog.exponent`). No la de Intl:
 * para COP o HUF dice 0 decimales mientras ISO, y la unidad menor guardada, tiene 2.
 */
const ZERO_DECIMALS = new Set(["BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"]);
const THREE_DECIMALS = new Set(["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"]);

/** Cuántos decimales tiene la unidad menor de la moneda (CLP 0, EUR 2, KWD 3). */
export function minorDigits(currency: string): number {
  const code = currency.toUpperCase();
  return ZERO_DECIMALS.has(code) ? 0 : THREE_DECIMALS.has(code) ? 3 : 2;
}

const numberText = (value: number, digits: number, locale: string, useGrouping: boolean) =>
  new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping }).format(value);

/** «10,00 US$» · «15.000 CLP» (es) · «$10.00» · «CLP 15,000» (en). Lo que no es un número, «—». */
export function formatAmount(money: AmountValue, locale: string): string {
  if (!Number.isFinite(money.amount_minor)) return "—";
  const digits = minorDigits(money.currency);
  const value = money.amount_minor / 10 ** digits;
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency: money.currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  } catch {
    // Una moneda que Intl no acepta: el número del idioma y su código, sin partirse.
    return `${numberText(value, digits, locale, true)} ${money.currency}`;
  }
}

/**
 * Las partes del mismo formato (para pintar los decimales y la moneda más
 * suaves, como «16,26 US$» en «Gasto del mes»). Unidas, dan {@link formatAmount}.
 */
export function amountParts(money: AmountValue, locale: string): Intl.NumberFormatPart[] {
  const digits = minorDigits(money.currency);
  const value = money.amount_minor / 10 ** digits;
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency: money.currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).formatToParts(value);
  } catch {
    return [{ type: "literal", value: formatAmount(money, locale) }];
  }
}

/** El importe para su campo: el separador decimal del idioma, sin miles ni moneda («1234,56»). */
export function amountInput(minor: number | null | undefined, currency: string, locale: string): string {
  if (minor == null || !Number.isFinite(minor)) return "";
  const digits = minorDigits(currency);
  return numberText(Math.max(0, minor) / 10 ** digits, digits, locale, false);
}

const INVALID: ParsedAmount = { kind: "invalid", code: "price_invalid" };
const TOO_LARGE: ParsedAmount = { kind: "invalid", code: "amount_too_large" };
/** Más cifras enteras que estas ya pasan del tope en cualquier moneda (y Number perdería precisión). */
const MAX_WHOLE_DIGITS = 15;

/** La parte entera: cifras solas o grupos de tres con un mismo separador («1.234.567», «1,234»). */
function wholeDigits(whole: string): string | null {
  if (/^\d+$/.test(whole)) return whole;
  if (/^\d{1,3}(\.\d{3})+$/.test(whole)) return whole.replaceAll(".", "");
  if (/^\d{1,3}(,\d{3})+$/.test(whole)) return whole.replaceAll(",", "");
  return null;
}

/**
 * Lo que escribe una persona → unidades menores (la lógica de
 * `business/sections/services-model.ts`, con los grupos comprobados):
 *
 * - coma o punto decimal: «15,50», «15.5»;
 * - con miles: «1.234,56» (es) y «1,234.56» (en); un punto solo con tres cifras
 *   detrás, o un separador repetido, es de miles («1.234», «1,234,567»);
 * - con una moneda sin decimales todo separador es de miles: «15.000» CLP;
 * - con tres decimales (KWD) el punto con tres cifras es decimal.
 *
 * Vacío no es cero. Sin signo. Más decimales de los de la moneda, o grupos mal
 * hechos, `price_invalid`; más de 10¹² unidades menores, `amount_too_large` (el
 * tope de `business-rules.ts` y de la API).
 */
export function parseAmount(text: string, currency: string): ParsedAmount {
  const raw = text.replace(/\s/g, "");
  if (!raw) return { kind: "empty" };
  if (!/^\d(?:[\d.,]*\d)?$/.test(raw)) return INVALID;
  const digits = minorDigits(currency);
  let whole = raw;
  let frac = "";
  const lastSep = Math.max(raw.lastIndexOf(","), raw.lastIndexOf("."));
  if (digits > 0 && lastSep >= 0) {
    const sep = raw.charAt(lastSep);
    const tail = raw.slice(lastSep + 1);
    const repeated = raw.indexOf(sep) !== lastSep;
    const both = raw.includes(",") && raw.includes(".");
    const decimal = !repeated && (both || sep === "," || tail.length !== 3 || digits === 3);
    if (decimal) {
      if (tail.length > digits) return INVALID;
      whole = raw.slice(0, lastSep);
      frac = tail;
    }
  }
  const w = wholeDigits(whole)?.replace(/^0+(?=\d)/, "");
  if (w === undefined) return INVALID;
  if (w.length > MAX_WHOLE_DIGITS) return TOO_LARGE;
  const minor = Number(w) * 10 ** digits + Number(frac.padEnd(digits, "0") || "0");
  return minor > AMOUNT_MAX_MINOR ? TOO_LARGE : { kind: "ok", minor };
}
