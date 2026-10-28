import type { Call } from "../backend";
import { BackendError, tokenFor } from "../backend";
import { env } from "../env";
import type { Principal } from "../principal";

import type { AgentKnowledge, KnowledgeSource, TeachScope } from "./agent-knowledge-types";

/**
 * Carril del conocimiento en dos capas (spec 047, historia 22; T134 sobre T133):
 * `contracts/console-api.md` §4. Se esparce en `backendFor`.
 *
 * - la capa del agente: `GET/POST …/agents/{agent_id}/knowledge`, `POST …/url`,
 *   `DELETE …/{doc_id}` (quitar) y `POST …/{doc_id}/restore` (10 minutos);
 * - «Enseñar»: `POST …/agents/{agent_id}/teach` `{text, scope}` → la fuente que crea;
 * - la capa del negocio sigue en `/clients/{ref}/knowledge` (`agent-tools.ts`);
 *   aquí solo su `restore`, que es nuevo.
 *
 * Los errores llegan como `BackendError` con su código: `undo_window_closed`
 * (409), `teach_empty` y `teach_too_long` (422). Una fuente de otro agente es
 * un 404 (garantía 9).
 */

export * from "./agent-knowledge-types";

export function agentKnowledgeApi(call: Call) {
  const enc = encodeURIComponent;
  const client = (ref: string) => `/console/clients/${enc(ref)}`;
  const agent = (ref: string, agentId: string) => `${client(ref)}/agents/${enc(agentId)}`;
  return {
    getAgentKnowledge: (ref: string, agentId: string) => call<AgentKnowledge>(`${agent(ref, agentId)}/knowledge`),
    addAgentKnowledgeUrl: (ref: string, agentId: string, body: { url: string; title?: string }) =>
      call<KnowledgeSource>(`${agent(ref, agentId)}/knowledge/url`, { method: "POST", body }),
    removeAgentKnowledge: (ref: string, agentId: string, docId: string) =>
      call<null>(`${agent(ref, agentId)}/knowledge/${enc(docId)}`, { method: "DELETE" }),
    restoreAgentKnowledge: (ref: string, agentId: string, docId: string) =>
      call<KnowledgeSource>(`${agent(ref, agentId)}/knowledge/${enc(docId)}/restore`, { method: "POST" }),
    teachAgent: (ref: string, agentId: string, body: { text: string; scope: TeachScope }) =>
      call<KnowledgeSource>(`${agent(ref, agentId)}/teach`, { method: "POST", body }),
    /** Deshacer «Eliminar» en la capa del negocio, durante 10 minutos. */
    restoreKnowledge: (ref: string, docId: string) =>
      call<KnowledgeSource>(`${client(ref)}/knowledge/${enc(docId)}/restore`, { method: "POST" }),
  };
}

/**
 * Subir un archivo solo para este agente. Como `uploadKnowledgeFile`: `request()`
 * solo habla JSON, así que firma su propio token de 60 s y manda el `FormData`
 * (`file` y `title` opcional) tal cual. 413 por encima de 10 MB.
 */
export async function uploadAgentKnowledgeFile(principal: Principal, ref: string, agentId: string, formData: FormData): Promise<KnowledgeSource> {
  const token = await tokenFor(principal);
  const url = `${env().NEXUS_BACKEND_URL}/console/clients/${encodeURIComponent(ref)}/agents/${encodeURIComponent(agentId)}/knowledge`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    body: formData,
    cache: "no-store",
  });
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) throw new BackendError(res.status, url, parsed);
  return parsed as KnowledgeSource;
}
