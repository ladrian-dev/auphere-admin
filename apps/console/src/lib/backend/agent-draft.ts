import type { Call } from "../backend";

import type { AgentDraft, AgentVersionEntry, DraftPatch } from "./agent-draft-types";

/**
 * Lane module of the agent's one draft (spec 047, historia 2): read it, write
 * into it with the revision the screen read (`If-Match`), discard it, and the
 * agent's history. A stale write answers 412 with the draft as it is now and
 * what changed — `BackendError.code` is `revision_conflict` and `info` carries
 * `current` and `changes`. Spread into `backendFor` in `lib/backend.ts`.
 */

export * from "./agent-draft-types";

/** `If-Match` of a revision: the strong ETag the API answers with. */
export function ifMatch(revision: number): Record<string, string> {
  return { "If-Match": `"${revision}"` };
}

export function agentDraftApi(call: Call) {
  const enc = encodeURIComponent;
  const agent = (ref: string, agentId: string) => `/console/clients/${enc(ref)}/agents/${enc(agentId)}`;
  return {
    getAgentDraft: (ref: string, agentId: string) => call<AgentDraft>(`${agent(ref, agentId)}/draft`),
    saveAgentDraft: (ref: string, agentId: string, revision: number, patch: DraftPatch) =>
      call<AgentDraft>(`${agent(ref, agentId)}/draft`, { method: "PATCH", body: patch, headers: ifMatch(revision) }),
    discardAgentDraft: (ref: string, agentId: string, revision: number) =>
      call<AgentDraft>(`${agent(ref, agentId)}/draft`, { method: "DELETE", headers: ifMatch(revision) }),
    listAgentVersions: (ref: string, agentId: string) => call<AgentVersionEntry[]>(`${agent(ref, agentId)}/versions`),
  };
}
