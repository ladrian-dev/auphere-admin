import type { Call } from "../backend";

/**
 * Spec 047 (T057, T058, T060) — las secciones de Negocio que escribe la persona:
 * datos básicos, sedes, horario, fechas especiales y servicios
 * (`contracts/console-api.md` §3, `/console/clients/{ref}/business/*`).
 *
 * Cada sección trae su `revision` y las escrituras mandan `If-Match` con ella:
 * si otra persona guardó antes, la API responde 412 y no pisa nada. Los precios
 * van en unidades menores de la moneda del negocio (`exponent` dice sus
 * decimales: CLP, 0; EUR, 2).
 */

export type SectionState = "complete" | "read_pending" | "pending" | "optional";
export type SectionAction = "edit";
export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export const DAYS: readonly Day[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export type Layout = "blocks" | "daily";

type SectionMeta = { revision: number; state: SectionState; allowed: SectionAction[] };

export type ShiftOut = { open: string; close: string; overnight: boolean };
export type ShiftIn = { open: string; close: string };

/**
 * El sector del negocio (requisito 57; `contracts/console-api.md` §10): la clave
 * de una guía de Auphere u `otro`, su etiqueta legible, la confianza, de dónde
 * salió y quién lo decidió. `has_guide` dice si sus agentes siguen una guía de
 * Auphere o una generada para este cliente (58.4).
 */
export type SectorSource = "niche" | "info" | "web" | "person" | "fallback";
export type Sector = {
  key: string;
  label: string;
  confidence: number;
  source: SectorSource;
  decided_by: "system" | "person";
  has_guide: boolean;
};
/** Un sector con guía de Auphere, para el selector (`GET /console/sectors`). */
export type SectorOption = { key: string; label: string };
/** `key = "otro"` exige `label` (1–40). */
export type SectorBody = { key: string; label: string };

export type Basics = SectionMeta & {
  name: string;
  niche: string;
  info: string | null;
  website: string | null;
  country: string | null;
  timezone: string;
  price_currency: string | null;
  eu_only: boolean;
  /**
   * `null` mientras se identifica; sin el campo (una API de antes de la fase 27),
   * la consola no habla del sector.
   */
  sector?: Sector | null;
};
export type BasicsBody = Partial<Omit<Basics, keyof SectionMeta | "sector">> & { sector?: SectorBody };

/** Las cuatro políticas del negocio (requisito 8.1), tal cual entran en el prompt. */
export const POLICY_KEYS = ["cancellation", "payments", "deposit", "no_show"] as const;
export type PolicyKey = (typeof POLICY_KEYS)[number];
export type Policies = SectionMeta & Record<PolicyKey, string | null>;
/** `PUT /policies` sustituye las cuatro: lo que no se manda queda vacío. */
export type PoliciesBody = Record<PolicyKey, string | null>;

/** Una pregunta frecuente; `suggested` es «Sugerido · confirma» y no entra en el prompt. */
export type Faq = { id: string; q: string; a: string; suggested: boolean };
export type Faqs = SectionMeta & { items: Faq[]; created_id: string | null };
export type FaqBody = { q: string; a: string };
export type FaqPatch = { q?: string; a?: string; suggested?: boolean };

export type Hours = SectionMeta & {
  location_id: string | null;
  inherits: boolean;
  layout: Layout | null;
  days: Record<Day, ShiftOut[]>;
  /** «Así lo dirá el agente»; `null` sin horario. */
  label: string | null;
};
export type HoursBody =
  | { layout: Layout; days: Partial<Record<Day, ShiftIn[]>>; confirm_loss?: boolean }
  | { inherit: true }
  | { clear: true };

export type Location = {
  id: string;
  name: string;
  address: string | null;
  phone_e164: string | null;
  own_hours: boolean;
  label: string | null;
  archived: boolean;
};
export type Locations = SectionMeta & { items: Location[]; created_id: string | null };
export type LocationBody = { name?: string; address?: string | null; phone_e164?: string | null };

export type SpecialDate = {
  id: string;
  name: string;
  location_id: string | null;
  from: string;
  to: string;
  closed: boolean;
  shifts: ShiftOut[];
  archived: boolean;
};
export type SpecialDates = SectionMeta & { items: SpecialDate[]; created_id: string | null };
export type SpecialDateBody = {
  name?: string | null;
  location_id?: string | null;
  from: string;
  to: string;
  closed: boolean;
  shifts?: ShiftIn[];
};

export type PriceKind = "none" | "free" | "amount";
export type Price = { kind: PriceKind; amount_minor?: number };
export type AgentRef = { id: string; name: string };
export type AgentOption = AgentRef & { serves_all: boolean };
export type Service = {
  id: string;
  name: string;
  description: string | null;
  bookable: boolean;
  duration_min: number | null;
  price: Price;
  currency: string;
  staff: "all" | string[];
  agents: { mode: "all_agents" | "list"; agent_ids: string[] };
  used_by: AgentRef[];
  archived: boolean;
};
export type Services = SectionMeta & {
  currency: string;
  exponent: number;
  items: Service[];
  agents: AgentOption[];
  created_id: string | null;
};
export type ServiceBody = {
  name?: string;
  description?: string | null;
  bookable?: boolean;
  duration_min?: number | null;
  price?: Price;
};

export function businessSectionsApi(call: Call) {
  const enc = encodeURIComponent;
  const biz = (ref: string) => `/console/clients/${enc(ref)}/business`;
  const ifMatch = (revision: number) => ({ "If-Match": `"${revision}"` });
  const loc = (id: string | null | undefined) => (id ? `?location_id=${enc(id)}` : "");
  return {
    getBasics: (ref: string) => call<Basics>(`${biz(ref)}/basics`),
    putBasics: (ref: string, body: BasicsBody, revision: number) =>
      call<Basics>(`${biz(ref)}/basics`, { method: "PUT", body, headers: ifMatch(revision) }),
    getHours: (ref: string, locationId?: string | null) => call<Hours>(`${biz(ref)}/hours${loc(locationId)}`),
    putHours: (ref: string, body: HoursBody, revision: number, locationId?: string | null) =>
      call<Hours>(`${biz(ref)}/hours${loc(locationId)}`, { method: "PUT", body, headers: ifMatch(revision) }),
    getLocations: (ref: string) => call<Locations>(`${biz(ref)}/locations?archived=true`),
    createLocation: (ref: string, body: LocationBody, revision: number) =>
      call<Locations>(`${biz(ref)}/locations`, { method: "POST", body, headers: ifMatch(revision) }),
    updateLocation: (ref: string, id: string, body: LocationBody, revision: number) =>
      call<Locations>(`${biz(ref)}/locations/${enc(id)}`, { method: "PATCH", body, headers: ifMatch(revision) }),
    archiveLocation: (ref: string, id: string, revision: number, restore: boolean) =>
      call<Locations>(`${biz(ref)}/locations/${enc(id)}/${restore ? "restore" : "archive"}`, {
        method: "POST",
        headers: ifMatch(revision),
      }),
    getSpecialDates: (ref: string) => call<SpecialDates>(`${biz(ref)}/special-dates`),
    createSpecialDate: (ref: string, body: SpecialDateBody, revision: number) =>
      call<SpecialDates>(`${biz(ref)}/special-dates`, { method: "POST", body, headers: ifMatch(revision) }),
    archiveSpecialDate: (ref: string, id: string, revision: number) =>
      call<SpecialDates>(`${biz(ref)}/special-dates/${enc(id)}/archive`, { method: "POST", headers: ifMatch(revision) }),
    getServices: (ref: string) => call<Services>(`${biz(ref)}/services`),
    createService: (ref: string, body: ServiceBody, revision: number) =>
      call<Services>(`${biz(ref)}/services`, { method: "POST", body, headers: ifMatch(revision) }),
    updateService: (ref: string, id: string, body: ServiceBody, revision: number) =>
      call<Services>(`${biz(ref)}/services/${enc(id)}`, { method: "PATCH", body, headers: ifMatch(revision) }),
    archiveService: (ref: string, id: string, revision: number) =>
      call<Services>(`${biz(ref)}/services/${enc(id)}/archive`, { method: "POST", headers: ifMatch(revision) }),
    duplicateService: (ref: string, id: string, revision: number) =>
      call<Services>(`${biz(ref)}/services/${enc(id)}/duplicate`, { method: "POST", headers: ifMatch(revision) }),
    setServiceAgents: (ref: string, id: string, body: { mode: "all_agents" | "list"; agent_ids: string[] }, revision: number) =>
      call<Services>(`${biz(ref)}/services/${enc(id)}/agents`, { method: "PUT", body, headers: ifMatch(revision) }),
    // Spec 047, fase 27 (T209; requisitos 57.5 y 60.4).
    getPolicies: (ref: string) => call<Policies>(`${biz(ref)}/policies`),
    putPolicies: (ref: string, body: PoliciesBody, revision: number) =>
      call<Policies>(`${biz(ref)}/policies`, { method: "PUT", body, headers: ifMatch(revision) }),
    getFaqs: (ref: string) => call<Faqs>(`${biz(ref)}/faqs`),
    createFaq: (ref: string, body: FaqBody, revision: number) =>
      call<Faqs>(`${biz(ref)}/faqs`, { method: "POST", body, headers: ifMatch(revision) }),
    updateFaq: (ref: string, id: string, body: FaqPatch, revision: number) =>
      call<Faqs>(`${biz(ref)}/faqs/${enc(id)}`, { method: "PATCH", body, headers: ifMatch(revision) }),
    archiveFaq: (ref: string, id: string, revision: number) =>
      call<Faqs>(`${biz(ref)}/faqs/${enc(id)}/archive`, { method: "POST", headers: ifMatch(revision) }),
    /** Los sectores con guía de Auphere (el selector de Datos básicos). */
    listSectors: async () => (await call<{ sectors: SectorOption[] }>("/console/sectors")).sectors,
  };
}
