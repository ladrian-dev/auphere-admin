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
  cost_alert_threshold_usd_per_day: string;
  created_at: string;
  updated_at: string;
};

export type TenantCreateInput = {
  slug: string;
  name: string;
  plan: TenantPlan;
  market?: string | null;
  timezone?: string;
  owner_email?: string | null;
  owner_phone?: string | null;
  business_hours?: Record<string, unknown> | null;
  cost_alert_threshold_usd_per_day?: number;
};

export type TenantUpdateInput = Partial<{
  name: string;
  plan: TenantPlan;
  status: TenantStatus;
  market: string | null;
  timezone: string;
  owner_email: string | null;
  owner_phone: string | null;
  business_hours: Record<string, unknown> | null;
  cost_alert_threshold_usd_per_day: number;
}>;

export type SlugAvailability = {
  slug: string;
  available: boolean;
};

export type WhatsAppPreview = {
  phone_number: string;
  phone_number_id: string;
  waba_id: string;
  display_name: string | null;
  verified_name: string | null;
  quality_rating: string | null;
};

export type WhatsAppConnect = WhatsAppPreview & {
  status: string;
  channel_id: string;
  audit_log_id: string;
};

export type SeedTemplate = {
  name: string;
  version: string;
  display_name: string;
  tools_required: string[];
  policies_default: Record<string, unknown>;
};

export type ChannelOut = {
  id: string;
  type: "whatsapp" | "instagram" | "telegram" | "email" | "web";
  provider: string;
  provider_identifier: string;
  config: Record<string, unknown>;
  status: "active" | "paused" | "degraded" | "disconnected";
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

export type IsolationMetric = {
  metric: string;
  count_24h: number;
  last_breach_at: string | null;
  persisted: boolean;
};

export type IsolationMetricsOut = {
  tenant_id: string;
  window_hours: number;
  generated_at: string;
  metrics: IsolationMetric[];
};

// ── connectors (Block L) ────────────────────────────────────────────────────

export type ConnectorAuthKind =
  | "oauth_composio"
  | "browser_credentials"
  | "webhook_manual"
  | "api_key";

export type ConnectorCatalogStatus = "available" | "beta" | "deprecated";

export type Connector = {
  id: string;
  slug: string;
  display_name: string;
  vendor: string;
  category: string;
  capabilities: string[];
  auth_kind: ConnectorAuthKind;
  mcp_server_ref: string;
  provider_meta: Record<string, unknown>;
  auto_enable_on_connect: boolean;
  auto_enable_destructive: boolean;
  consent_link_template_name: string | null;
  status: ConnectorCatalogStatus;
};

export type TenantConnectorStatus =
  | "pending"
  | "connected"
  | "partial"
  | "needs_reauth"
  | "disconnected"
  | "error";

export type TenantConnector = {
  id: string;
  tenant_id: string;
  connector_id: string;
  connector_slug: string;
  connector_display_name: string;
  connector_auth_kind: ConnectorAuthKind;
  connector_category: string;
  status: TenantConnectorStatus;
  credentials_ref: Record<string, unknown>;
  scopes_granted: string[];
  config: Record<string, unknown>;
  last_health_check_at: string | null;
  last_synced_at: string | null;
  connected_at: string | null;
  disconnected_at: string | null;
  consent_token_expires_at: string | null;
};

export type InitiateConsentOut = {
  tenant_connector_id: string;
  redirect_url: string;
  consent_link_template_name: string;
  expires_at: string;
  signed_consent_url: string;
};

export type ConnectorToolMode = "always" | "blocked" | "needs_approval";

export type ConnectorToolOverride = {
  tenant_id: string;
  tool_name: string;
  mode: ConnectorToolMode;
  reason: string | null;
  set_by_actor: string;
  updated_at: string;
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

  getIsolationMetrics: (tenantId: string) =>
    call<IsolationMetricsOut>(
      `/admin/tenants/${tenantId}/isolation/metrics`,
    ),

  // ── Block J: onboarding wizard ──────────────────────────────────────────

  checkSlugAvailability: (slug: string) =>
    call<SlugAvailability>(
      `/admin/tenants/check-slug?slug=${encodeURIComponent(slug)}`,
    ),

  createTenant: (body: TenantCreateInput) =>
    call<Tenant>("/admin/tenants", { method: "POST", body }),

  updateTenant: (tenantId: string, body: TenantUpdateInput) =>
    call<Tenant>(`/admin/tenants/${tenantId}`, { method: "PUT", body }),

  verifyWhatsApp: (waba_id: string, phone_number_id: string) =>
    call<WhatsAppPreview>(
      `/admin/integrations/whatsapp/verify?waba_id=${encodeURIComponent(
        waba_id,
      )}&phone_number_id=${encodeURIComponent(phone_number_id)}`,
    ),

  connectWhatsAppManual: (
    tenantId: string,
    body: { waba_id: string; phone_number_id: string },
  ) =>
    call<WhatsAppConnect>(
      `/admin/tenants/${tenantId}/integrations/whatsapp/connect-manual`,
      { method: "POST", body },
    ),

  listSeedTemplates: () =>
    call<SeedTemplate[]>("/admin/seed-templates").then((r) => r ?? []),

  applyAgentConfigSeed: (
    tenantId: string,
    body: { seed_template_ref: string; placeholders: Record<string, unknown> },
  ) =>
    call<AgentConfig>(
      `/admin/tenants/${tenantId}/agent-config/from-seed`,
      { method: "POST", body },
    ),

  listChannels: (tenantId: string) =>
    call<ChannelOut[]>(`/admin/tenants/${tenantId}/channels`).then(
      (r) => r ?? [],
    ),

  // ── Connectors (Block L / ADR-011) ─────────────────────────────────────

  listConnectors: (params: { category?: string; status?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.category) q.set("category", params.category);
    if (params.status) q.set("status_filter", params.status);
    const qs = q.toString();
    return call<Connector[]>(
      `/admin/connectors${qs ? "?" + qs : ""}`,
    ).then((r) => r ?? []);
  },

  getConnector: (slug: string) =>
    call<Connector>(`/admin/connectors/${encodeURIComponent(slug)}`, {
      optional: true,
    }),

  listTenantConnectors: (tenantId: string) =>
    call<TenantConnector[]>(
      `/admin/tenants/${tenantId}/connectors`,
    ).then((r) => r ?? []),

  initiateConnectorConsent: (tenantId: string, slug: string) =>
    call<InitiateConsentOut>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/initiate-consent`,
      { method: "POST", body: {} },
    ),

  bootstrapBrowserConnector: (
    tenantId: string,
    slug: string,
    body: { tenant_credentials_id: string; context_id?: string | null },
  ) =>
    call<TenantConnector>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/bootstrap-browser`,
      { method: "POST", body },
    ),

  connectManualConnector: (
    tenantId: string,
    slug: string,
    body: { channel_id: string },
  ) =>
    call<TenantConnector>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/connect-manual`,
      { method: "POST", body },
    ),

  syncConnector: (tenantId: string, slug: string) =>
    call<{ added: string[]; deprecated: string[]; unchanged_count: number }>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/sync`,
      { method: "POST", body: {} },
    ),

  disconnectConnector: (tenantId: string, slug: string) =>
    call<TenantConnector>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/disconnect`,
      { method: "POST", body: {} },
    ),

  reissueConnectorConsent: (tenantId: string, slug: string) =>
    call<InitiateConsentOut>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/reissue-consent`,
      { method: "POST", body: {} },
    ),

  listConnectorToolOverrides: (tenantId: string) =>
    call<ConnectorToolOverride[]>(
      `/admin/tenants/${tenantId}/connector-tool-overrides`,
    ).then((r) => r ?? []),

  putConnectorToolOverride: (
    tenantId: string,
    toolName: string,
    body: { mode: ConnectorToolMode; reason?: string | null },
  ) =>
    call<ConnectorToolOverride>(
      `/admin/tenants/${tenantId}/connector-tool-overrides/${encodeURIComponent(toolName)}`,
      { method: "PUT", body },
    ),

  deleteConnectorToolOverride: (tenantId: string, toolName: string) =>
    call<null>(
      `/admin/tenants/${tenantId}/connector-tool-overrides/${encodeURIComponent(toolName)}`,
      { method: "DELETE" },
    ),
};
