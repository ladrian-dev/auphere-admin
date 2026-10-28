import type { Call } from "../backend";
import { q } from "../backend";
import type {
  AgentConversationPage,
  AgentPerformance,
  ImprovementAccepted,
  ImprovementDiscarded,
  Improvements,
} from "./agent-improve-types";

export type * from "./agent-improve-types";

/**
 * Spec 047 (T174) — el cliente de la API del Rendimiento y las Mejoras de un
 * agente. Los tipos viven en `./agent-improve-types.ts`, que no arrastra nada de
 * servidor y se puede importar desde un componente de cliente.
 */
export function agentImproveApi(call: Call) {
  const enc = encodeURIComponent;
  const base = (ref: string, agent: string) => `/console/clients/${enc(ref)}/agents/${enc(agent)}`;
  return {
    getAgentPerformance: (ref: string, agent: string, days: number = 30) =>
      call<AgentPerformance>(`${base(ref, agent)}/performance${q({ days })}`),
    listAgentConversations: (ref: string, agent: string, cursor?: string, limit = 50) =>
      call<AgentConversationPage>(`${base(ref, agent)}/conversations${q({ cursor, limit })}`),
    listImprovements: (ref: string, agent: string) => call<Improvements>(`${base(ref, agent)}/improvements`),
    acceptImprovement: (ref: string, agent: string, id: string) =>
      call<ImprovementAccepted>(`${base(ref, agent)}/improvements/${enc(id)}/accept`, { method: "POST" }),
    discardImprovement: (ref: string, agent: string, id: string, reason: string) =>
      call<ImprovementDiscarded>(`${base(ref, agent)}/improvements/${enc(id)}/discard`, { method: "POST", body: { reason } }),
  };
}
