import { minorDigits } from "@/lib/amount";

/**
 * Prices of Servicios (spec 043): the API sends the ISO 4217 minor unit
 * (`amount_minor`) with its currency; CLP has no decimals. Since spec 056
 * (requisito 13) Reservas formats, reads and writes them with `lib/amount.ts`,
 * the one money format of the console, in the person's language. What stays
 * here is the table's old name, for the callers that still import it.
 */

export type Locale = "es" | "en";

/** How many decimals the currency's minor unit has (CLP 0, EUR 2): ISO 4217, as the API has it. */
export { minorDigits };
