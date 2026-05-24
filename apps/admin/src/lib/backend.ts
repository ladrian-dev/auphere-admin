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
  /** ADR-017: public AgendaPro URL used by the new public browser MCP. */
  agendapro_public_url: string | null;
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

/** Mirror of ``MetaSignupOut`` from ``apps/api`` admin endpoint. The
 *  frontend never sees the BISUAT — only post-signup metadata + the
 *  channel row id needed to install the connector row. */
export type MetaSignupResult = {
  status: string;
  channel_id: string;
  waba_id: string;
  phone_number_id: string;
  display_phone_number: string;
  mode: "cloud_api" | "coexistence";
  bisuat_expires_at: string | null;
  audit_log_id: string;
};

export type MetaSignupInput = {
  code: string;
  waba_id: string;
  // phone_number_id and business_id are present in the Cloud API
  // postMessage payload but absent in Coexistence (Meta only sends
  // waba_id in FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING). The backend
  // derives them from GET /{waba_id}/phone_numbers when missing.
  phone_number_id?: string;
  business_id?: string;
  mode: "cloud_api" | "coexistence";
};

export type MetaTestSendInput = {
  to: string;
  kind?: "template" | "text";
  template_name?: string;
  language?: string;
  text_body?: string;
};

export type MetaTestSendResult = {
  status: string;
  wamid: string;
  to: string;
  kind: "template" | "text";
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

export type SkillRef = {
  skill_id: string;
  version: string;
  /** Optional channel-gate. When non-empty, the skill is only injected
   *  on turns where ``state.channel_type`` matches one of these. Empty
   *  / undefined = load on every channel (back-compat with skills
   *  uploaded before the gate landed). */
  channels?: string[] | null;
};

export type McpServerRef = {
  name: string;
  url: string;
  allowed_tools: string[];
  credential_key: string;
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
  // Runtime feature flags (migration 0035). Toggleable per agent_config
  // from the admin agent editor; activation travels with STAGED →
  // ACTIVE promote.
  runtime_memory_tool: boolean;
  runtime_outcome_grader: boolean;
  runtime_mcp_connector: boolean;
  runtime_skills: SkillRef[] | null;
  runtime_mcp_servers: McpServerRef[] | null;
};

export type RuntimeCapabilitiesInput = {
  runtime_memory_tool: boolean;
  runtime_outcome_grader: boolean;
  runtime_mcp_connector: boolean;
  runtime_skills: SkillRef[];
  runtime_mcp_servers: McpServerRef[];
};

export type AvailableSkill = {
  name: string;
  description: string;
  local_version: string;
  /** Null until the skill has been uploaded to the Anthropic workspace
   *  via apps/worker/scripts/upload_skill.py. */
  skill_id: string | null;
  uploaded_version: string | null;
};

/** Block N — modes for the prompt improver. Keep in sync with
 *  ``nexus_api.services.prompt_improver.SUPPORTED_MODES``. */
export type ImprovePromptMode =
  | "general"
  | "specific"
  | "structure"
  | "examples"
  | "shorter"
  | "edge_cases"
  | "english";

export type ImprovePromptOut = {
  improved_prompt: string;
  summary_of_changes: string[];
  mode: ImprovePromptMode;
  meta_prompt_version: string;
  model: string;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
};

/** Block Q — Prompt library + seed metrics. */
export type PromptSnippetCategory =
  | "tone"
  | "edge_case"
  | "escalation"
  | "output_format"
  | "tool_calling"
  | "policy";

export type PromptSnippet = {
  id: string;
  title: string;
  category: PromptSnippetCategory;
  description: string;
  body: string;
  verticals: string[];
  tags: string[];
};

export type SeedTemplateMetrics = {
  name: string;
  tenant_count: number;
  active_count: number;
  eval_pass_rate_avg: string | null;
  eval_pass_rate_count: number;
  last_used_at: string | null;
};

/** Block P — Eval suite types. */
export type EvalDataset = {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  version: number;
  pass_threshold: string;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type EvalCaseAssertions = {
  must_contain?: string[];
  must_not_contain?: string[];
  expected_tools_called?: string[];
  tools_must_not_call?: string[];
  must_emit_text?: boolean;
  judge_questions?: string[];
};

export type EvalCase = {
  id: string;
  dataset_id: string;
  idx: number;
  name: string;
  user_message: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
  assertions: EvalCaseAssertions;
  created_at: string;
  updated_at: string;
};

export type EvalDatasetDetail = EvalDataset & {
  cases: EvalCase[];
};

export type EvalRunStatus =
  | "pending"
  | "running"
  | "passed"
  | "failed"
  | "error";

export type EvalRunResultItem = {
  id: string;
  run_id: string;
  case_id: string;
  case_idx: number;
  case_name: string;
  status: "pass" | "fail" | "error";
  transcript: Record<string, unknown>;
  assertion_results: Array<Record<string, unknown>>;
  latency_ms: number;
  created_at: string;
};

export type EvalRun = {
  id: string;
  tenant_id: string;
  dataset_id: string;
  dataset_version: number;
  agent_config_version: number;
  agent_config_status: string;
  status: EvalRunStatus;
  case_count: number;
  pass_count: number;
  fail_count: number;
  error_count: number;
  pass_rate: string;
  actor: string | null;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
};

export type EvalRunDetail = EvalRun & {
  results: EvalRunResultItem[];
};

/** Block O — Test Agent sandbox. */
export type TestAgentHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export type PlannedToolCall = {
  name: string;
  arguments: Record<string, unknown>;
  tool_call_id: string;
  dry_run_result: string;
  iteration: number;
};

export type TestTurnOut = {
  version_tested: number;
  version_status: "staged" | "active" | "archived";
  assistant_message: string;
  planned_tool_calls: PlannedToolCall[];
  model: string;
  iterations: number;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
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
  agent_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ConversationPage = {
  items: ConversationOut[];
  next_cursor: string | null;
};

export type MessageStatus =
  | "pending"
  | "sent"
  | "delivered"
  | "read"
  | "failed";

export type InteractiveButton = { id: string; title: string };
export type InteractiveListItem = {
  id: string;
  title: string;
  description?: string;
};
export type InteractiveList = {
  button: string;
  items: InteractiveListItem[];
};
export type InteractiveCtaUrl = { text: string; url: string };

/** Mirror of ``response.send_interactive`` payload — the structured
 *  shape the agent emits when calling the terminal interactive tool.
 *  At most one of ``buttons`` / ``list`` / ``cta_url`` is set on a
 *  given row (validated by the backend). */
export type InteractivePayload = {
  body: string;
  header?: string | null;
  footer?: string | null;
  buttons?: InteractiveButton[] | null;
  list?: InteractiveList | null;
  cta_url?: InteractiveCtaUrl | null;
  context_message_id?: string | null;
};

export type OutcomeVerdict = "pass" | "fail" | "skipped" | "error";

export type AuditLogOut = {
  id: string;
  tenant_id: string;
  actor: string;
  action: string;
  target: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  created_at: string;
};

export type AuditLogPage = {
  items: AuditLogOut[];
  next_cursor: string | null;
};

export type MessageOut = {
  // Identity + ordering
  id: string;
  conversation_id: string;
  created_at: string;
  // Core content
  direction: "inbound" | "outbound";
  content: string;
  intent: string | null;
  // LLM telemetry
  cost_usd: number | null;
  latency_ms: number | null;
  model: string | null;
  trace_id: string | null;
  tool_calls: Array<Record<string, unknown>>;
  // Delivery lifecycle
  status: MessageStatus;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
  failure_code: string | null;
  last_error: string | null;
  attempts: number;
  provider_message_id: string | null;
  pricing_category: string | null;
  // Media
  media_kind: string | null;
  media_mime: string | null;
  media_filename: string | null;
  media_size_bytes: number | null;
  media_transcript: string | null;
  // Reactions + quoted reply
  reaction_emoji: string | null;
  reaction_target_wamid: string | null;
  context_message_id: string | null;
  // Interactive component
  interactive_payload: InteractivePayload | null;
  // Outcome grader
  outcome_overall: OutcomeVerdict | null;
  outcome_retries: number | null;
  outcome_feedback: string | null;
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
  // Block L additions (migration 0013) — exposed on the API in M.2.
  connector_id: string | null;
  read_only: boolean;
  destructive: boolean;
  requires_consent: boolean;
};

/**
 * Block M.2 — per-tenant tool catalog. Joins the global tool list with
 * the tenant's connector installs so the editor can disable tools whose
 * connector is not connected and surface a CTA inline.
 */
export type ToolWithInstallStatus = ToolCatalog & {
  connector_slug: string | null;
  connector_display_name: string | null;
  connector_logo_url: string | null;
  tenant_connector_status: TenantConnectorStatus | null;
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
  | "paused"
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

  /** Update the runtime feature flags + skills + MCP servers of a
   *  STAGED agent_config. The backend refuses non-STAGED versions on
   *  purpose: capability changes are versioned through STAGED →
   *  ACTIVE so rollback stays atomic. */
  updateRuntimeCapabilities: (
    tenantId: string,
    version: number,
    body: RuntimeCapabilitiesInput,
  ) =>
    call<AgentConfig>(
      `/admin/tenants/${tenantId}/agent-config/${version}/runtime`,
      { method: "PATCH", body },
    ),

  /** List Anthropic Skills bundled with this deploy + their upload
   *  status. Empty ``skill_id`` means the skill has not been uploaded
   *  yet (apps/worker/scripts/upload_skill.py). */
  listAvailableSkills: () =>
    call<AvailableSkill[]>("/admin/skills/available").then((r) => r ?? []),

  /**
   * Block N — "Mejorar prompt". Sends the operator's draft + chosen
   * mode + optional feedback; receives the improved text + bullet
   * summary of changes for the diff view.
   */
  improveAgentPrompt: (
    tenantId: string,
    body: {
      prompt: string;
      mode?: ImprovePromptMode;
      feedback?: string | null;
    },
  ) =>
    call<ImprovePromptOut>(
      `/admin/tenants/${tenantId}/agent-config/improve-prompt`,
      { method: "POST", body },
    ),

  /**
   * Block O — "Probar agente" sandbox. Runs one turn against the latest
   * staged (or active) version without persisting anything and without
   * dispatching tools.
   */
  testAgentTurn: (
    tenantId: string,
    body: {
      user_message: string;
      history?: TestAgentHistoryMessage[];
      version?: number;
    },
  ) =>
    call<TestTurnOut>(`/admin/tenants/${tenantId}/agent-config/test`, {
      method: "POST",
      body,
    }),

  // ── Block P — Eval suite ─────────────────────────────────────────────────

  listEvalDatasets: (tenantId: string) =>
    call<EvalDataset[]>(`/admin/tenants/${tenantId}/eval-datasets`).then(
      (r) => r ?? [],
    ),

  createEvalDataset: (
    tenantId: string,
    body: {
      name: string;
      description?: string | null;
      pass_threshold?: number | null;
    },
  ) =>
    call<EvalDataset>(`/admin/tenants/${tenantId}/eval-datasets`, {
      method: "POST",
      body,
    }),

  getEvalDataset: (tenantId: string, datasetId: string) =>
    call<EvalDatasetDetail>(
      `/admin/tenants/${tenantId}/eval-datasets/${datasetId}`,
      { optional: true },
    ),

  createEvalCase: (
    tenantId: string,
    datasetId: string,
    body: {
      name: string;
      user_message: string;
      history?: Array<{ role: "user" | "assistant"; content: string }>;
      assertions: EvalCaseAssertions;
      idx?: number;
    },
  ) =>
    call<EvalCase>(
      `/admin/tenants/${tenantId}/eval-datasets/${datasetId}/cases`,
      { method: "POST", body },
    ),

  deleteEvalCase: (tenantId: string, caseId: string) =>
    call<null>(`/admin/tenants/${tenantId}/eval-cases/${caseId}`, {
      method: "DELETE",
    }),

  triggerEvalRun: (
    tenantId: string,
    datasetId: string,
    body: { agent_config_version?: number },
  ) =>
    call<EvalRunDetail>(
      `/admin/tenants/${tenantId}/eval-datasets/${datasetId}/run`,
      { method: "POST", body },
    ),

  listEvalRuns: (
    tenantId: string,
    opts: { agent_config_version?: number; limit?: number } = {},
  ) => {
    const qs = new URLSearchParams();
    if (opts.agent_config_version !== undefined) {
      qs.set("agent_config_version", String(opts.agent_config_version));
    }
    if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return call<EvalRun[]>(`/admin/tenants/${tenantId}/eval-runs${suffix}`).then(
      (r) => r ?? [],
    );
  },

  // ── Block Q — Prompt library + seed metrics ──────────────────────────────

  listPromptLibrary: (opts: { vertical?: string; category?: string } = {}) => {
    const qs = new URLSearchParams();
    if (opts.vertical) qs.set("vertical", opts.vertical);
    if (opts.category) qs.set("category", opts.category);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return call<PromptSnippet[]>(`/admin/prompt-library${suffix}`).then(
      (r) => r ?? [],
    );
  },

  getSeedTemplateMetrics: (name: string) =>
    call<SeedTemplateMetrics>(`/admin/seed-templates/${name}/metrics`, {
      optional: true,
    }),

  /**
   * Block M.3 — toggle per-conversation agent control. ``agent_active=false``
   * puts the operator in the loop: inbound messages are persisted but the
   * pipeline is skipped until the operator flips it back to ``true``.
   */
  toggleConversationAgent: (
    tenantId: string,
    conversationId: string,
    agentActive: boolean,
  ) =>
    call<ConversationOut>(
      `/admin/tenants/${tenantId}/conversations/${conversationId}/agent`,
      { method: "PATCH", body: { agent_active: agentActive } },
    ),

  getConversation: (tenantId: string, conversationId: string) =>
    call<ConversationOut>(
      `/admin/tenants/${tenantId}/conversations/${conversationId}`,
      { optional: true },
    ),

  listConversationMessages: (tenantId: string, conversationId: string) =>
    call<MessageOut[]>(
      `/admin/tenants/${tenantId}/conversations/${conversationId}/messages`,
    ).then((r) => r ?? []),

  listConversations: (tenantId: string, cursor?: string, limit = 50) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (cursor) qs.set("cursor", cursor);
    return call<ConversationPage>(
      `/admin/tenants/${tenantId}/conversations?${qs.toString()}`,
    ).then((r) => r ?? { items: [], next_cursor: null });
  },

  listAuditLog: (
    tenantId: string,
    filters: {
      cursor?: string;
      limit?: number;
      actor?: string;
      action?: string;
      action_prefix?: string;
      target?: string;
      after?: string;
      before?: string;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    qs.set("limit", String(filters.limit ?? 50));
    for (const k of ["cursor", "actor", "action", "action_prefix", "target", "after", "before"] as const) {
      const v = filters[k];
      if (v !== undefined && v !== "") qs.set(k, v);
    }
    return call<AuditLogPage>(
      `/admin/tenants/${tenantId}/audit-log?${qs.toString()}`,
    ).then((r) => r ?? { items: [], next_cursor: null });
  },

  listAuditActions: (tenantId: string) =>
    call<string[]>(
      `/admin/tenants/${tenantId}/audit-log/actions`,
    ).then((r) => r ?? []),

  listToolCatalog: (includeDeprecated = false) =>
    call<ToolCatalog[]>(
      `/admin/tool-catalog?include_deprecated=${includeDeprecated}`,
    ).then((r) => r ?? []),

  /**
   * Tenant-scoped variant — each tool comes annotated with the connector
   * binding and the tenant's install status. Block M.2 endpoint.
   */
  listTenantToolCatalog: (tenantId: string, includeDeprecated = false) =>
    call<ToolWithInstallStatus[]>(
      `/admin/tenants/${tenantId}/tool-catalog?include_deprecated=${includeDeprecated}`,
    ).then((r) => r ?? []),

  // AgendaPro public link (ADR-017). The legacy bootstrap + health-check
  // endpoints were removed in migration 0021 — the agent now consumes
  // AgendaPro only via the tenant's public booking URL.
  setAgendaProPublicUrl: (tenantId: string, publicUrl: string | null) =>
    call<{
      integration: string;
      public_url: string | null;
      updated_at: string;
      audit_log_id: string;
    }>(`/admin/tenants/${tenantId}/integrations/agendapro/public-url`, {
      method: "PATCH",
      body: { public_url: publicUrl },
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

  deleteTenant: (tenantId: string) =>
    call<null>(`/admin/tenants/${tenantId}`, { method: "DELETE" }),

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

  /** Complete an Embedded Signup v4 flow for a tenant. The browser already
   *  ran ``FB.login`` and captured ``code`` + ``data``; this call hands them
   *  off to the orchestrator which does the exchange + register + subscribe
   *  dance on the server. */
  metaSignup: (tenantId: string, body: MetaSignupInput) =>
    call<MetaSignupResult>(
      `/admin/tenants/${tenantId}/integrations/meta/signup`,
      { method: "POST", body },
    ),

  /** Send a one-off test message from the tenant's connected Meta
   *  WhatsApp channel — defaults to the always-approved hello_world
   *  template so it works outside the 24h service window. Used by the
   *  "Enviar prueba" button in the connector card to smoke-test the
   *  BISUAT and to exercise whatsapp_business_messaging for App Review. */
  metaTestSend: (tenantId: string, body: MetaTestSendInput) =>
    call<MetaTestSendResult>(
      `/admin/tenants/${tenantId}/integrations/meta/test-send`,
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

  connectManualConnector: (
    tenantId: string,
    slug: string,
    body: { channel_id: string },
  ) =>
    call<TenantConnector>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/connect-manual`,
      { method: "POST", body },
    ),

  connectApiKeyConnector: (
    tenantId: string,
    slug: string,
    body: { secrets: Record<string, string>; endpoint_meta: Record<string, unknown> },
  ) =>
    call<TenantConnector>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/connect-api-key`,
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

  pauseConnector: (tenantId: string, slug: string) =>
    call<TenantConnector>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/pause`,
      { method: "POST", body: {} },
    ),

  resumeConnector: (tenantId: string, slug: string) =>
    call<TenantConnector>(
      `/admin/tenants/${tenantId}/connectors/${encodeURIComponent(slug)}/resume`,
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
