/**
 * Pure types of the agent's one draft (spec 047, historia 2). No imports with
 * side effects: safe for client components and tests. Mirrors
 * `api/console/schemas_agent_draft.py`. The API client is `./agent-draft.ts`.
 */
import type { Audience, AudienceIn, ConsolePolicy, PaymentReview, VersionStatus } from "./agent-tools-types";

/** The screens of the agent where the draft differs from the active version. */
export type AgentDraftScreen = "settings" | "capabilities" | "knowledge" | "prompt";

/**
 * The draft of one agent — or, without one (`exists: false`), the version a
 * draft would start from. `revision` goes back in `If-Match` on every write.
 * `number` is «v{n} de {agente}»; `version` is the client-wide number the
 * routes of before spec 047 still take.
 */
export type AgentDraft = {
  agent_id: string;
  agent_name: string;
  revision: number;
  exists: boolean;
  number: number | null;
  version: number | null;
  status: VersionStatus | null;
  base_number: number | null;
  active_number: number | null;
  active_version: number | null;
  author: string | null;
  created_at: string | null;
  updated_at: string | null;
  change_note: string | null;
  system_prompt: string;
  tools: string[];
  skills: string[];
  settings: ConsolePolicy;
  audience: Audience;
  payment_review: PaymentReview;
  screens: AgentDraftScreen[];
  allowed: ("edit" | "discard")[];
};

/** What one save sends. Only what is sent changes. */
export type DraftPatch = {
  system_prompt?: string;
  tools?: string[];
  settings?: ConsolePolicy;
  audience?: AudienceIn;
  payment_review?: PaymentReview;
  note?: string;
};

/** One write on the draft after the revision a stale screen read. */
export type DraftChange = {
  revision: number;
  kind: "edit" | "publish" | "rollback" | "discard";
  by: string;
  at: string;
  /** Stable keys: `system_prompt`, `tools`, `settings.tone`, `audience`… */
  fields: string[];
};

/** The `detail` of a 412: the draft as it is now and what changed since. */
export type DraftConflict = {
  code: "revision_conflict";
  current: AgentDraft;
  changes: DraftChange[];
};

/** One version of the agent's history. */
export type AgentVersionEntry = {
  number: number;
  version: number;
  status: VersionStatus;
  author: string | null;
  created_at: string;
  published_at: string | null;
  published_by: string | null;
  change_note: string | null;
  base_number: number | null;
};
