import type { Price } from "@/lib/backend/business-sections";

/**
 * El modelo de Servicios — spec 047 (T060, requisitos 11.1 y 11.7). Puro.
 *
 * Los precios van en unidades menores de la moneda del negocio (`exponent` son
 * sus decimales, ISO 4217): los pesos chilenos sin decimales, los euros con dos.
 * Se escriben y se leen con el separador del idioma de la persona.
 */

/** Duración de un servicio reservable: de 5 a 480 min, en pasos de 5. */
export const DURATIONS: readonly number[] = Array.from({ length: 96 }, (_, i) => (i + 1) * 5);

const numberFormat = (locale: string, exponent: number) =>
  new Intl.NumberFormat(locale === "en" ? "en-US" : "es-ES", {
    minimumFractionDigits: exponent,
    maximumFractionDigits: exponent,
    useGrouping: true,
  });

/** «15.000 CLP» · «15,50 EUR». */
export function formatAmount(amountMinor: number, currency: string, exponent: number, locale: string): string {
  const value = amountMinor / 10 ** exponent;
  // es-ES leaves four-digit amounts ungrouped; group them like the rest.
  const text = numberFormat(locale, exponent)
    .formatToParts(value)
    .map((p) => p.value)
    .join("");
  const grouped = locale === "en" ? text : withGroups(text);
  return `${grouped} ${currency}`;
}

function withGroups(text: string): string {
  const [whole, frac] = text.split(",");
  const digits = (whole ?? "").replace(/\./g, "");
  const out = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return frac !== undefined ? `${out},${frac}` : out;
}

/** El importe para el campo de texto, sin la moneda. */
export function amountText(amountMinor: number, exponent: number, locale: string): string {
  return formatAmount(amountMinor, "", exponent, locale).trim();
}

/**
 * Lo que escribe una persona → unidades menores. Acepta «15,50», «15.5» y
 * «1.234,56»; con una moneda sin decimales, «15.000» son quince mil. `null` si no
 * es un importe (o lleva más decimales de los de la moneda).
 */
export function parseAmount(text: string, exponent: number): number | null {
  const raw = text.trim().replace(/\s/g, "");
  if (!raw || !/^\d[\d.,]*$/.test(raw)) return null;
  let whole = raw;
  let frac = "";
  const lastSep = Math.max(raw.lastIndexOf(","), raw.lastIndexOf("."));
  if (exponent > 0 && lastSep >= 0) {
    const sep = raw[lastSep];
    const tail = raw.slice(lastSep + 1);
    const both = raw.includes(",") && raw.includes(".");
    // «15,50» y «1.234,56» (es), «15.5» y «1,234.56» (en); «1.234» solo, miles.
    const decimal = sep === "," || both || tail.length !== 3;
    if (decimal) {
      if (tail.length > exponent) return null;
      whole = raw.slice(0, lastSep);
      frac = tail;
    }
  }
  const digits = whole.replace(/[.,]/g, "");
  if (!/^\d+$/.test(digits)) return null;
  return Number(digits) * 10 ** exponent + Number(frac.padEnd(exponent, "0") || 0);
}

export type PriceChoice = Price["kind"];
