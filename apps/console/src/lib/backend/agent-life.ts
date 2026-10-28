import type { Call } from "../backend";

import type { AgentHeader, ChannelDestination, CopilotAnswer, CopilotContext, CopilotFixResult } from "./agent-life-types";

/**
 * Carril de la vida de un agente, del copiloto y de «Completar con el
 * constructor» (spec 047, historias 18, 19 y 20; T124, T099 y T098):
 * `contracts/console-api.md` §3 y §4. Se esparce en `backendFor`.
 *
 * Los errores llegan como `BackendError` con su código: `confirm_required`
 * (409, con `open_conversations`), `channel_destination_required`,
 * `default_agent_required`, `unknown_target_agent`, `no_version`,
 * `build_budget_exhausted` (402) e `invalid_fix` (con `problems`).
 */

export * from "./agent-life-types";

export function agentLifeApi(call: Call) {
  const enc = encodeURIComponent;
  const client = (ref: string) => `/console/clients/${enc(ref)}`;
  const agent = (ref: string, agentId: string) => `${client(ref)}/agents/${enc(agentId)}`;
  return {
    getAgentHeader: (ref: string, agentId: string) => call<AgentHeader>(agent(ref, agentId)),
    pauseAgent: (ref: string, agentId: string, body: { confirm?: boolean; note?: string }) =>
      call<AgentHeader>(`${agent(ref, agentId)}/pause`, { method: "POST", body }),
    resumeAgent: (ref: string, agentId: string) => call<AgentHeader>(`${agent(ref, agentId)}/resume`, { method: "POST" }),
    archiveAgentWith: (ref: string, agentId: string, channels: ChannelDestination[]) =>
      call<AgentHeader>(`${agent(ref, agentId)}/archive`, { method: "POST", body: { channels } }),
    restoreAgent: (ref: string, agentId: string) => call<AgentHeader>(`${agent(ref, agentId)}/restore`, { method: "POST" }),
    setDefaultAgent: (ref: string, agentId: string) =>
      call<AgentHeader>(`${client(ref)}/default-agent`, { method: "PUT", body: { agent_id: agentId } }),

    askCopilot: (ref: string, agentId: string, message: string, context?: CopilotContext) =>
      call<CopilotAnswer>(`${agent(ref, agentId)}/copilot`, { method: "POST", body: context ? { message, context } : { message } }),
    copilotFix: (ref: string, agentId: string, body: { test_id: string; scope: "business" | "agent"; value: string }) =>
      call<CopilotFixResult>(`${agent(ref, agentId)}/copilot/fix`, { method: "POST", body }),

    startClientBuilder: (ref: string) => call<{ job_id: string }>(`${client(ref)}/business/builder`, { method: "POST" }),
  };
}
