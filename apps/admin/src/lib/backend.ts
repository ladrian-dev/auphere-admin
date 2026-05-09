/**
 * Typed client for the FastAPI backend (``apps/api``).
 *
 * This is the ONLY surface through which the panel reads the application
 * data — Drizzle in this app is reserved for Better Auth bookkeeping.
 * Reasons:
 *
 *  - The backend is the source-of-truth for tenant_id-scoped data with
 *    Postgres RLS enforced. Querying directly with Drizzle would require
 *    re-implementing the ``SET LOCAL app.tenant_id`` ceremony in TS.
 *  - The backend already exposes versioned ``/admin/*`` endpoints with
 *    audit_log writes on mutation. The panel never reproduces business
 *    logic.
 *
 * Auth model Phase 1: Better Auth gates the panel UI. Once a session is
 * present, every backend call adds the static ``NEXUS_ADMIN_TOKEN``
 * Bearer header. Phase 2 swaps the static token for a per-session JWT
 * the backend co-signs — see decisions/ADR-009.
 *
 * Server-side only. Never import from a client component; the bearer
 * token must not reach the browser.
 */

import "server-only";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8000";
const ADMIN_TOKEN = process.env.NEXUS_ADMIN_TOKEN ?? "dev-admin-token-change-me";

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
  }
}

type FetchOpts = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** When ``true``, a 404 returns ``null`` instead of throwing. */
  optional?: boolean;
};

async function call<T>(path: string, opts: FetchOpts = {}): Promise<T | null> {
  const url = `${BACKEND_URL}${path}`;
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: {
      Authorization: `Bearer ${ADMIN_TOKEN}`,
      Accept: "application/json",
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    cache: "no-store",
    signal: opts.signal,
  };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);

  const res = await fetch(url, init);
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

// ── domain types ────────────────────────────────────────────────────────────

export type TenantStatus = "active" | "paused" | "archived";
export type TenantPlan = "essential" | "pro" | "business" | "internal";

export type Tenant = {
  id: string;
  name: string;
  slug: string;
  plan: TenantPlan;
  status: TenantStatus;
  market: string | null;
  timezone: string;
  business_hours: Record<string, unknown> | null;
  owner_phone: string | null;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentConfig = {
  id: string;
  tenant_id: string;
  version: number;
  status: "staged" | "active" | "archived";
  system_prompt_rendered: string;
  channels: Array<Record<string, unknown>>;
  tools: string[];
  policies: Record<string, unknown>;
  seed_template_ref: string | null;
  kg_schema_id: string | null;
  promoted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentConfigBundle = {
  active: AgentConfig | null;
  versions: AgentConfig[];
};

export type ConversationOut = {
  id: string;
  channel_id: string;
  customer_id: string;
  status: "open" | "closed" | "escalated";
  created_at: string;
  updated_at: string;
};

export type ConversationPage = {
  items: ConversationOut[];
  next_cursor: string | null;
};

export type ToolStatus = "active" | "deprecated" | "experimental" | "internal";

export type ToolCatalog = {
  id: string;
  name: string;
  description: string;
  mcp_server: string;
  side_effects: string[];
  capability_tags: string[];
  cost_estimate: Record<string, unknown> | null;
  status: ToolStatus;
};

// ── tenants ─────────────────────────────────────────────────────────────────

export const backend = {
  listTenants: () => call<Tenant[]>("/admin/tenants").then((r) => r ?? []),

  getTenant: (tenantId: string) =>
    call<Tenant>(`/admin/tenants/${tenantId}`, { optional: true }),

  getAgentConfig: (tenantId: string) =>
    call<AgentConfigBundle>(`/admin/tenants/${tenantId}/agent-config`).then(
      (r) => r ?? { active: null, versions: [] },
    ),

  stageAgentConfig: (
    tenantId: string,
    body: {
      system_prompt_rendered: string;
      channels: Array<Record<string, unknown>>;
      tools: string[];
      policies: Record<string, unknown>;
      seed_template_ref?: string | null;
      kg_schema_id?: string | null;
    },
  ) =>
    call<AgentConfig>(`/admin/tenants/${tenantId}/agent-config`, {
      method: "PUT",
      body,
    }),

  promoteAgentConfig: (tenantId: string, version: number) =>
    call<AgentConfig>(
      `/admin/tenants/${tenantId}/agent-config/${version}/promote`,
      { method: "POST" },
    ),

  rollbackAgentConfig: (tenantId: string, version: number) =>
    call<AgentConfig>(
      `/admin/tenants/${tenantId}/agent-config/${version}/rollback`,
      { method: "POST" },
    ),

  listConversations: (tenantId: string, cursor?: string, limit = 50) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (cursor) qs.set("cursor", cursor);
    return call<ConversationPage>(
      `/admin/tenants/${tenantId}/conversations?${qs.toString()}`,
    ).then((r) => r ?? { items: [], next_cursor: null });
  },

  listToolCatalog: (includeDeprecated = false) =>
    call<ToolCatalog[]>(
      `/admin/tool-catalog?include_deprecated=${includeDeprecated}`,
    ).then((r) => r ?? []),

  bootstrapAgendaPro: (
    tenantId: string,
    body: { login: string; password: string; business_url?: string | null },
  ) =>
    call<{
      integration: string;
      context_id: string;
      bootstrap_at: string;
      screenshot_url: string | null;
      audit_log_id: string;
    }>(`/admin/tenants/${tenantId}/integrations/agendapro/bootstrap`, {
      method: "POST",
      body,
    }),

  healthCheckAgendaPro: (tenantId: string) =>
    call<{
      healthy: boolean;
      relogin_attempted: boolean;
      relogin_succeeded: boolean;
      needs_reauth: boolean;
      checked_at: string;
      notes: string | null;
      new_context_id_persisted: boolean;
    }>(`/admin/tenants/${tenantId}/integrations/agendapro/health-check`, {
      method: "POST",
    }),
};
