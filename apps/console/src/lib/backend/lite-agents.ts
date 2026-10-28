import type { Call } from "../backend";
import type {
  Hours,
  HoursBody,
  LocationBody,
  Locations,
  Price,
  ServiceBody,
  Services,
  SpecialDateBody,
  SpecialDates,
} from "./business-sections";

/**
 * Spec 047 (T168; requisitos 50.1 a 50.4; `contracts/lite-app-api.md` §1 y §2)
 * — «Agentes» y «Negocio» de la persona del cliente, todo bajo
 * `/console/lite/*`. Ninguna llamada lleva la referencia del cliente: la API lo
 * saca de la persona verificada.
 *
 * Los agentes llegan con el mismo `visible_state` que la consola del partner
 * (los mismos códigos y tonos, 25.5). Negocio son las mismas vistas que la ficha
 * del partner (horario, fechas especiales, servicios y sedes), cada una con su
 * `revision`: cada escritura manda `If-Match` (412 con lo que cambió) e
 * `Idempotency-Key`. Crear, archivar o publicar agentes, instrucciones,
 * calidad, canales nuevos y la bolsa no tienen ruta (50.3).
 */

/** El estado visible, calculado por la API: la consola solo pone las palabras. */
export type LiteVisibleState = { code: string; tone: string; reason: string | null };
export type LiteAgentAction = "pause" | "resume";

export type LiteAgentChannel = {
  id: string;
  type: string;
  /** El número del negocio (nunca el de un cliente final). */
  identifier: string;
  visible_state: LiteVisibleState;
  allowed: LiteAgentAction[];
};

export type LiteAgent = {
  id: string;
  name: string;
  is_default: boolean;
  visible_state: LiteVisibleState;
  pause_reason: string | null;
  /** `client_user`, `partner_user`, `system`… quién lo pausó. */
  paused_by_kind: string | null;
  /** `lite_web`, `app`, `console`… desde dónde. */
  paused_origin: string | null;
  /** El nombre de la persona del cliente que lo pausó (27.6); `null` si no fue una. */
  paused_by_name?: string | null;
  open_conversations: number;
  channels: LiteAgentChannel[];
  /** Solo lo que esta persona puede hacer (§V): la pausa del sistema no la quita nadie. */
  allowed: LiteAgentAction[];
};

export type LiteAgents = { items: LiteAgent[] };

export type LitePerson = { kind: string; name: string | null };

/** Un cambio de sus cuatro secciones (o una corrección desde la Bandeja), con «Deshacer». */
export type LiteChange = {
  id: string;
  section: string;
  kind: string;
  at: string;
  by: LitePerson | null;
  origin: string;
  undone_at: string | null;
  undoable: boolean;
};

export type LiteProvenance = { source: string; by: LitePerson | null; origin: string | null; at: string | null; review: string | null };

/** `GET /console/lite/business`: lo que el negocio edita, con su historial. */
export type LiteBusiness = {
  hours: Hours;
  special_dates: SpecialDates;
  services: Services;
  locations: Locations;
  provenance: Record<string, LiteProvenance>;
  history: LiteChange[];
};

export type LiteUndo = { section: string; revision: number | null; change_id: string | null };

/** Un servicio nuevo: el nombre, y lo demás como en la ficha. Quién lo hace es del partner. */
export type LiteServiceNew = { name: string; description?: string | null; bookable?: boolean; duration_min?: number | null; price?: Price };
/** Lo que cambia la lite de un servicio: precio, duración, descripción y si es reservable (no el nombre). */
export type LiteServicePatch = Omit<ServiceBody, "name">;

export function liteAgentsApi(call: Call) {
  const enc = encodeURIComponent;
  const B = "/console/lite/business";
  const write = (revision: number, key?: string) => ({ "If-Match": `"${revision}"`, ...(key ? { "Idempotency-Key": key } : {}) });
  return {
    liteAgents: () => call<LiteAgents>("/console/lite/agents"),
    litePauseAgent: (id: string, confirm: boolean) =>
      call<LiteAgent>(`/console/lite/agents/${enc(id)}/pause`, { method: "POST", body: { confirm } }),
    liteResumeAgent: (id: string) => call<LiteAgent>(`/console/lite/agents/${enc(id)}/resume`, { method: "POST" }),
    litePauseChannel: (id: string) => call<LiteAgentChannel>(`/console/lite/channels/${enc(id)}/pause`, { method: "POST" }),
    liteResumeChannel: (id: string) => call<LiteAgentChannel>(`/console/lite/channels/${enc(id)}/resume`, { method: "POST" }),

    liteBusiness: () => call<LiteBusiness>(B),
    /** El horario de una sede (el suyo o el que hereda) o, sin sede, el del negocio. */
    liteHours: (locationId: string | null) =>
      call<Hours>(`${B}/hours${locationId ? `?location_id=${enc(locationId)}` : ""}`),
    litePutHours: (body: HoursBody, revision: number, key?: string, locationId?: string | null) =>
      call<Hours>(`${B}/hours${locationId ? `?location_id=${enc(locationId)}` : ""}`, { method: "PUT", body, headers: write(revision, key) }),
    liteCreateSpecialDate: (body: SpecialDateBody, revision: number, key?: string) =>
      call<SpecialDates>(`${B}/special-dates`, { method: "POST", body, headers: write(revision, key) }),
    liteArchiveSpecialDate: (id: string, revision: number, key?: string) =>
      call<SpecialDates>(`${B}/special-dates/${enc(id)}/archive`, { method: "POST", headers: write(revision, key) }),
    liteCreateService: (body: LiteServiceNew, revision: number, key?: string) =>
      call<Services>(`${B}/services`, { method: "POST", body, headers: write(revision, key) }),
    liteUpdateService: (id: string, body: LiteServicePatch, revision: number, key?: string) =>
      call<Services>(`${B}/services/${enc(id)}`, { method: "PATCH", body, headers: write(revision, key) }),
    liteArchiveService: (id: string, revision: number, key?: string) =>
      call<Services>(`${B}/services/${enc(id)}/archive`, { method: "POST", headers: write(revision, key) }),
    liteCreateLocation: (body: LocationBody, revision: number, key?: string) =>
      call<Locations>(`${B}/locations`, { method: "POST", body, headers: write(revision, key) }),
    liteUpdateLocation: (id: string, body: LocationBody, revision: number, key?: string) =>
      call<Locations>(`${B}/locations/${enc(id)}`, { method: "PATCH", body, headers: write(revision, key) }),
    liteArchiveLocation: (id: string, revision: number, restore: boolean, key?: string) =>
      call<Locations>(`${B}/locations/${enc(id)}/${restore ? "restore" : "archive"}`, { method: "POST", headers: write(revision, key) }),
    liteUndoChange: (changeId: string, key?: string) =>
      call<LiteUndo>(`${B}/history/${enc(changeId)}/undo`, { method: "POST", ...(key ? { headers: { "Idempotency-Key": key } } : {}) }),
  };
}
