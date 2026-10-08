import "server-only";

import { cache } from "react";

import { backendFor, type ClientAgent } from "@/lib/backend";
import type { Principal } from "@/lib/principal";

/** One fetch per request for layout + metadata + page. */
export const getClientCached = cache(async (principal: Principal, ref: string) => backendFor(principal).getClient(ref));

/** Spec 017 (R3.1): el layout necesita saber si hay borrador y en qué
 *  pantallas, para el punto de la pestaña y para la barra. Una lectura por
 *  petición, compartida por el layout y por la pestaña que la vuelva a
 *  pedir. Falla en silencio: un borrador que no se puede leer no debe
 *  tumbar la ficha entera. */
export const getAgentBundleCached = cache(async (principal: Principal, ref: string, agent?: string) =>
  backendFor(principal)
    .getAgent(ref, agent)
    .catch(() => null),
);

/** Spec 030 (R14): the client's active agents, principal first. `null` when
 *  they cannot be read — the tabs then act on the principal, as they did
 *  before a client could have more than one. */
export const getAgentsCached = cache(async (principal: Principal, ref: string) =>
  backendFor(principal)
    .listAgents(ref)
    .catch(() => null),
);

export type AgentChoice = {
  /** Empty with fewer than two agents: there is nothing to choose. */
  agents: ClientAgent[];
  /** The agent the tab acts on; `undefined` is the principal (no `?agent=`). */
  agentId: string | undefined;
  agentName: string | null;
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The agent a tab of the record acts on (spec 030): `?agent=` when it names
 * one of the client's agents. Anything else — no parameter, the principal's
 * own id, an id of nobody's — is the principal, so a stale link never ends
 * on an error page.
 *
 * When the list cannot be read, an agent named in the URL is passed on as it
 * is and the API decides (404 if it is not this client's): falling back to
 * the principal there would let someone edit the wrong agent without
 * knowing it.
 */
export async function agentChoice(principal: Principal, ref: string, raw: string | undefined): Promise<AgentChoice> {
  const listed = await getAgentsCached(principal, ref);
  if (listed === null) {
    return { agents: [], agentId: raw && UUID_RE.test(raw) ? raw : undefined, agentName: null };
  }
  const all = listed;
  const agents = all.length > 1 ? all : [];
  const picked = agents.find((a) => a.id === raw && !a.is_principal);
  const principalAgent = agents.find((a) => a.is_principal);
  return { agents, agentId: picked?.id, agentName: (picked ?? principalAgent)?.name ?? null };
}
