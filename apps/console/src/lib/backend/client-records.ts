import "server-only";

import { env } from "@/lib/env";
import type { Principal } from "@/lib/principal";

import { BackendError, q, tokenFor, type Call, type Job } from "../backend";
import type { ClientRead, Network, WalletCurrency } from "./clients-v2";

/**
 * Spec 047 (T062–T072) — el cliente con la consola nueva: su ciclo de vida, la
 * lista, el Panel y su ficha (procedencia, historial, propuestas, fuentes y
 * ClientSpec). `contracts/console-api.md` §2 y §3.
 *
 * El dinero llega como `{amount_micros, currency}` (cien milésimas). Ninguna
 * respuesta trae cuerpos de mensaje, teléfonos de clientes finales ni costes.
 */

export type Money = { amount_micros: number; currency: "EUR" | "USD" };
export type Lifecycle = "active" | "paused" | "archived";
export type ClientAction = "edit" | "assign_balance" | "request_balance" | "new_agent" | "archive" | "restore" | "delete";
export type AgentVisible = "archived" | "paused" | "draft" | "serving" | "testing" | "ready_no_channel";
export type Tone = "positive" | "info" | "warn" | "danger" | "muted";
export type PauseReason = "manual" | "no_balance" | "agent_cap" | "client_paused" | "client_archived";
export type VisibleState = { code: AgentVisible; tone: Tone; pause_reason: PauseReason | null };
export type AttentionCode =
  | "no_balance"
  | "channel_problem"
  | "integration_reauth"
  | "agent_cap"
  | "agent_without_channel"
  | "low_balance"
  | "no_agents";
export type Attention = { needs: boolean; reasons: { code: AttentionCode; count: number }[] };
export type BagState = "ok" | "low" | "not_enough" | "empty" | "unlimited" | "unassigned";
export type Bag = {
  state: BagState;
  balance: Money | null;
  assigned: Money | null;
  spent: Money | null;
  pct_spent: number | null;
  pct_left: number | null;
  days_left: number | null;
  days_estimable: boolean;
  alerts: ("warn_80" | "empty")[];
};
export type ClientAgent = { agent_id: string; name: string; visible_state: VisibleState };
export type AgentsSummary = { total: number; serving: number; testing: number; ready_no_channel: number; draft: number; paused: number };

export type ClientRowV2 = {
  external_client_ref: string;
  name: string;
  status: string;
  timezone: string;
  niche: string | null;
  lifecycle: Lifecycle;
  attention: Attention | null;
  agents: ClientAgent[];
  agents_summary: AgentsSummary | null;
  bag: Bag | null;
  allowed: ClientAction[];
};
export type ClientFilter = "all" | "attention" | "active" | "archived";
export type ClientCounts = Record<ClientFilter, number>;
export type ClientListV2 = { items: ClientRowV2[]; total: number; limit: number; offset: number; counts: ClientCounts | null };

export type ClientDetailV2 = {
  external_client_ref: string;
  name: string;
  status: string;
  timezone: string;
  niche: string | null;
  info: string | null;
  website: string | null;
  country: string | null;
  price_currency: string | null;
  wallet_currency: WalletCurrency | null;
  eu_only: boolean | null;
  lifecycle: Lifecycle;
  revision: number | null;
  allowed: ClientAction[];
};

export type ClientEditBody = {
  name?: string;
  niche?: string;
  info?: string | null;
  country?: string | null;
  timezone?: string;
  price_currency?: string | null;
  wallet_currency?: WalletCurrency;
  eu_only?: boolean;
};

export type AgentLifecycle = { agent_id: string; name: string; visible_state: VisibleState; before: VisibleState | null };
export type ClientLifecycleResult = {
  ref: string;
  lifecycle: Lifecycle;
  previous: Lifecycle | null;
  agents: AgentLifecycle[];
  undo: "restore" | null;
};

export type MissingSection = "hours" | "services" | "locations" | "sources" | "links";
export type ClientPanel = {
  ref: string;
  name: string;
  niche: string | null;
  lifecycle: Lifecycle;
  bag: Bag;
  attention: Attention;
  spend_by_agent: { agent_id: string; name: string; spent: Money; share_pct: number }[];
  month: {
    period_start: string;
    period_end: string;
    conversations: number;
    handed_to_person: number;
    resolved_without_person: number;
    resolved_pct: number | null;
    spent: Money;
  };
  top_agents: {
    agent_id: string;
    name: string;
    visible_state: VisibleState;
    spent: Money;
    conversations: number;
    spend_per_conversation: Money | null;
    cap: Money | null;
  }[];
  agents_total: number;
  missing: { section: MissingSection; action: `add_${MissingSection}` } | null;
  read: ClientRead;
  allowed: ClientAction[];
};

// ── la ficha ────────────────────────────────────────────────────────────────

export type Section = "basics" | "locations" | "hours" | "special_dates" | "services" | "policies" | "faqs" | "sources" | "links";
export type SectionState = "complete" | "read_pending" | "pending" | "optional";
export type ProvenanceSource = "person" | "web" | "document" | "social" | "migrated" | "builder" | "inbox_correction" | "import";
export type Origin = "console" | "lite_web" | "app" | "admin" | "api" | "system";
export type ActorKind = "partner_member" | "client_user" | "operator" | "system" | "builder";
export type Person = { kind: ActorKind; id: string | null; name: string | null };
export type Provenance = {
  source: ProvenanceSource;
  by: Person | null;
  origin: Origin;
  at: string;
  source_url: string | null;
  translated_from: string | null;
  review: "pending" | "confirmed";
};
export type SectionInfo = {
  section: Section;
  state: SectionState;
  revision: number;
  updated_at: string | null;
  updated_by: Person | null;
  origin: Origin | null;
  pending_suggestions: number;
};
export type Suggestion = {
  id: string;
  pointer: string;
  section: Section;
  proposed_value: unknown;
  current_value: unknown;
  source: ProvenanceSource;
  source_url: string | null;
  translated_from: string | null;
  created_at: string;
};
export type BusinessRecord = {
  spec: Record<string, unknown>;
  valid: boolean;
  problems: { pointer: string; code: string }[];
  sections: SectionInfo[];
  provenance: Record<string, Provenance>;
  suggestions: Suggestion[];
  allowed: ("edit" | "import" | "undo" | "decide")[];
};
export type ChangeKind = "edit" | "read_applied" | "builder_applied" | "correction" | "migration" | "import" | "undo";
export type Change = {
  id: string;
  section: Section;
  kind: ChangeKind;
  at: string;
  by: Person | null;
  origin: Origin;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  undone_at: string | null;
  undo_of: string | null;
  undoable: boolean;
};
export type LinkItem = { id: string; network: Network; url: string | null; handle: string | null };
export type SourceFailure = "unreachable" | "blocked" | "no_text" | "too_large";
export type Source = {
  id: string;
  kind: "file" | "web";
  title: string;
  url: string | null;
  status: "reading" | "read" | "failed";
  failure: SourceFailure | null;
  size_bytes: number;
  read_at: string | null;
  created_at: string;
};
export type RemovedSource = { id: string; kind: "file" | "web"; title: string; restore_until: string };
export type Sources = { items: Source[]; removed: RemovedSource[]; max_bytes: number; allowed: ("add" | "remove" | "reread")[] };

export function clientRecordsApi(call: Call) {
  const enc = encodeURIComponent;
  const base = (ref: string) => `/console/clients/${enc(ref)}`;
  const biz = (ref: string) => `${base(ref)}/business`;
  const ifMatch = (revision: number) => ({ "If-Match": `"${revision}"` });
  return {
    listClientsV2: (params: { q?: string; filter?: ClientFilter; limit?: number; offset?: number }) =>
      call<ClientListV2>(`/console/clients${q({ ...params, filter: params.filter ?? "all" })}`),
    getClientV2: (ref: string) => call<ClientDetailV2>(base(ref)),
    updateClientV2: (ref: string, body: ClientEditBody, revision: number) =>
      call<ClientDetailV2>(base(ref), { method: "PATCH", body, headers: ifMatch(revision) }),
    archiveClient: (ref: string) => call<ClientLifecycleResult>(`${base(ref)}/archive`, { method: "POST" }),
    restoreClient: (ref: string) => call<ClientLifecycleResult>(`${base(ref)}/restore`, { method: "POST" }),
    deleteClientV2: (ref: string, confirmName: string) =>
      call<null>(base(ref), { method: "DELETE", body: { confirm_name: confirmName } }),
    getClientPanel: (ref: string) => call<ClientPanel>(`${base(ref)}/panel`),
    getBusiness: (ref: string) => call<BusinessRecord>(biz(ref)),
    putLinks: (ref: string, links: { network: Network; url?: string | null; handle?: string | null }[], revision: number) =>
      call<{ links: LinkItem[]; revision: number }>(`${biz(ref)}/links`, { method: "PUT", body: { links }, headers: ifMatch(revision) }),
    confirmSection: (ref: string, section: Section) =>
      call<{ section: Section; state: SectionState; revision: number; confirmed: number }>(
        `${biz(ref)}/sections/${enc(section)}/confirm`,
        { method: "POST" },
      ),
    getHistory: (ref: string, section?: Section) => call<{ items: Change[] }>(`${biz(ref)}/history${q({ section })}`),
    undoChange: (ref: string, changeId: string) =>
      call<{ section: Section; revision: number | null; change_id: string | null }>(`${biz(ref)}/history/${enc(changeId)}/undo`, {
        method: "POST",
      }),
    decideSuggestion: (ref: string, id: string, decision: "accept" | "edit" | "discard", value?: unknown) =>
      call<{ suggestion_id: string; decision: string; section: Section; revision: number | null }>(
        `${biz(ref)}/suggestions/${enc(id)}/decide`,
        { method: "POST", body: { decision, ...(decision === "edit" ? { value } : {}) } },
      ),
    listSources: (ref: string) => call<Sources>(`${biz(ref)}/sources`),
    addSourceUrl: (ref: string, url: string, title?: string) =>
      call<{ source: Source; job_id: string }>(`${biz(ref)}/sources`, { method: "POST", body: { url, ...(title ? { title } : {}) } }),
    rereadSource: (ref: string, id: string) =>
      call<{ source: Source; job_id: string }>(`${biz(ref)}/sources/${enc(id)}/reread`, { method: "POST" }),
    removeSource: (ref: string, id: string) =>
      call<{ id: string; restore_until: string }>(`${biz(ref)}/sources/${enc(id)}/remove`, { method: "POST" }),
    restoreSource: (ref: string, id: string) => call<Source>(`${biz(ref)}/sources/${enc(id)}/restore`, { method: "POST" }),
    exportSpec: (ref: string) => call<Record<string, unknown>>(`${biz(ref)}/export`),
    importSpec: (ref: string, document: Record<string, unknown>, dryRun: boolean) =>
      call<{ dry_run: boolean; base_hash: string; ops: { op: string; path: string; value: unknown; current: unknown }[]; created: number }>(
        `${biz(ref)}/import${q({ dry_run: dryRun })}`,
        { method: "POST", body: document },
      ),
  };
}

/** Multipart al API (como `uploadKnowledgeFile`): el archivo no pasa por JSON. */
export async function uploadBusinessSource(principal: Principal, ref: string, formData: FormData): Promise<{ source: Source; job_id: string }> {
  const token = await tokenFor(principal);
  const url = `${env().NEXUS_BACKEND_URL}/console/clients/${encodeURIComponent(ref)}/business/sources`;
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
  return parsed as { source: Source; job_id: string };
}

export type { Job };
