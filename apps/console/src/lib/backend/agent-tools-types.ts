/**
 * Pure types + constants of lane `agent-tools` (no imports, no
 * `server-only`): safe for client components, Zod schemas and tests.
 * Mirrors `api/console/schemas_agent_tools.py` and
 * `services/agent_console_policy.py`. The API client lives in
 * `./agent-tools.ts` (server-only, spread into `backendFor`).
 */

// ── CP-11 · structured settings (policies.console) ─────────────────────

export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export type Weekday = (typeof WEEKDAYS)[number];
export const TONES = ["formal", "cercano", "neutro"] as const;
export type Tone = (typeof TONES)[number];
export const ESCALATION_TRIGGERS = ["user_asks_human", "angry", "out_of_scope", "after_n_turns"] as const;
export type EscalationTrigger = (typeof ESCALATION_TRIGGERS)[number];

export type ScheduleSlot = { day: Weekday; open: string; close: string };

export type ConsolePolicy = {
  schema_version: number;
  identity: { name: string; persona: string };
  tone: { style: Tone; guidance: string };
  objective: string;
  schedule: { timezone: string; weekly: ScheduleSlot[]; closed_message: string };
  languages: { primary: string; allowed: string[] };
  escalation: { enabled: boolean; triggers: EscalationTrigger[]; after_n_turns: number | null; handoff_message: string };
  ai_disclosure: { enabled: boolean; disclosure_message: string; decided_by: string | null; decided_at: string | null };
};

export type VersionStatus = "staged" | "active" | "archived";

export type AgentSettingsOut = {
  version: number | null;
  version_status: VersionStatus | null;
  active_version: number | null;
  has_draft: boolean;
  settings: ConsolePolicy;
};
export type AgentSettingsSaved = AgentSettingsOut & { draft_created: boolean };

// ── CP-13 · tools + connectors ─────────────────────────────────────────

export const TOOL_MODES = ["always", "needs_approval", "blocked"] as const;
export type ToolMode = (typeof TOOL_MODES)[number];

export type ToolOut = {
  name: string;
  description: string;
  capability_tags: string[];
  read_only: boolean;
  destructive: boolean;
  status: string;
  enabled: boolean;
  enabled_in_active: boolean;
  connector_slug: string | null;
  connector_display_name: string | null;
  connector_status: string | null;
  connector_required: boolean;
  usable: boolean;
  default_mode: ToolMode;
  override_mode: ToolMode | null;
  effective_mode: ToolMode;
};
export type ToolCatalogOut = {
  version: number | null;
  version_status: VersionStatus | null;
  active_version: number | null;
  has_draft: boolean;
  tools: ToolOut[];
};
export type ToolsSaved = ToolCatalogOut & { draft_created: boolean };
export type ToolModeOut = { tool_name: string; mode: ToolMode; set_by: string; updated_at: string };

export type CredentialsField = { field: string; label?: string; placeholder?: string; secret?: boolean; required?: boolean };
export type ConnectorOut = {
  slug: string;
  display_name: string;
  vendor: string;
  category: string;
  auth_kind: string;
  logo_url: string | null;
  capabilities: string[];
  installed: boolean;
  status: string | null;
  scopes_granted: string[];
  connected_at: string | null;
  last_synced_at: string | null;
  last_health_check_at: string | null;
  consent_expires_at: string | null;
  credentials_form: CredentialsField[];
  tools_total: number;
  tools_enabled: number;
};
export type ConsentOut = { slug: string; signed_consent_url: string; expires_at: string };
export type ConnectorSyncOut = { slug: string; added: string[]; deprecated: string[]; unchanged_count: number };
export type ConnectApiKeyBody = { secrets: Record<string, string>; endpoint_meta: Record<string, unknown> };

// ── CP-14 · skills ─────────────────────────────────────────────────────

export type SkillOut = { name: string; description: string; version: string; activatable: boolean; enabled: boolean; enabled_in_active: boolean };
export type SkillsOut = {
  version: number | null;
  version_status: VersionStatus | null;
  active_version: number | null;
  has_draft: boolean;
  skills: SkillOut[];
};
export type SkillsSaved = SkillsOut & { draft_created: boolean };

// ── CP-15 · knowledge ──────────────────────────────────────────────────

export const KNOWLEDGE_ERROR_CODES = ["fetch_failed", "unsupported_type", "too_large", "empty"] as const;
export type KnowledgeErrorCode = (typeof KNOWLEDGE_ERROR_CODES)[number];
export type KnowledgeStatus = "pending" | "indexed" | "failed";
export type KnowledgeDocumentOut = {
  id: string;
  kind: "file" | "url";
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
export type KnowledgeListOut = { items: KnowledgeDocumentOut[]; total: number; indexed_chars: number; prompt_char_cap: number };

/** Server-side cap of `POST /knowledge` (413 above it). Mirrored client-side. */
export const KNOWLEDGE_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
