import type {
  DeducedSettings,
  DeductionSource,
  DetectedLink,
  LinkChoice,
  Network,
  NewClientBody,
  NicheGroup,
  NicheSuggestion,
  WalletCurrency,
} from "@/lib/backend/clients-v2";

/**
 * Spec 047 (T050) — lo que el modal «Nuevo cliente» / «Editar cliente» decide
 * sin pintar nada: límites, sugerencias de nicho, chips, «Más ajustes» y el
 * cuerpo que se manda. Puro, para probarlo sin navegador.
 */

export const NAME_MAX = 60;
export const NICHE_MIN = 2;
export const NICHE_MAX = 80;
export const INFO_MAX = 2000;

export type Settings = {
  country: string | null;
  timezone: string;
  price_currency: string | null;
  wallet_currency: WalletCurrency;
  eu_only: boolean;
};
export type SettingKey = keyof Settings;

export type ClientDraft = {
  name: string;
  niche: string;
  info: string;
  settings: Settings;
};

export const EMPTY_SETTINGS: Settings = {
  country: null,
  timezone: "UTC",
  price_currency: null,
  wallet_currency: "USD",
  eu_only: false,
};

/** Requisito 4.1: «Crear cliente» solo con nombre y nicho válidos. */
export function draftProblems(draft: Pick<ClientDraft, "name" | "niche" | "info">): {
  name: "missing" | "too_long" | null;
  niche: "missing" | "too_short" | "too_long" | null;
  info: "too_long" | null;
} {
  const name = draft.name.trim();
  const niche = draft.niche.trim();
  return {
    name: !name ? "missing" : name.length > NAME_MAX ? "too_long" : null,
    niche: !niche ? "missing" : niche.length < NICHE_MIN ? "too_short" : niche.length > NICHE_MAX ? "too_long" : null,
    info: draft.info.length > INFO_MAX ? "too_long" : null,
  };
}

export function canSubmit(draft: Pick<ClientDraft, "name" | "niche" | "info">): boolean {
  const p = draftProblems(draft);
  return p.name === null && p.niche === null && p.info === null;
}

const fold = (s: string) =>
  s
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLocaleLowerCase()
    .trim();

/**
 * Requisito 4.2: una sugerencia rellena el campo vacío o se añade a lo escrito,
 * y nunca lo sustituye. Si ya está, o no cabe, no cambia nada. La misma regla
 * que `merge_niche_suggestion` de la API.
 */
export function mergeNicheSuggestion(current: string, suggestion: string): string {
  const written = current.split(/\s+/).filter(Boolean).join(" ");
  if (!written) return suggestion.trim();
  if (fold(written).includes(fold(suggestion))) return current;
  const merged = `${written} · ${suggestion.trim()}`;
  return merged.length <= NICHE_MAX ? merged : current;
}

/** Los 6 grupos de plantillas más «Otro», en el orden en que se enseñan. */
export const NICHE_GROUPS: NicheGroup[] = ["beauty", "health", "aesthetics", "food", "retail", "services", "other"];

/** Cuántas sugerencias caben bajo el campo. */
export const MAX_SUGGESTIONS = 8;

/**
 * Las que se enseñan: sin texto, la primera de cada grupo y luego los más
 * usados; con texto, las que casan (ya filtradas por la API), por grupo.
 */
export function visibleSuggestions(items: NicheSuggestion[], typed: string): NicheSuggestion[] {
  const used = items.filter((i) => i.source === "used");
  const templates = items.filter((i) => i.source === "template");
  const byGroup = (a: NicheSuggestion, b: NicheSuggestion) =>
    NICHE_GROUPS.indexOf(a.group ?? "other") - NICHE_GROUPS.indexOf(b.group ?? "other");
  if (typed.trim()) return [...templates.sort(byGroup), ...used].slice(0, MAX_SUGGESTIONS);
  const firstOfEach = NICHE_GROUPS.map((g) => templates.find((t) => t.group === g)).filter(
    (t): t is NicheSuggestion => Boolean(t),
  );
  return [...firstOfEach, ...used].slice(0, MAX_SUGGESTIONS);
}

// ── chips ────────────────────────────────────────────────────────────────

/** Un chip como lo dejó la persona: quitado o con su red cambiada. */
export type ChipEdits = { removed: string[]; network: Record<string, Network> };
export const NO_EDITS: ChipEdits = { removed: [], network: {} };

export const chipKey = (link: Pick<DetectedLink, "network" | "value">) => `${link.network}:${link.value.toLocaleLowerCase()}`;

/** El enlace de un perfil a partir del usuario (como `social_url` de la API). */
export function socialUrl(network: Network, handle: string): string | null {
  const bare = handle.replace(/^@/, "");
  if (!/^[A-Za-z0-9._]{1,30}$/.test(bare)) return null;
  switch (network) {
    case "instagram":
      return `https://www.instagram.com/${bare}`;
    case "facebook":
      return `https://www.facebook.com/${bare}`;
    case "tiktok":
      return `https://www.tiktok.com/@${bare}`;
    case "youtube":
      return `https://www.youtube.com/@${bare}`;
    case "x":
      return `https://x.com/${bare}`;
    case "threads":
      return `https://www.threads.net/@${bare}`;
    default:
      return null;
  }
}

/** Un chip que se enseña: el detectado, con los cambios de la persona, y la
 *  clave del detectado (`origin`), que es con la que se guardan sus cambios. */
export type ShownChip = DetectedLink & { origin: string };

/** Los chips que se enseñan, con los cambios de la persona aplicados. */
export function shownChips(detected: DetectedLink[], edits: ChipEdits): ShownChip[] {
  return detected
    .filter((link) => !edits.removed.includes(chipKey(link)))
    .map((link) => {
      const origin = chipKey(link);
      const network = edits.network[origin];
      if (!network || network === link.network || !link.handle) return { ...link, origin };
      return { ...link, network, url: socialUrl(network, link.handle), guessed: true, origin };
    });
}

/**
 * Lo que va en `links` del alta. Sin cambios de la persona no se manda nada
 * y la API detecta lo mismo que enseñó el modal; con cambios, la lista exacta.
 */
export function linksToSend(detected: DetectedLink[], edits: ChipEdits): LinkChoice[] | null {
  const touched = edits.removed.length > 0 || Object.keys(edits.network).length > 0;
  if (!touched) return null;
  return shownChips(detected, edits).map((link): LinkChoice =>
    link.network === "web" ? { network: "web", url: link.url } : { network: link.network, url: link.url, handle: link.handle },
  );
}

// ── «Más ajustes» ───────────────────────────────────────────────────────────

/** Lo deducido entra en lo que la persona **no** ha tocado. */
export function applyDeduction(current: Settings, deduced: DeducedSettings, touched: ReadonlySet<SettingKey>): Settings {
  const next: Settings = { ...current };
  for (const key of ["country", "timezone", "price_currency", "wallet_currency", "eu_only"] as const) {
    if (!touched.has(key)) (next as Record<SettingKey, unknown>)[key] = deduced[key];
  }
  return next;
}

export function sourceKey(source: DeductionSource) {
  return `business.settings.source.${source}` as const;
}

/** Los países de la plataforma (los de la deducción de la API), por código. */
export const COUNTRIES = [
  "ES", "PT", "FR", "DE", "IT", "NL", "BE", "LU", "IE", "AT", "FI", "GR", "CY", "MT", "SK", "SI", "EE",
  "LV", "LT", "HR", "BG", "PL", "CZ", "HU", "RO", "SE", "DK", "NO", "IS", "LI", "GB", "CH", "AD",
  "US", "CA", "MX", "GT", "SV", "HN", "NI", "CR", "PA", "CU", "DO", "PR", "CO", "VE", "EC", "PE",
  "BO", "CL", "AR", "UY", "PY", "BR",
] as const;

/** Las monedas de los precios de esos países, ISO 4217. */
export const PRICE_CURRENCIES = [
  "EUR", "USD", "GBP", "CHF", "PLN", "CZK", "HUF", "RON", "SEK", "DKK", "NOK", "ISK", "CAD", "MXN",
  "GTQ", "HNL", "NIO", "CRC", "CUP", "DOP", "COP", "PEN", "BOB", "CLP", "ARS", "UYU", "PYG", "BRL",
] as const;

/** Con «Solo UE» encendido por defecto (UE y EEE). */
const EU_EEA = new Set([
  "ES", "PT", "FR", "DE", "IT", "NL", "BE", "LU", "IE", "AT", "FI", "GR", "CY", "MT", "SK", "SI", "EE",
  "LV", "LT", "HR", "BG", "PL", "CZ", "HU", "RO", "SE", "DK", "NO", "IS", "LI",
]);
export const isEuEea = (country: string | null) => (country ? EU_EEA.has(country) : false);

/** Las zonas IANA que ofrece el navegador; si no las sabe, las que ya hay. */
export function timezoneOptions(...keep: (string | null | undefined)[]): string[] {
  const own = keep.filter((z): z is string => Boolean(z));
  let all: string[] = [];
  try {
    const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
    all = intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
  } catch {
    all = [];
  }
  return Array.from(new Set(["UTC", ...own, ...all])).sort((a, b) => (a === "UTC" ? -1 : b === "UTC" ? 1 : a.localeCompare(b)));
}

export function displayName(locale: string, type: "region" | "currency", code: string): string {
  try {
    return new Intl.DisplayNames([locale], { type }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** Lo que el navegador sabe: la última fuente de la deducción (requisito 4.5). */
export function browserHints(): { browser_timezone: string | null; browser_locale: string | null } {
  try {
    return {
      browser_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone ?? null,
      browser_locale: typeof navigator !== "undefined" ? navigator.language ?? null : null,
    };
  } catch {
    return { browser_timezone: null, browser_locale: null };
  }
}

/** El cuerpo de `POST /console/clients`: lo escrito, «Más ajustes» y los chips. */
export function newClientBody(draft: ClientDraft, detected: DetectedLink[], edits: ChipEdits): NewClientBody {
  const info = draft.info.trim();
  return {
    name: draft.name.trim(),
    niche: draft.niche.trim(),
    info: info || null,
    country: draft.settings.country,
    timezone: draft.settings.timezone,
    price_currency: draft.settings.price_currency,
    wallet_currency: draft.settings.wallet_currency,
    eu_only: draft.settings.eu_only,
    links: linksToSend(detected, edits),
  };
}

/** Una clave por alta: dos clics en «Crear cliente» son el mismo cliente. */
export function newIdempotencyKey(): string {
  try {
    return `alta-${crypto.randomUUID()}`;
  } catch {
    return `alta-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}
