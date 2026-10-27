import type { Call, Job, JobAccepted } from "../backend";

/**
 * Lane module `business` — el alta en tres datos y la lectura de la web
 * (spec 047, T048–T050; `contracts/console-api.md` §2 y §3).
 *
 * - `POST /console/clients/link-detection`: los chips de «Irá a la ficha» y
 *   «Más ajustes» relleno, mientras se escribe;
 * - `GET /console/clients/niche-suggestions?q=`: las plantillas (como clave;
 *   el texto es de la consola) y los nichos más usados del partner;
 * - `POST /console/clients` con `{name, niche, info?, …}`: nunca crea un agente;
 * - `GET|POST /console/clients/{ref}/business/read`: la tarjeta de lectura.
 */

export type Network = "web" | "instagram" | "facebook" | "tiktok" | "linkedin" | "youtube" | "x" | "threads";
export type NicheGroup = "beauty" | "health" | "aesthetics" | "food" | "retail" | "services" | "other";
export type WalletCurrency = "EUR" | "USD";
export type DeductionSource = "web" | "phone" | "partner" | "browser" | "default";

export type DetectedLink = {
  kind: "web" | "social";
  network: Network;
  value: string;
  url: string | null;
  handle: string | null;
  target: "website" | "links";
  guessed: boolean;
  alternatives: Network[];
};

export type DeducedSettings = {
  country: string | null;
  timezone: string;
  price_currency: string | null;
  wallet_currency: WalletCurrency;
  eu_only: boolean;
  source: DeductionSource;
};

export type LinkDetection = { links: DetectedLink[]; deduced: DeducedSettings };

export type NicheSuggestion = {
  source: "template" | "used";
  key: string | null;
  group: NicheGroup | null;
  value: string | null;
  uses: number;
};

export type LinkChoice = { network: Network; url?: string | null; handle?: string | null };

export type NewClientBody = {
  name: string;
  niche: string;
  info?: string | null;
  country?: string | null;
  timezone?: string | null;
  price_currency?: string | null;
  wallet_currency?: WalletCurrency | null;
  eu_only?: boolean | null;
  links?: LinkChoice[] | null;
};

export type NewClientCreated = {
  ref: string;
  name: string;
  status: "active";
  duplicate_name: boolean;
  read_job_id: string | null;
};

/** Por qué falla una lectura (vocabulario cerrado del lector). */
export type ReadFailure = "unreachable" | "blocked" | "no_text" | "too_large" | "extract_failed" | "nothing_to_read" | "timeout" | "internal" | "interrupted";

export type ReadSource = {
  network: Network;
  value: string | null;
  status: "read" | "failed";
  failure: ReadFailure | null;
  pages: number;
};

/** El `result` de un trabajo `client_read` terminado. */
export type ReadResult = {
  website: string | null;
  sources: ReadSource[];
  found: { locations: number; hours: number; services: number; policies: number; faqs: number; links: number };
  applied: number;
  suggested: number;
  translated_from: string | null;
};

export type ClientRead = { job: Job | null; website: string | null; networks: Network[] };

export function clientsV2Api(call: Call) {
  const enc = encodeURIComponent;
  return {
    detectClientLinks: (body: { info: string; browser_timezone?: string | null; browser_locale?: string | null }) =>
      call<LinkDetection>("/console/clients/link-detection", { method: "POST", body }),
    nicheSuggestions: (q: string) =>
      call<{ items: NicheSuggestion[] }>(`/console/clients/niche-suggestions${q ? `?${new URLSearchParams({ q }).toString()}` : ""}`),
    createClientV2: (body: NewClientBody, idempotencyKey?: string) =>
      call<NewClientCreated>("/console/clients", {
        method: "POST",
        body,
        ...(idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : {}),
      }),
    getClientRead: (ref: string) => call<ClientRead>(`/console/clients/${enc(ref)}/business/read`),
    startClientRead: (ref: string) => call<JobAccepted>(`/console/clients/${enc(ref)}/business/read`, { method: "POST" }),
  };
}
