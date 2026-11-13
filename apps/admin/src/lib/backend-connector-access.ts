/**
 * Spec 060: qué partners pueden usar cada conector
 * (`apps/api/src/nexus_api/api/admin/connector_access.py`). Mismo `call` y mismo
 * token que el resto del panel; las escrituras nombran a la persona
 * (`X-Operator-Id`) y llevan su motivo, que van a la auditoría. Solo servidor.
 */

import "server-only";

import { call } from "@/lib/backend";

export type PartnerConnectorState = "enabled" | "disabled" | "default";

export type PartnerConnector = {
  slug: string;
  display_name: string;
  category: string;
  auth_kind: string;
  /** El valor por defecto del conector para los partners. */
  default_enabled: boolean;
  /** `default`: sin decisión propia, hereda el valor por defecto. */
  partner_state: PartnerConnectorState;
  /** Si los clientes del partner lo pueden usar. */
  effective: boolean;
  connected_clients: number;
  set_by: string | null;
  set_at: string | null;
  reason: string | null;
};

export type PartnerConnectors = {
  partner: { id: string; name: string };
  items: PartnerConnector[];
};

export type PartnerDecision = {
  partner_id: string;
  name: string;
  state: "enabled" | "disabled";
  effective: boolean;
  connected_clients: number;
  set_by: string;
  set_at: string;
  reason: string;
};

export type ConnectorAccess = {
  slug: string;
  default_enabled: boolean;
  default_reason: string | null;
  default_updated_by: string | null;
  default_updated_at: string | null;
  partners: PartnerDecision[];
  partners_without_decision: number;
  clients_without_partner_connected: number;
};

/** `409 confirm_required`: a quién afecta, antes de guardar (requisito 4.1). */
export type AccessImpact = {
  affected: {
    partner_id: string | null;
    partner_name: string | null;
    clients: { tenant_id: string; name: string; connection_status: string; agents: number }[];
  }[];
  totals: { clients: number; agents: number };
};

export const connectorAccessBackend = {
  forPartner: (partnerId: string) =>
    call<PartnerConnectors>(`/admin/partners/${encodeURIComponent(partnerId)}/connectors`),
  forConnector: (slug: string) =>
    call<ConnectorAccess>(`/admin/connectors/${encodeURIComponent(slug)}/access`, { optional: true }),
  setPartnerState: (
    slug: string,
    partnerId: string,
    body: { state: PartnerConnectorState; reason: string; confirm: boolean },
    operatorId: string,
  ) =>
    call<PartnerConnector>(
      `/admin/connectors/${encodeURIComponent(slug)}/partners/${encodeURIComponent(partnerId)}`,
      { method: "PUT", body, headers: { "X-Operator-Id": operatorId } },
    ),
  setDefault: (
    slug: string,
    body: { enabled: boolean; reason: string; confirm: boolean },
    operatorId: string,
  ) =>
    call<ConnectorAccess>(`/admin/connectors/${encodeURIComponent(slug)}/access/default`, {
      method: "PUT",
      body,
      headers: { "X-Operator-Id": operatorId },
    }),
};
