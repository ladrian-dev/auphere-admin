import type { Call } from "../backend";

/**
 * Spec 017 (R5): Capacidades — lo que el agente sabe hacer.
 *
 * Una sola lectura para herramientas y habilidades: el partner no distingue
 * unas de otras y no tiene por qué. La API contesta con el nombre de negocio
 * ya traducido al idioma que se le pide, porque quien sabe qué significa
 * `booking.create` es el backend, no la pantalla.
 */

export type CapabilityKind = "tool" | "skill";
/** «Requiere aprobación» se retira (R5.7): se comportaba como un bloqueo. */
export type CapabilityMode = "always" | "blocked";
export type CapabilityFunction =
  | "appointments"
  | "orders"
  | "messages"
  | "escalation"
  | "knowledge"
  | "other";

export type CapabilityConnector = { slug: string; display_name: string; status: string };

export type CapabilityModeInfo = {
  default: CapabilityMode;
  override: CapabilityMode | null;
  effective: CapabilityMode;
  options: CapabilityMode[];
};

export type Capability = {
  key: string;
  kind: CapabilityKind;
  business_name: string;
  description: string;
  function: CapabilityFunction;
  sectors: string[];
  recommended: boolean;
  /** Se está viendo pese a ser de otro sector (solo con «Ver todas»). */
  other_sector: boolean;
  enabled: boolean;
  enabled_in_active: boolean;
  /** Encendida **y** con lo que necesita para funcionar. Encenderla sin su
   *  integración es una decisión legítima: queda encendida y no utilizable. */
  usable: boolean;
  connector: CapabilityConnector | null;
  /** Las habilidades no tienen modo; no se inventa una columna vacía. */
  mode: CapabilityModeInfo | null;
  read_only: boolean;
  destructive: boolean;
  technical: { name: string; kind: CapabilityKind; version: string | null; tags: string[] };
};

export type CapabilityGroup = { function: CapabilityFunction; items: Capability[] };

export type CapabilitiesOut = {
  sector: string | null;
  has_draft: boolean;
  version: number | null;
  active_version: number | null;
  /** Cuántas se quedaron fuera por no ser de este sector. */
  hidden_by_sector: number;
  groups: CapabilityGroup[];
};

export type CapabilityUpdated = {
  capability: Capability;
  draft_created: boolean;
  version: number | null;
};

export type CapabilityUpdateBody = {
  key: string;
  kind: CapabilityKind;
  enabled?: boolean;
  mode?: CapabilityMode;
};

export function capabilitiesApi(call: Call) {
  const enc = encodeURIComponent;
  return {
    listCapabilities: (
      ref: string,
      opts: { q?: string; all?: boolean; lang?: string } = {},
    ): Promise<CapabilitiesOut> => {
      const qs = new URLSearchParams();
      if (opts.q) qs.set("q", opts.q);
      if (opts.all) qs.set("all", "true");
      if (opts.lang) qs.set("lang", opts.lang);
      const suffix = qs.size ? `?${qs}` : "";
      return call<CapabilitiesOut>(`/console/clients/${enc(ref)}/capabilities${suffix}`);
    },
    /** Un cambio por llamada (R5.4): el resto de la lista no se toca. */
    setCapability: (ref: string, body: CapabilityUpdateBody): Promise<CapabilityUpdated> =>
      call<CapabilityUpdated>(`/console/clients/${enc(ref)}/capabilities`, { method: "PUT", body }),
  };
}
