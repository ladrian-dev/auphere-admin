import type { Call } from "../backend";

import type { ModelPolicy, ModelQuality, QualityCheckAccepted } from "./model-quality-types";

/**
 * Carril de Agente › Avanzado › Calidad (spec 047, T147; requisito 39;
 * `contracts/console-api.md` §4): las opciones con su precio estimado por
 * mensaje, la comprobación de cada una y el precio real de 7 días; y
 * «Comprobar la calidad», un trabajo (`202 {job_id}`) que se consulta con
 * `getConsoleJob` como las pasadas de pruebas. Se esparce en `backendFor`.
 *
 * Los errores llegan como `BackendError` con su código: `invalid_model_policy`
 * (422), `profile_not_eu_servable` (409), `no_version` (409) y
 * `build_budget_exhausted` (402).
 */

export * from "./model-quality-types";

export function modelQualityApi(call: Call) {
  const enc = encodeURIComponent;
  const agent = (ref: string, agentId: string) => `/console/clients/${enc(ref)}/agents/${enc(agentId)}`;
  return {
    getModelQuality: (ref: string, agentId: string) => call<ModelQuality>(`${agent(ref, agentId)}/quality`),
    checkModelQuality: (ref: string, agentId: string, policy: ModelPolicy) =>
      call<QualityCheckAccepted>(`${agent(ref, agentId)}/quality/check`, { method: "POST", body: { model_policy: policy } }),
  };
}
