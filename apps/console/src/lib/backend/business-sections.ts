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

export type Basics = SectionMeta & {
  name: string;
  niche: string;
  info: string | null;
  website: string | null;
  country: string | null;
  timezone: string;
  price_currency: string | null;
  eu_only: boolean;
};
export type BasicsBody = Partial<Omit<Basics, keyof SectionMeta>>;

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
  };
}
