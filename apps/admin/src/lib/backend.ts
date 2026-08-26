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

import type { ChannelRole } from "@/lib/channels";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8000";
const ADMIN_TOKEN = process.env.NEXUS_ADMIN_TOKEN ?? "dev-admin-token-change-me";
const CONSOLE_URL = (process.env.NEXUS_CONSOLE_URL ?? "http://localhost:3110").replace(
  /\/$/,
  "",
);

/** Deep-link into the partner console. Operator does not enter with a partner session. */
export function consoleHref(path: string): string {
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${CONSOLE_URL}${suffix}`;
}

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
  /** Extra headers (e.g. ``If-Match`` for the optimistic-lock CAS on
   *  PATCH .../conversations/:id/agent). */
  headers?: Record<string, string>;
};

async function call<T>(path: string, opts: FetchOpts = {}): Promise<T | null> {
  const url = `${BACKEND_URL}${path}`;
  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: {
      Authorization: `Bearer ${ADMIN_TOKEN}`,
      Accept: "application/json",
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(opts.headers ?? {}),
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

export type ReadinessStatus = "ok" | "warning" | "blocker";

export type ReadinessItem = {
  key: string;
  label: string;
  status: ReadinessStatus;
  detail: string;
  action_label: string | null;
  action_href: string | null;
};

export type ReadinessOut = {
  /** true iff no item has status "blocker". */
  ready: boolean;
  items: ReadinessItem[];
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
  catalog_id?: string | null;
};

/** TikTok authorisation is a redirect, not a popup SDK: the backend mints a
 *  URL and the browser leaves the panel. There is no "signup result" to
 *  render inline — the channel appears once TikTok bounces the owner back to
 *  the API callback, which redirects here with ``?tiktok=<status>``. */
export type TikTokAuthorizeUrlResult = {
  authorize_url: string;
};

export type TikTokDisconnectResult = {
  status: string;
  audit_log_id: string;
};

export type MetaConnectOwnedInput = {
  system_user_token: string;
  waba_id: string;
  phone_number_id?: string;
  business_id?: string;
  catalog_id?: string;
  attempt_register?: boolean;
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

export type WhatsAppTemplate = {
  id: string | null;
  name: string;
  language: string;
  category: string | null;
  status: string | null;
  quality_score: string | null;
  components: Array<Record<string, unknown>>;
};

export type WhatsAppTemplateList = {
  templates: WhatsAppTemplate[];
  waba_id: string;
};

export type WhatsAppTemplateCreateInput = {
  name: string;
  language?: string;
  category?: string;
  components: Array<Record<string, unknown>>;
};

export type WhatsAppTemplateCreateResult = {
  id: string | null;
  name: string;
  status: string | null;
  category: string | null;
  audit_log_id: string;
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
  type: "whatsapp" | "instagram" | "telegram" | "email" | "web" | "tiktok";
  provider: string;
  provider_identifier: string;
  /**
   * Meta identifiers written at connect time, plus the two operator-editable
   * flags: `role` and `agent_enabled`. Read them through `channelRole()` /
   * `channelAgentEnabled()` so the defaults stay in one place — an absent
   * flag means "behave as before roles existed", not "false".
   */
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

export type TakeoverContext = {
  reason: string | null;
  notes: string | null;
  started_at: string | null;
  operator_id: string | null;
};

export type ConversationOut = {
  id: string;
  channel_id: string;
  customer_id: string;
  status: "open" | "closed" | "escalated";
  agent_active: boolean;
  /** Bloque C — optimistic-locking counter on ``agent_active``.
   *  Sent back on PATCH via ``If-Match`` to detect two operators
   *  racing on the same conversation. */
  agent_active_version: number;
  /** Bloque C — operator-authored briefing captured when the agent
   *  is paused; consumed by the dispatcher on the first turn after
   *  resume and cleared. Populated only while the conversation is
   *  in a takeover window. */
  takeover_context: TakeoverContext | null;
  /** Transport provider of the conversation's channel ("meta").
   *  Lets the panel badge each thread. Null only
   *  when the underlying channel row is missing. */
  provider: string | null;
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

// ── auphere_owner_channels (Bloque D Fase 2) ──────────────────────────

export type AuphereChannelProvider = "meta";

export type AuphereOwnerChannelOut = {
  id: string;
  phone_e164: string;
  display_name: string;
  country_code: string | null;
  provider: AuphereChannelProvider;
  provider_phone_id: string | null;
  active: boolean;
  is_default: boolean;
  has_webhook_secret: boolean;
  has_access_token: boolean;
  created_at: string;
  updated_at: string;
};

export type AuphereChannelCreateInput = {
  phone_e164: string;
  display_name: string;
  country_code?: string | null;
  provider?: AuphereChannelProvider;
  provider_phone_id?: string | null;
  is_default?: boolean;
  webhook_secret?: string | null;
  access_token?: string | null;
};

export type AuphereChannelUpdateInput = {
  display_name?: string;
  country_code?: string | null;
  provider_phone_id?: string | null;
  active?: boolean;
  is_default?: boolean;
  webhook_secret?: string | null;
  access_token?: string | null;
};

// ── owner_phone_index (per tenant) ────────────────────────────────────

export type OwnerPhoneIndexOut = {
  phone_e164: string;
  tenant_id: string;
  user_label: string | null;
  active: boolean;
  added_at: string;
  auphere_channel_id: string | null;
  /** Phase 2 TOFU — NULL until the owner sends ``/yes`` on the
   *  registered phone. The panel surfaces "pendiente de confirmación"
   *  for rows where this is still NULL. */
  confirmed_at: string | null;
};

export type BackchannelOwnerCreateInput = {
  phone_e164: string;
  user_label?: string | null;
  auphere_channel_id?: string | null;
};

export type BackchannelOwnerUpdateInput = {
  user_label?: string | null;
  active?: boolean;
  auphere_channel_id?: string | null;
  clear_channel_id?: boolean;
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
  // Actor identity (Bloque C). NULL on inbound rows and on outbound
  // rows written before migration 0041 (back-compat).
  actor_kind: "agent" | "operator" | "owner" | "system" | null;
  actor_id: string | null;
};

/** Bloque C — body for the operator-side send endpoint. */
export type OperatorSendInput = { content: string };

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

// ── partners (ADR-028 — embed widget platform) ──────────────────────────────

export type PartnerStatus = "active" | "suspended";

export type PartnerOut = {
  id: string;
  name: string;
  slug: string;
  status: PartnerStatus;
  contact_email: string | null;
  billing_email: string | null;
  broadcast_recipient_cap: number;
  rate_limit_mint_per_min: number;
  rate_limit_embed_per_min: number;
  default_seed_template: string | null;
  default_connector_slug: string | null;
  auto_activate: boolean;
  created_at: string;
  updated_at: string;
};

export type PartnerCreateInput = {
  name: string;
  slug: string;
  contact_email?: string | null;
};

export type PartnerUpdateInput = Partial<{
  name: string;
  status: PartnerStatus;
  contact_email: string | null;
  broadcast_recipient_cap: number;
  rate_limit_mint_per_min: number;
  rate_limit_embed_per_min: number;
  // Blueprint (Fase 2b) — "" limpia el campo en el backend.
  default_seed_template: string;
  default_connector_slug: string;
  auto_activate: boolean;
}>;

export type PartnerClientUsage = {
  external_client_ref: string;
  client_name: string | null;
  tenant_id: string;
  tenant_status: string;
  whatsapp_connected: boolean;
  agent_version: number | null;
  agent_seed_template: string | null;
  broadcasts: number;
  broadcast_recipients: number;
  messages_inbound: number;
  messages_outbound: number;
  cost_usd: number;
};

export type PartnerWalletOut = {
  included_remaining: number;
  purchased_remaining: number;
  available: number;
  reserve: number;
  included_expires_at: string | null;
  exhausted: boolean;
};

export type PartnerLedgerOut = {
  id: string;
  bucket: string;
  qty: number;
  reason: string;
  created_at: string;
};

export type PartnerModelItemOut = {
  model_id: string;
  display_name: string;
  allowed: boolean;
};

export type PartnerModelsOut = {
  items: PartnerModelItemOut[];
};

export type PartnerLlmOut = {
  blocked: boolean;
};

export type TicketStatus = "open" | "pending" | "closed";

export type AdminTicketOut = {
  id: string;
  ticket_ref: string;
  partner_id: string;
  partner_name: string;
  partner_slug: string;
  category: string;
  topic: string;
  sla: string;
  status: TicketStatus;
  client_ref: string | null;
  need: string;
  checked: string[];
  alternative: string | null;
  bridge: boolean;
  opened_by: string;
  created_at?: string;
  opened_at: string;
  updated_at: string;
};

export type AdminTicketEventOut = {
  id: string;
  kind: string;
  from_status: string | null;
  to_status: string;
  actor: string;
  created_at: string;
};

export type AdminTicketDetailOut = AdminTicketOut & {
  events: AdminTicketEventOut[];
  links: {
    consumo: string;
    modelos: string;
    conocimiento: string;
  };
};

export type KnowledgeKind = "file" | "url";
export type KnowledgeStatus = "pending" | "indexed" | "failed";
export type KnowledgeErrorCode =
  | "fetch_failed"
  | "unsupported_type"
  | "too_large"
  | "empty";

/** Mirror of console ``KnowledgeDocumentOut``. Never ``content_text``. */
export type KnowledgeDocumentOut = {
  id: string;
  kind: KnowledgeKind;
  title: string;
  source_url: string | null;
  mime: string;
  size_bytes: number;
  status: KnowledgeStatus;
  error_code: KnowledgeErrorCode | null;
  chunk_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  indexed_at: string | null;
};

/** Mirror of console ``KnowledgeListOut``. */
export type KnowledgeListOut = {
  items: KnowledgeDocumentOut[];
  total: number;
  indexed_chars: number;
  prompt_char_cap: number;
};

export type WorkflowCronOut = {
  hour: number;
  minute: number;
  timezone: string;
};

/** Mirror of console ``WorkflowPackOut``. */
export type WorkflowPackOut = {
  client_ref: string;
  is_set: boolean;
  version: number | null;
  trigger: "cron" | "event" | null;
  steps: string[];
  template_id: string | null;
  cron: WorkflowCronOut | null;
  enabled: boolean | null;
  end_time: string | null;
  stop: string | null;
};

export type WorkflowRunOut = {
  thread_id: string;
  status: string;
};

/** Mirror of console ``WorkflowRunsOut``. */
export type WorkflowRunsOut = {
  items: WorkflowRunOut[];
};

export type PartnerUsageOut = {
  partner_id: string;
  window_days: number;
  clients_total: number;
  clients_active: number;
  clients_whatsapp_connected: number;
  clients_with_agent: number;
  broadcasts: number;
  broadcast_recipients: number;
  messages_inbound: number;
  messages_outbound: number;
  cost_usd: number;
  clients: PartnerClientUsage[];
};

export type PartnerApiKeyType = "live" | "test";

export type PartnerApiKeyOut = {
  id: string;
  type: PartnerApiKeyType;
  prefix_snippet: string;
  scopes: string[];
  allowed_origins: string[];
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  grace_expires_at: string | null;
};

/** Returned ONLY on key creation / rotation. ``plaintext`` is the single
 *  time the secret exists outside the partner's own storage — the panel
 *  shows it once in an un-dismissable dialog and never persists it. */
export type PartnerApiKeyCreatedOut = PartnerApiKeyOut & {
  plaintext: string;
};

export type PartnerApiKeyCreateInput = {
  type?: PartnerApiKeyType;
  scopes?: string[];
  allowed_origins?: string[];
  expires_at?: string | null;
};

export type PartnerTenantOut = {
  partner_id: string;
  external_client_ref: string;
  tenant_id: string;
  client_name: string | null;
  created_at: string;
};

export type PartnerTenantLinkInput = {
  external_client_ref: string;
  tenant_id: string;
  client_name?: string | null;
};

export type EmbedAuditEntryOut = {
  id: number;
  partner_id: string | null;
  api_key_id: string | null;
  tenant_id: string | null;
  event: string;
  payload: Record<string, unknown>;
  ip: string | null;
  origin: string | null;
  jti: string | null;
  created_at: string;
};

export type ReceiptSummaryOut = {
  invoice_id: string;
  period_year: number;
  period_month: number;
  total_usd: number;
  currency: string;
  status: string;
  issued_at: string | null;
  due_date: string;
};

export type ReceiptLineOut = {
  tenant_id: string;
  tenant_slug: string;
  tenant_name: string;
  model: string;
  description: string;
  amount_usd: number;
  commission_clp: number | null;
};

export type ReceiptOut = {
  invoice_id: string;
  partner_id: string;
  partner_slug: string;
  partner_name: string;
  billing_email: string | null;
  period_year: number;
  period_month: number;
  total_usd: number;
  currency: string;
  status: string;
  clp_per_usd: number | null;
  issued_at: string | null;
  due_date: string;
  created: boolean;
  lines: ReceiptLineOut[];
};

export type ReceiptGenerateInput = {
  period_year: number;
  period_month: number;
  send_email?: boolean;
};

export type ReceiptSendOut = {
  invoice_id: string;
  emailed: boolean;
  to: string | null;
};

export type BillingPlanOut = {
  id: string;
  code: string;
  name: string;
  monthly_amount_cents: number;
  active: boolean;
};

export type BillingPlanCreateInput = {
  code: string;
  name: string;
  monthly_amount_cents: number;
};

export type TenantBillingOut = {
  tenant_id: string;
  tenant_name: string;
  partner_id: string | null;
  partner_name: string | null;
  billing_plan_id: string | null;
  plan_name: string | null;
  plan_amount_cents: number | null;
  price_override_cents: number | null;
  billing_effective_from: string | null;
  effective_monthly_cents: number | null;
  model: string;
};

export type TenantBillingUpdateInput = {
  partner_id?: string | null;
  billing_plan_id?: string | null;
  price_override_cents?: number | null;
  billing_effective_from?: string | null;
};

// ── tenants ─────────────────────────────────────────────────────────────────

export const backend = {
  listTenants: () => call<Tenant[]>("/admin/tenants").then((r) => r ?? []),

  getTenant: (tenantId: string) =>
    call<Tenant>(`/admin/tenants/${tenantId}`, { optional: true }),

  getReadiness: (tenantId: string) =>
    call<ReadinessOut>(`/admin/tenants/${tenantId}/readiness`),

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

  getEvalRun: (tenantId: string, runId: string) =>
    call<EvalRunDetail>(`/admin/tenants/${tenantId}/eval-runs/${runId}`),

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
   * Block M.3 + Bloque C — toggle per-conversation agent control with
   * optimistic locking and optional operator briefing.
   *
   * ``agentActive=false`` puts the operator in the loop: inbound messages
   * are persisted but the pipeline is skipped until the operator flips
   * back to ``true``. The ``reason`` and ``notes`` (used only on pause)
   * land in ``conversations.takeover_context`` and the dispatcher uses
   * them on the first turn after resume to brief the LLM about the
   * intervention.
   *
   * ``expectedVersion`` (Bloque C) is the ``agent_active_version`` the
   * client last saw. The backend rejects the PATCH with 412 when the
   * counter has moved, preventing two operators from clobbering each
   * other's intent. Omit on first call after a hard reload.
   */
  toggleConversationAgent: (
    tenantId: string,
    conversationId: string,
    agentActive: boolean,
    opts?: {
      reason?: string | null;
      notes?: string | null;
      expectedVersion?: number;
    },
  ) =>
    call<ConversationOut>(
      `/admin/tenants/${tenantId}/conversations/${conversationId}/agent`,
      {
        method: "PATCH",
        body: {
          agent_active: agentActive,
          reason: opts?.reason ?? null,
          notes: opts?.notes ?? null,
        },
        headers:
          opts?.expectedVersion !== undefined
            ? { "If-Match": String(opts.expectedVersion) }
            : undefined,
      },
    ),

  /**
   * Bloque C — operator sends a free-form text reply on a paused
   * conversation. The endpoint refuses with 409 when ``agent_active``
   * is still true; pause before calling.
   */
  operatorSendMessage: (
    tenantId: string,
    conversationId: string,
    content: string,
  ) =>
    call<MessageOut>(
      `/admin/tenants/${tenantId}/conversations/${conversationId}/send`,
      { method: "POST", body: { content } },
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

  // ── Auphere channels (global registry) ─────────────────────────────

  listAuphereChannels: (includeInactive = false) =>
    call<AuphereOwnerChannelOut[]>(
      `/admin/auphere/channels?include_inactive=${includeInactive}`,
    ).then((r) => r ?? []),

  getAuphereChannel: (id: string) =>
    call<AuphereOwnerChannelOut>(
      `/admin/auphere/channels/${id}`,
      { optional: true },
    ),

  createAuphereChannel: (body: AuphereChannelCreateInput) =>
    call<AuphereOwnerChannelOut>(
      "/admin/auphere/channels",
      { method: "POST", body },
    ),

  updateAuphereChannel: (id: string, body: AuphereChannelUpdateInput) =>
    call<AuphereOwnerChannelOut>(
      `/admin/auphere/channels/${id}`,
      { method: "PATCH", body },
    ),

  deactivateAuphereChannel: (id: string) =>
    call<AuphereOwnerChannelOut>(
      `/admin/auphere/channels/${id}`,
      { method: "DELETE" },
    ),

  // ── Backchannel owners (per tenant) ────────────────────────────────

  listBackchannelOwners: (tenantId: string) =>
    call<OwnerPhoneIndexOut[]>(
      `/admin/tenants/${tenantId}/backchannel/owners`,
    ).then((r) => r ?? []),

  registerBackchannelOwner: (
    tenantId: string,
    body: BackchannelOwnerCreateInput,
  ) =>
    call<OwnerPhoneIndexOut>(
      `/admin/tenants/${tenantId}/backchannel/owners`,
      { method: "POST", body },
    ),

  updateBackchannelOwner: (
    tenantId: string,
    phoneE164: string,
    body: BackchannelOwnerUpdateInput,
  ) =>
    call<OwnerPhoneIndexOut>(
      `/admin/tenants/${tenantId}/backchannel/owners/${encodeURIComponent(phoneE164)}`,
      { method: "PATCH", body },
    ),

  deregisterBackchannelOwner: (tenantId: string, phoneE164: string) =>
    call<null>(
      `/admin/tenants/${tenantId}/backchannel/owners/${encodeURIComponent(phoneE164)}`,
      { method: "DELETE" },
    ),

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

  /** Complete an Embedded Signup v4 flow for a tenant. The browser already
   *  ran ``FB.login`` and captured ``code`` + ``data``; this call hands them
   *  off to the orchestrator which does the exchange + register + subscribe
   *  dance on the server. */
  metaSignup: (tenantId: string, body: MetaSignupInput) =>
    call<MetaSignupResult>(
      `/admin/tenants/${tenantId}/integrations/meta/signup`,
      { method: "POST", body },
    ),

  /** Connect a WhatsApp number the app OWNER already controls (a number
   *  under the portfolio that owns the Auphere app), via a permanent
   *  System User token — Embedded Signup refuses that portfolio. The
   *  operator supplies the token + WABA/phone/catalog ids. */
  metaConnectOwned: (tenantId: string, body: MetaConnectOwnedInput) =>
    call<MetaSignupResult>(
      `/admin/tenants/${tenantId}/integrations/meta/connect-owned`,
      { method: "POST", body },
    ),

  /** Mint the URL the business owner opens to authorise the Auphere TikTok
   *  app over their Business Account. The URL carries a signed, tenant-bound
   *  ``state``; TikTok redirects the browser straight back to the API
   *  callback, so — unlike Meta's Embedded Signup — the panel never handles
   *  the auth_code itself. */
  tiktokAuthorizeUrl: (tenantId: string) =>
    call<TikTokAuthorizeUrlResult>(
      `/admin/tenants/${tenantId}/integrations/tiktok/authorize-url`,
      { method: "POST" },
    ),

  /** Offboard the tenant from TikTok: delete the webhook registration,
   *  drop the credentials, mark the channel disconnected. */
  tiktokDisconnect: (tenantId: string) =>
    call<TikTokDisconnectResult>(
      `/admin/tenants/${tenantId}/integrations/tiktok`,
      { method: "DELETE" },
    ),

  /** Send a one-off test message from the tenant's connected Meta
   *  WhatsApp channel — defaults to the always-approved hello_world
   *  template so it works outside the 24h service window. Used by the
   *  "Enviar prueba" button in the connector card to smoke-test the
   *  BISUAT and to exercise whatsapp_business_messaging for App Review. */
  listWhatsAppTemplates: (tenantId: string) =>
    call<WhatsAppTemplateList>(
      `/admin/tenants/${tenantId}/whatsapp/templates`,
    ),

  createWhatsAppTemplate: (
    tenantId: string,
    body: WhatsAppTemplateCreateInput,
  ) =>
    call<WhatsAppTemplateCreateResult>(
      `/admin/tenants/${tenantId}/whatsapp/templates`,
      { method: "POST", body },
    ),

  deleteWhatsAppTemplate: (tenantId: string, name: string) =>
    call<{ name: string; deleted: boolean }>(
      `/admin/tenants/${tenantId}/whatsapp/templates/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),

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

  /**
   * Assign what a WhatsApp number is for.
   *
   * `role` decides which line business-initiated sends (broadcasts, cobranza
   * reminders, the template API) leave from. `agent_enabled: false` makes the
   * line send-only: inbound is still stored and visible, but nothing answers
   * and no read receipt goes out.
   *
   * Omitted fields are left untouched; `role: null` clears the assignment.
   */
  updateChannelRole: (
    tenantId: string,
    channelId: string,
    body: { role?: ChannelRole | null; agent_enabled?: boolean },
  ) =>
    call<ChannelOut>(`/admin/tenants/${tenantId}/channels/${channelId}`, {
      method: "PATCH",
      body,
    }),

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

  // ── Partners (ADR-028 — embed widget platform) ─────────────────────────

  listPartners: () =>
    call<PartnerOut[]>("/admin/partners").then((r) => r ?? []),

  getPartner: (partnerId: string) =>
    call<PartnerOut>(`/admin/partners/${partnerId}`, { optional: true }),

  createPartner: (body: PartnerCreateInput) =>
    call<PartnerOut>("/admin/partners", { method: "POST", body }),

  updatePartner: (partnerId: string, body: PartnerUpdateInput) =>
    call<PartnerOut>(`/admin/partners/${partnerId}`, {
      method: "PATCH",
      body,
    }),

  listPartnerKeys: (partnerId: string) =>
    call<PartnerApiKeyOut[]>(`/admin/partners/${partnerId}/keys`).then(
      (r) => r ?? [],
    ),

  createPartnerKey: (partnerId: string, body: PartnerApiKeyCreateInput) =>
    call<PartnerApiKeyCreatedOut>(`/admin/partners/${partnerId}/keys`, {
      method: "POST",
      body,
    }),

  /** Mint a replacement key; the old one keeps authenticating until
   *  ``grace_expires_at`` (now + grace_hours) so the partner can deploy
   *  the new secret without downtime. */
  rotatePartnerKey: (
    partnerId: string,
    keyId: string,
    body: { grace_hours?: number },
  ) =>
    call<PartnerApiKeyCreatedOut>(
      `/admin/partners/${partnerId}/keys/${keyId}/rotate`,
      { method: "POST", body },
    ),

  /** Immediate revoke, no grace — the key and every session token minted
   *  with it die now. */
  revokePartnerKey: (partnerId: string, keyId: string) =>
    call<PartnerApiKeyOut>(
      `/admin/partners/${partnerId}/keys/${keyId}/revoke`,
      { method: "POST", body: {} },
    ),

  listPartnerTenants: (partnerId: string) =>
    call<PartnerTenantOut[]>(`/admin/partners/${partnerId}/tenants`).then(
      (r) => r ?? [],
    ),

  linkPartnerTenant: (partnerId: string, body: PartnerTenantLinkInput) =>
    call<PartnerTenantOut>(`/admin/partners/${partnerId}/tenants`, {
      method: "POST",
      body,
    }),

  listPartnerAudit: (partnerId: string, limit = 100) =>
    call<EmbedAuditEntryOut[]>(
      `/admin/partners/${partnerId}/audit?limit=${limit}`,
    ).then((r) => r ?? []),

  getPartnerWallet: (partnerId: string) =>
    call<PartnerWalletOut>(`/admin/partners/${partnerId}/wallet`, {
      optional: true,
    }),

  listPartnerWalletLedger: (partnerId: string, limit = 50) =>
    call<PartnerLedgerOut[]>(
      `/admin/partners/${partnerId}/wallet/ledger?limit=${limit}`,
    ).then((r) => r ?? []),

  rechargePartnerWallet: (partnerId: string, qty: number) =>
    call<PartnerWalletOut>(`/admin/partners/${partnerId}/wallet/purchased`, {
      method: "POST",
      body: { qty },
    }),

  getPartnerModels: (partnerId: string) =>
    call<PartnerModelsOut>(`/admin/partners/${partnerId}/models`, {
      optional: true,
    }),

  putPartnerModels: (partnerId: string, modelIds: string[]) =>
    call<PartnerModelsOut>(`/admin/partners/${partnerId}/models`, {
      method: "PUT",
      body: { model_ids: modelIds },
    }),

  getPartnerLlm: (partnerId: string) =>
    call<PartnerLlmOut>(`/admin/partners/${partnerId}/llm`),

  blockPartnerLlm: (partnerId: string, blocked: boolean) =>
    call<PartnerLlmOut>(`/admin/partners/${partnerId}/llm/block`, {
      method: "POST",
      body: { blocked },
    }),

  getPartnerKnowledge: (partnerId: string) =>
    call<KnowledgeListOut>(`/admin/partners/${partnerId}/knowledge`, {
      optional: true,
    }),

  getPartnerClientWorkflow: (partnerId: string, ref: string) =>
    call<WorkflowPackOut>(
      `/admin/partners/${partnerId}/clients/${encodeURIComponent(ref)}/workflow`,
      { optional: true },
    ),

  getPartnerClientWorkflowRuns: (partnerId: string, ref: string) =>
    call<WorkflowRunsOut>(
      `/admin/partners/${partnerId}/clients/${encodeURIComponent(ref)}/workflow/runs`,
      { optional: true },
    ).then((r) => r ?? { items: [] }),

  getPartnerUsage: (partnerId: string, windowDays = 30) =>
    call<PartnerUsageOut>(
      `/admin/partners/${partnerId}/usage?window_days=${windowDays}`,
      { optional: true },
    ),

  listPartnerReceipts: (partnerId: string) =>
    call<ReceiptSummaryOut[]>(`/admin/partners/${partnerId}/receipts`).then(
      (r) => r ?? [],
    ),

  getPartnerReceipt: (partnerId: string, invoiceId: string) =>
    call<ReceiptOut>(
      `/admin/partners/${partnerId}/receipts/${invoiceId}`,
      { optional: true },
    ),

  generatePartnerReceipt: (partnerId: string, body: ReceiptGenerateInput) =>
    call<ReceiptOut>(`/admin/partners/${partnerId}/receipts`, {
      method: "POST",
      body,
    }),

  sendPartnerReceipt: (partnerId: string, invoiceId: string) =>
    call<ReceiptSendOut>(
      `/admin/partners/${partnerId}/receipts/${invoiceId}/send`,
      { method: "POST", body: {} },
    ),

  // ── F4 support tickets inbox ──────────────────────────────────────
  listTickets: (opts?: { status?: TicketStatus; partnerId?: string }) => {
    const qs = new URLSearchParams();
    if (opts?.status) qs.set("status", opts.status);
    if (opts?.partnerId) qs.set("partner_id", opts.partnerId);
    const suffix = qs.toString() ? `?${qs}` : "";
    return call<AdminTicketOut[]>(`/admin/tickets${suffix}`).then((r) => r ?? []);
  },

  getTicket: (ticketId: string) =>
    call<AdminTicketDetailOut>(`/admin/tickets/${ticketId}`, {
      optional: true,
    }),

  patchTicketStatus: (ticketId: string, status: TicketStatus) =>
    call<AdminTicketDetailOut>(`/admin/tickets/${ticketId}`, {
      method: "PATCH",
      body: { status },
    }),

  // ── billing plans + per-tenant billing ────────────────────────────────
  listBillingPlans: () =>
    call<BillingPlanOut[]>("/admin/billing-plans").then((r) => r ?? []),

  createBillingPlan: (body: BillingPlanCreateInput) =>
    call<BillingPlanOut>("/admin/billing-plans", { method: "POST", body }),

  getTenantBilling: (tenantId: string) =>
    call<TenantBillingOut>(`/admin/tenants/${tenantId}/billing`, {
      optional: true,
    }),

  updateTenantBilling: (tenantId: string, body: TenantBillingUpdateInput) =>
    call<TenantBillingOut>(`/admin/tenants/${tenantId}/billing`, {
      method: "PUT",
      body,
    }),
};
