import type { Call } from "../backend";
import { q } from "../backend";

import type { ConnectorTools } from "./agent-connectors-types";
import type { AgendaBody, AgentAgenda } from "./agenda-types";

/**
 * Carril de la agenda de un agente (spec 057, requisitos 2, 4.4 y 5.3;
 * `contracts/console-api.md` §3–§5): leerla, activarla o desactivarla en el
 * borrador (encendiendo Reservas para el cliente si hace falta) y lo que puede
 * hacer, con la forma de `ConnectorTools` para reutilizar su diálogo. Encender o
 * apagar una sola herramienta sigue siendo `PUT /capabilities?agent=`
 * (`setCapability`). Se esparce en `backendFor`.
 *
 * El cliente sale del `ref`: ningún cuerpo lleva `tenant_id` ni `partner_id`.
 * Los errores llegan como `BackendError` con su código: `reservas_mode_required`,
 * `reservas_kind_required`, `reservas_kind_forbidden` (422), `too_many_tools`
 * (422, con `max`), `spec_invalid` (422, con `problems`), `archived` y
 * `no_partner` (409).
 */

export * from "./agenda-types";

export function agendaApi(call: Call) {
  const enc = encodeURIComponent;
  const agent = (ref: string, agentId: string) => `/console/clients/${enc(ref)}/agents/${enc(agentId)}`;
  return {
    getAgentAgenda: (ref: string, agentId: string) => call<AgentAgenda>(`${agent(ref, agentId)}/agenda`),
    setAgentAgenda: (ref: string, agentId: string, body: AgendaBody) =>
      call<AgentAgenda>(`${agent(ref, agentId)}/agenda`, { method: "PUT", body }),
    agendaTools: (ref: string, agentId: string, lang: "es" | "en") =>
      call<ConnectorTools>(`${agent(ref, agentId)}/agenda/tools${q({ lang })}`),
  };
}
