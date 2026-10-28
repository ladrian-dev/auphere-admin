/**
 * Tipos puros de la vida de un agente, del copiloto y de «Completar con el
 * constructor» (spec 047, historias 18, 19 y 20; T124, T099 y T098). Sin
 * imports con efectos: valen para componentes de cliente y para los tests.
 * Reflejan `api/console/agent_lifecycle_routes.py`, `agent_copilot.py`,
 * `agents_list.py` y `client_builder.py`. El cliente de la API es
 * `./agent-life.ts`.
 */
import type { ProposalOp } from "./builder-types";

// ── la vida del agente (requisitos 25 a 28) ─────────────────────────────────

export type AgentLifecycle = "draft" | "published" | "paused" | "archived";
export type PauseReason = "manual" | "no_balance" | "agent_cap" | "client_paused" | "client_archived";
export type VisibleCode = "archived" | "paused" | "draft" | "serving" | "testing" | "ready_no_channel";
export type StateTone = "positive" | "info" | "warn" | "danger" | "muted";

/** El estado visible: un solo cálculo en la API, el mismo en toda la consola (25.5). */
export type AgentVisibleState = { code: VisibleCode | string; tone: StateTone | string; reason: PauseReason | string | null };

/** La pestaña que abre la tarjeta de un agente (26.1). */
export type AgentOpens = "builder" | "channels" | "overview";

export type AgentLifeAction = "rename" | "pause" | "resume" | "archive" | "restore" | "make_default";

/** La cabecera de un agente; también la de uno archivado, para restaurarlo. */
export type AgentHeader = {
  id: string;
  name: string;
  lifecycle: AgentLifecycle | string;
  pause_reason: PauseReason | string | null;
  visible_state: AgentVisibleState;
  is_default: boolean;
  open_conversations: number;
  paused_by_kind: string | null;
  paused_origin: string | null;
  /** Solo lo que esta persona puede hacer (§V). */
  allowed: AgentLifeAction[];
  /** Spec 047 (44.1): el tope mensual y lo gastado este mes, en cien milésimas de `cap_currency` (la moneda de la bolsa). */
  monthly_cap_micros?: number | null;
  month_spent_micros?: number;
  cap_currency?: "EUR" | "USD";
  /** Spec 047 (35): Recepción según la versión publicada; el borrador puede decir otra cosa. */
  is_reception?: boolean;
};

/** Adónde va cada número al archivar: otro agente o «pause» (28.1). */
export type ChannelDestination = { channel_id: string; to: string | "pause" };

// ── el copiloto (requisito 19) ──────────────────────────────────────────────

export type CopilotContext = { answer?: string; actions?: { tool: string; phrase: string }[]; test_id?: string };

export type CitationKind = "business" | "instruction" | "knowledge" | "tool";
export type Citation = {
  kind: CitationKind | string;
  label: string;
  excerpt: string;
  link: { target: string; pointer?: string | null; tool?: string | null } | null;
};

export type CopilotProposal = { id: string; kind: string; summary: string | null; diff: { ops?: ProposalOp[] } & Record<string, unknown>; expires_at: string };

/** «Arreglar» un dato: la persona elige dónde se corrige y entonces se aplica (19.4). */
export type CopilotFixOffer = { test_id: string; scopes: ("business" | "agent")[] };

export type CopilotAnswer = { text: string; citations: Citation[]; proposals: CopilotProposal[]; fix: CopilotFixOffer | null };
export type CopilotFixResult = { scope: "business" | "agent"; faq_id?: string; pointer?: string };

// ── «Completar con el constructor» (requisito 18) ───────────────────────────

export type ClientBuilderResult = {
  /** Los ids de las sugerencias que dejó en la ficha, por sección. */
  sections: Record<string, string[]>;
  /** Agentes que propone, sin crearlos (18.4). */
  agents: { name: string; description: string }[];
  discarded: string[];
};
