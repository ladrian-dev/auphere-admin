/**
 * Spec 047 (T117, 31.5, 31.6, 54.7): the words and the rules of the «WhatsApp
 * login» beta by country. Pure, so it is tested on its own; the API checks it
 * all again (and the database too: the CHECK of migration 0191).
 */

/**
 * The EU and the EEA (research D12): Meta's beta does not hold there. The same
 * list as `EU_EEA` in `api/admin/whatsapp_login_beta.py` and the CHECK of
 * migration 0191 — change the three together.
 */
export const EU_EEA: ReadonlySet<string> = new Set([
  "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
  "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS",
  "LI", "NO",
  // EU territories with their own ISO code: outermost regions, Saint Martin, Åland.
  "GF", "GP", "MQ", "RE", "YT", "MF", "AX",
]);

/** ISO 3166-1 alpha-2: every country the form can offer. */
const ISO2 = (
  "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW " +
  "BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI " +
  "FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN " +
  "IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME " +
  "MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF " +
  "PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV " +
  "SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE " +
  "YT ZA ZM ZW"
).split(" ");

export const REASON_MIN = 3;
export const REASON_MAX = 300;

/** Why the EU and the EEA cannot be picked, in one line. */
export const EU_WHY =
  "La beta de Meta no vale para números de la UE ni del EEE: allí el enlace del dueño sigue pidiendo la cuenta de Meta y nunca promete «sin Facebook».";

const NAMES = new Intl.DisplayNames(["es"], { type: "region" });

/**
 * Los nombres de todos los países, para calcularlos **en el servidor** y pasarlos
 * a la vista: el ICU de Node y el del navegador no los dicen igual («RAE de Hong
 * Kong (China)» frente a «Hong Kong») y la página no hidrataba.
 */
export type CountryNames = Readonly<Record<string, string>>;

export function countryNames(): CountryNames {
  return Object.fromEntries(ISO2.map((code) => [code, countryName(code)]));
}

export function countryName(iso2: string, names?: CountryNames): string {
  const known = names?.[iso2];
  if (known) return known;
  try {
    return NAMES.of(iso2) ?? iso2;
  } catch {
    return iso2;
  }
}

export function isEuEea(iso2: string): boolean {
  return EU_EEA.has(iso2.toUpperCase());
}

export type CountryOption = { code: string; name: string };

/**
 * What the form offers: the countries where the beta can be turned on (not
 * those already on) and, apart, the EU and the EEA, which are shown but
 * cannot be picked. Both by their Spanish name.
 */
export function countryOptions(enabled: readonly string[], names?: CountryNames): { available: CountryOption[]; blocked: CountryOption[] } {
  const on = new Set(enabled.map((c) => c.toUpperCase()));
  const byName = (a: CountryOption, b: CountryOption) => a.name.localeCompare(b.name, "es");
  const all = ISO2.map((code) => ({ code, name: countryName(code, names) }));
  return {
    available: all.filter((c) => !EU_EEA.has(c.code) && !on.has(c.code)).sort(byName),
    blocked: all.filter((c) => EU_EEA.has(c.code)).sort(byName),
  };
}

/** The reason goes to the audit: between 3 and 300 characters, like the API. */
export function reasonError(reason: string): string | null {
  const length = reason.trim().length;
  if (length === 0) return "Hace falta el motivo.";
  if (length < REASON_MIN) return `El motivo necesita al menos ${REASON_MIN} caracteres.`;
  if (length > REASON_MAX) return `El motivo admite como mucho ${REASON_MAX} caracteres.`;
  return null;
}

/** Who turned it on: the API stores `operator:{email}` (older rows, `operator:{id}`). */
export function enabledByLabel(
  enabledBy: string,
  operatorId: string,
  operatorEmail?: string,
): string {
  const who = enabledBy.startsWith("operator:") ? enabledBy.slice("operator:".length) : enabledBy;
  if (who === operatorId || (operatorEmail && who === operatorEmail)) return "Tú";
  if (who.includes("@")) return who;
  return enabledBy.startsWith("operator:") ? `Operador ${who.slice(0, 8)}` : enabledBy;
}

export const ERRORS: Record<string, string> = {
  eu_country_not_allowed: EU_WHY,
  invalid_country: "Ese código no es un país (dos letras, ISO 3166-1).",
};
