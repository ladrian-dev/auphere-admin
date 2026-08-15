import "server-only";

import { env } from "./env";
import { mintPrincipalToken, mintServiceToken } from "./jwt";
import type { Principal } from "./principal";

/**
 * Typed client for the API's ``/console/*`` family (CP-03/CP-04).
 *
 * Written clean — NOT copied from apps/admin. The differences are the
 * point:
 *
 *  - there is no static credential: every call mints a fresh 60-second
 *    EdDSA token for the CURRENT principal (``mintPrincipalToken``);
 *  - the client never sends ``tenant_id``/``partner_id`` — the API does
 *    not accept them, clients are addressed by ``external_client_ref``;
 *  - ``BackendError`` keeps the same three fields as the admin's
 *    (``status``, ``url``, ``body``) so error handling stays interchangeable.
 */
export class BackendError extends Error {
  constructor(
    public readonly status: number,
    public readonly url: string,
    public readonly body: unknown,
  ) {
    super(
      `backend ${status} ${url}: ${
        typeof body === "string" ? body.slice(0, 200) : JSON.stringify(body).slice(0, 200)
      }`,
    );
    this.name = "BackendError";
  }
  /** FastAPI ``detail`` when present — the message a partner should read. */
  get detail(): string {
    const b = this.body as { detail?: unknown } | null;
    if (b && typeof b === "object" && typeof b.detail === "string") return b.detail;
    return this.message;
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type Opts = { method?: Method; body?: unknown; optional?: boolean; signal?: AbortSignal };

async function request<T>(token: string, path: string, opts: Opts = {}): Promise<T | null> {
  const url = `${env().NEXUS_BACKEND_URL}${path}`;
  const res = await fetch(url, {
    method: opts.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
    signal: opts.signal,
  });
  if (res.status === 404 && opts.optional) return null;
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
  return parsed as T;
}

// ── response types (mirror api/console/schemas.py — metadata only) ─────

export type Quota = {
  max_clients: number;
  used_clients: number;
  remaining_clients: number;
  max_channels_per_client: number;
};
export type Me = {
  user_id: string;
  email: string;
  display_name: string | null;
  role: string;
  permissions: string[];
  membership_id: string;
  partner: { slug: string; name: string; status: string };
  quota: Quota;
};
export type ClientSummary = {
  external_client_ref: string;
  name: string;
  status: "provisioning" | "active" | "paused" | "archived";
  timezone: string;
  created_at: string;
  updated_at: string;
};
export type ClientHealth = {
  whatsapp_connected: boolean;
  display_phone_number: string | null;
  agent_version: number | null;
  agent_configured: boolean;
  ready: boolean;
  missing: string[];
};
export type Client = ClientSummary & { health: ClientHealth };
export type ClientPage = { items: ClientSummary[]; total: number; limit: number; offset: number };
export type ClientCreated = {
  external_client_ref: string;
  status: string;
  agent_status: string;
  whatsapp_connected: boolean;
  quota: Quota;
};
export type AgentVersion = {
  version: number;
  status: "staged" | "active" | "archived";
  system_prompt: string;
  tools: string[];
  seed_template_ref: string | null;
  created_by: string | null;
  created_at: string;
  promoted_at: string | null;
  promoted_by: string | null;
};
export type AgentBundle = { active_version: number | null; versions: AgentVersion[] };
export type Channel = {
  id: string;
  type: string;
  provider: string;
  provider_identifier: string;
  status: string;
  role: string | null;
  last_health_check_at: string | null;
  created_at: string;
};
export type ConversationMeta = {
  id: string;
  channel_id: string;
  channel_type: string | null;
  status: string;
  agent_active: boolean;
  started_at: string;
  last_activity_at: string;
  turns: number;
  inbound_messages: number;
  outbound_messages: number;
  failed_messages: number;
  escalated: boolean;
  avg_latency_ms: number | null;
  duration_seconds: number | null;
};
export type ConversationPage = { items: ConversationMeta[]; total: number; limit: number; offset: number };
export type ConversationStats = {
  since: string;
  until: string;
  conversations: number;
  open: number;
  escalated: number;
  closed: number;
  turns: number;
  failed_messages: number;
  avg_latency_ms: number | null;
};
export type UsageBucket = {
  external_client_ref: string | null;
  client_name: string | null;
  meter: string;
  source: "channel" | "qa";
  quantity: number;
  billable_qty: number;
  records: number;
};
export type UsageReport = {
  since: string;
  until: string;
  buckets: UsageBucket[];
  totals_by_meter: Record<string, number>;
  total_records: number;
};
export type AuditEntry = {
  id: string;
  at: string;
  actor: string;
  action: string;
  target: string;
  external_client_ref: string | null;
  client_name: string | null;
  summary: string;
};
export type AuditPage = { items: AuditEntry[]; next_cursor: string | null };
export type Member = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  status: string;
  accepted_at: string | null;
  created_at: string;
  is_you: boolean;
};
export type Invitation = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  created_at: string;
};
export type InvitationCreated = Invitation & { accept_path: string; email_sent: boolean };
export type Team = { members: Member[]; invitations: Invitation[] };
export type InvitationLookup = { partner_name: string; email: string; role: string; expires_at: string };
export type InvitationAccepted = { membership_id: string; partner: { slug: string; name: string; status: string }; role: string };
export type ApiKey = {
  id: string;
  type: "live" | "test";
  prefix_snippet: string;
  scopes: string[];
  allowed_origins: string[];
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  grace_expires_at: string | null;
};
export type ApiKeyCreated = ApiKey & { plaintext: string };
export type ReceiptSummary = {
  invoice_id: string;
  period_year: number;
  period_month: number;
  total_usd: number;
  currency: string;
  status: string;
  issued_at: string | null;
  due_date: string;
};
export type Billing = { billing_email: string | null; contact_email: string | null; receipts: ReceiptSummary[] };

// ── client factory ─────────────────────────────────────────────────────

const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
};

/** A backend client bound to a principal. Every method mints its own token. */
export function backendFor(principal: Principal) {
  const claims = { userId: principal.userId, partnerId: principal.partnerId, role: principal.role };
  const call = async <T>(path: string, opts?: Opts): Promise<T> => {
    const token = await mintPrincipalToken(claims);
    return (await request<T>(token, path, opts)) as T;
  };
  const enc = encodeURIComponent;
  return {
    me: () => call<Me>("/console/me"),

    listClients: (p: { q?: string; status?: string; sort?: string; order?: string; limit?: number; offset?: number } = {}) =>
      call<ClientPage>(`/console/clients${q(p)}`),
    getClient: (ref: string) => call<Client>(`/console/clients/${enc(ref)}`),
    createClient: (body: { external_client_ref: string; name: string; timezone?: string; placeholders?: Record<string, unknown> }) =>
      call<ClientCreated>("/console/clients", { method: "POST", body }),
    updateClient: (ref: string, body: { name?: string; timezone?: string }) =>
      call<Client>(`/console/clients/${enc(ref)}`, { method: "PATCH", body }),
    setClientStatus: (ref: string, status: "active" | "paused" | "archived") =>
      call<Client>(`/console/clients/${enc(ref)}/status`, { method: "POST", body: { status } }),
    deleteClient: (ref: string, confirmName: string) =>
      call<null>(`/console/clients/${enc(ref)}`, { method: "DELETE", body: { confirm_name: confirmName } }),

    getAgent: (ref: string) => call<AgentBundle>(`/console/clients/${enc(ref)}/agent`),
    stageAgentVersion: (ref: string, body: { system_prompt: string; tools?: string[] }) =>
      call<AgentVersion>(`/console/clients/${enc(ref)}/agent/versions`, { method: "POST", body }),
    publishAgentVersion: (ref: string, version: number) =>
      call<AgentVersion>(`/console/clients/${enc(ref)}/agent/versions/${version}/publish`, { method: "POST" }),
    rollbackAgentVersion: (ref: string, version: number) =>
      call<AgentVersion>(`/console/clients/${enc(ref)}/agent/versions/${version}/rollback`, { method: "POST" }),

    listChannels: (ref: string) => call<Channel[]>(`/console/clients/${enc(ref)}/channels`),
    listConversations: (ref: string, p: { status?: string; escalated?: boolean; with_errors?: boolean; limit?: number; offset?: number } = {}) =>
      call<ConversationPage>(`/console/clients/${enc(ref)}/conversations${q(p)}`),
    conversationStats: (ref: string, days = 30) =>
      call<ConversationStats>(`/console/clients/${enc(ref)}/conversations/stats${q({ days })}`),

    usage: (p: { days?: number; client?: string; source?: string } = {}) => call<UsageReport>(`/console/usage${q(p)}`),
    audit: (p: { limit?: number; cursor?: string; actor?: string; action?: string; client?: string } = {}) =>
      call<AuditPage>(`/console/audit${q(p)}`),

    team: () => call<Team>("/console/team"),
    invite: (body: { email: string; role: string }) => call<InvitationCreated>("/console/team/invitations", { method: "POST", body }),
    revokeInvitation: (id: string) => call<null>(`/console/team/invitations/${enc(id)}`, { method: "DELETE" }),
    changeMemberRole: (id: string, role: string) => call<Member>(`/console/team/members/${enc(id)}/role`, { method: "PATCH", body: { role } }),
    changeMemberStatus: (id: string, status: "active" | "suspended") =>
      call<Member>(`/console/team/members/${enc(id)}/status`, { method: "PATCH", body: { status } }),
    removeMember: (id: string) => call<null>(`/console/team/members/${enc(id)}`, { method: "DELETE" }),

    listKeys: () => call<ApiKey[]>("/console/keys"),
    createKey: (body: { type?: "live" | "test"; scopes?: string[]; allowed_origins?: string[] }) =>
      call<ApiKeyCreated>("/console/keys", { method: "POST", body }),
    rotateKey: (id: string, graceHours = 24) => call<ApiKeyCreated>(`/console/keys/${enc(id)}/rotate`, { method: "POST", body: { grace_hours: graceHours } }),
    revokeKey: (id: string) => call<ApiKey>(`/console/keys/${enc(id)}/revoke`, { method: "POST" }),

    billing: () => call<Billing>("/console/billing"),
  };
}

export type Backend = ReturnType<typeof backendFor>;

/** Pre-membership calls (invitation lookup/accept) — service token. */
export const consoleService = {
  async lookupInvitation(token: string): Promise<InvitationLookup | null> {
    const t = await mintServiceToken();
    return request<InvitationLookup>(t, `/console/invitations/${encodeURIComponent(token)}`, { optional: true });
  },
  async acceptInvitation(token: string, body: { user_id: string; email: string; display_name?: string | null }): Promise<InvitationAccepted> {
    const t = await mintServiceToken();
    return (await request<InvitationAccepted>(t, `/console/invitations/${encodeURIComponent(token)}/accept`, {
      method: "POST",
      body,
    })) as InvitationAccepted;
  },
};
