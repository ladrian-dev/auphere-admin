/**
 * Spec 030 (R14.5) in the panel's Playground: which of the client's agents is
 * tested, and which threads are that agent's. Shared by `/qa/{client}/chat`
 * and the client's Playground tab.
 *
 * `?agent=` names it, as in the Agent tab; without it (or with one that is
 * not an active agent of this client) it is the principal. If the agents
 * cannot be read, nothing is chosen here: the API opens new threads with the
 * principal and every thread is listed.
 */
import type { TenantAgent } from "@/lib/backend";
import type { QAThread } from "@/lib/qa-api";

export type PlaygroundAgent = {
  /** Active agents of the client, for the selector. */
  agents: TenantAgent[];
  /** The agent on screen, or `null` when the agents could not be read. */
  selected: TenantAgent | null;
};

export function pickPlaygroundAgent(
  listed: TenantAgent[] | null,
  wanted: string | undefined,
): PlaygroundAgent {
  const agents = (listed ?? []).filter((a) => a.status === "active");
  const principal = agents.find((a) => a.is_principal) ?? agents[0] ?? null;
  const selected = agents.find((a) => a.id === wanted) ?? principal;
  return { agents, selected };
}

/** The threads of `selected`: a thread without agent is the principal's. */
export function threadsOfAgent(threads: QAThread[], selected: TenantAgent | null): QAThread[] {
  if (selected === null) return threads;
  return threads.filter(
    (t) => t.agent_id === selected.id || (selected.is_principal && t.agent_id === null),
  );
}

/** What the shell needs: `query` is `null` for the principal, so its links
 *  keep their shape from before. */
export function shellAgent(selected: TenantAgent | null) {
  return selected
    ? { id: selected.id, name: selected.name, query: selected.is_principal ? null : selected.id }
    : null;
}
