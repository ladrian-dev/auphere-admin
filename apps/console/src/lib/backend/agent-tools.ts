import type { Call } from "../backend";
import { BackendError, tokenFor } from "../backend";
import { env } from "../env";
import type { Principal } from "../principal";

import type {
  AgentSettingsOut,
  AgentSettingsSaved,
  ConnectApiKeyBody,
  ConnectorOut,
  ConnectorSyncOut,
  ConsentOut,
  ConsolePolicy,
  KnowledgeDocumentOut,
  KnowledgeListOut,
  SkillsOut,
  SkillsSaved,
  ToolCatalogOut,
  ToolMode,
  ToolModeOut,
  ToolsSaved,
} from "./agent-tools-types";

/**
 * Lane module `agent-tools` (CP-11 settings · CP-13 tools+connectors ·
 * CP-14 skills · CP-15 knowledge · CP-31 AI disclosure). Types mirror
 * `api/console/schemas_agent_tools.py` and `services/agent_console_policy.py`
 * — metadata only, never message bodies, never tenant ids, never the
 * extracted knowledge text. Spread into `backendFor` in `lib/backend.ts`.
 */

export * from "./agent-tools-types";

export function agentToolsApi(call: Call) {
  const enc = encodeURIComponent;
  const base = (ref: string) => `/console/clients/${enc(ref)}`;
  return {
    getAgentSettings: (ref: string) => call<AgentSettingsOut>(`${base(ref)}/agent/settings`),
    putAgentSettings: (ref: string, settings: ConsolePolicy) =>
      call<AgentSettingsSaved>(`${base(ref)}/agent/settings`, { method: "PUT", body: { settings } }),

    listTools: (ref: string) => call<ToolCatalogOut>(`${base(ref)}/tools`),
    putTools: (ref: string, tools: string[]) => call<ToolsSaved>(`${base(ref)}/tools`, { method: "PUT", body: { tools } }),
    putToolMode: (ref: string, toolName: string, mode: ToolMode) =>
      call<ToolModeOut>(`${base(ref)}/tools/${enc(toolName)}/mode`, { method: "PUT", body: { mode } }),
    deleteToolMode: (ref: string, toolName: string) => call<null>(`${base(ref)}/tools/${enc(toolName)}/mode`, { method: "DELETE" }),

    listConnectors: (ref: string) => call<ConnectorOut[]>(`${base(ref)}/connectors`),
    startConsent: (ref: string, slug: string) => call<ConsentOut>(`${base(ref)}/connectors/${enc(slug)}/consent`, { method: "POST" }),
    syncConnector: (ref: string, slug: string) => call<ConnectorSyncOut>(`${base(ref)}/connectors/${enc(slug)}/sync`, { method: "POST" }),
    disconnectConnector: (ref: string, slug: string) => call<ConnectorOut>(`${base(ref)}/connectors/${enc(slug)}/disconnect`, { method: "POST" }),
    pauseConnector: (ref: string, slug: string) => call<ConnectorOut>(`${base(ref)}/connectors/${enc(slug)}/pause`, { method: "POST" }),
    resumeConnector: (ref: string, slug: string) => call<ConnectorOut>(`${base(ref)}/connectors/${enc(slug)}/resume`, { method: "POST" }),
    connectApiKey: (ref: string, slug: string, body: ConnectApiKeyBody) =>
      call<ConnectorOut>(`${base(ref)}/connectors/${enc(slug)}/api-key`, { method: "POST", body }),

    listSkills: (ref: string) => call<SkillsOut>(`${base(ref)}/skills`),
    putSkills: (ref: string, skills: string[]) => call<SkillsSaved>(`${base(ref)}/skills`, { method: "PUT", body: { skills } }),

    listKnowledge: (ref: string) => call<KnowledgeListOut>(`${base(ref)}/knowledge`),
    addKnowledgeUrl: (ref: string, body: { url: string; title?: string }) =>
      call<KnowledgeDocumentOut>(`${base(ref)}/knowledge/url`, { method: "POST", body }),
    deleteKnowledge: (ref: string, docId: string) => call<null>(`${base(ref)}/knowledge/${enc(docId)}`, { method: "DELETE" }),
    reindexKnowledge: (ref: string, docId: string) =>
      call<KnowledgeDocumentOut>(`${base(ref)}/knowledge/${enc(docId)}/reindex`, { method: "POST" }),

    listPlaybook: () => call<KnowledgeListOut>("/console/knowledge"),
    addPlaybookUrl: (body: { url: string; title?: string }) =>
      call<KnowledgeDocumentOut>("/console/knowledge/url", { method: "POST", body }),
    deletePlaybook: (docId: string) => call<null>(`/console/knowledge/${enc(docId)}`, { method: "DELETE" }),
    reindexPlaybook: (docId: string) =>
      call<KnowledgeDocumentOut>(`/console/knowledge/${enc(docId)}/reindex`, { method: "POST" }),
  };
}

/**
 * Multipart upload of one knowledge document. `request()` in `lib/backend.ts`
 * only speaks JSON, so this mints its own 60 s token and streams the
 * `FormData` (`file` + optional `title`) straight to the API. Same
 * `BackendError` shape on failure (413 when the file exceeds 10 MB).
 */
export async function uploadKnowledgeFile(principal: Principal, ref: string, formData: FormData): Promise<KnowledgeDocumentOut> {
  const token = await tokenFor(principal);
  const url = `${env().NEXUS_BACKEND_URL}/console/clients/${encodeURIComponent(ref)}/knowledge`;
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
  return parsed as KnowledgeDocumentOut;
}

export async function uploadPlaybookFile(principal: Principal, formData: FormData): Promise<KnowledgeDocumentOut> {
  const token = await tokenFor(principal);
  const url = `${env().NEXUS_BACKEND_URL}/console/knowledge`;
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
  return parsed as KnowledgeDocumentOut;
}
