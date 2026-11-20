/**
 * Carril ``models`` (spec 065, `contracts/api.md` § Consola): el modelo con el
 * que responde cada agente, lo que el partner puede elegir con su precio
 * estimado, y el cambio. Es un ajuste vivo del agente: vale desde su siguiente
 * turno, sin publicar versión.
 *
 * El modelo por cliente (`GET/PUT /console/clients/{ref}/model`, spec 016) se
 * retiró con esta spec (requisito 12.4): la API responde `410` y la consola ya
 * no lo llama. ``partner_id``/``tenant_id`` nunca viajan.
 *
 * Los errores del `PUT` llegan como `BackendError` con su código:
 * `unknown_model` (422) y `model_unavailable_for_agent` (422).
 */
import type { Call } from "../backend";

/** Lo que costaría una respuesta de este agente con un modelo, en cien milésimas. */
export type ModelEstimate = {
  amount_micros: number;
  currency: string;
  /** `agent_7d`: con el consumo real del agente · `nominal`: sin consumo, con un turno típico. */
  basis: "agent_7d" | "nominal";
};

/** La elección guardada del agente; `null` si sigue el modelo por defecto de Auphere. */
export type AgentModelChoice = {
  model_id: string;
  display_name: string;
  set_by: "partner" | "operator";
  set_at: string | null;
};

/** El modelo con el que responde ahora, también cuando no está entre las opciones. */
export type AgentModelEffective = {
  model_id: string;
  display_name: string;
  source: "agent" | "agent_operator" | "version" | "platform";
  /** `retired`: ya no se ofrece · `operator`: lo eligió Auphere fuera de la lista del partner. */
  outside_offer: "retired" | "operator" | null;
  estimate: ModelEstimate | null;
};

export type AgentModelOption = {
  model_id: string;
  display_name: string;
  /** `openai` · `anthropic`. */
  provider: string;
  /** La gama: la consola la traduce a una línea sobre para qué sirve (requisito 1.5). */
  line: "max" | "balanced" | "economy";
  estimate: ModelEstimate | null;
};

export type AgentModel = {
  agent_id: string;
  choice: AgentModelChoice | null;
  effective: AgentModelEffective;
  /** La oferta del partner para este agente, del más barato al más caro. */
  options: AgentModelOption[];
  notice: "chosen_model_cannot_run_agent" | null;
  /** `agents:write`. */
  can_change: boolean;
};

export function modelsApi(call: Call) {
  const enc = encodeURIComponent;
  const path = (ref: string, agentId: string) => `/console/clients/${enc(ref)}/agents/${enc(agentId)}/model`;
  return {
    getAgentModel: (ref: string, agentId: string) => call<AgentModel>(path(ref, agentId)),
    /** La consola nunca manda `null` (volver al modelo por defecto): eso es del panel (requisito 2.7). */
    setAgentModel: (ref: string, agentId: string, model_id: string) =>
      call<AgentModel>(path(ref, agentId), { method: "PUT", body: { model_id } }),
  };
}
