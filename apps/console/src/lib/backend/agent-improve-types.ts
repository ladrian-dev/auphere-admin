import type { ProposalOp } from "./builder-types";

/**
 * Spec 047 (T174; requisitos 51 y 52.2; `contracts/console-api.md` §4) — el
 * Rendimiento y las Mejoras de un agente, para el partner
 * (`/console/clients/{ref}/agents/{agent_id}/…`).
 *
 * Nada de esto lleva cuerpos de mensaje ni datos del cliente final (C1 y C8): las
 * conversaciones llegan con sus metadatos y una sugerencia no dice a qué
 * conversaciones se refiere. El dinero va a precio, en cien milésimas de dólar.
 *
 * Tipos puros, sin imports con efectos: valen para componentes de cliente y para
 * los tests. El cliente de la API es `./agent-improve.ts`.
 */
export type ImproveMoney = { amount_micros: number; currency: "USD" };

export type PerformanceDay = {
  day: string;
  conversations: number;
  resolved_without_person: number;
  handed_to_person: number;
  spent: ImproveMoney;
};

export type AgentPerformance = {
  days: number;
  since: string;
  until: string;
  conversations: number;
  resolved_without_person: number;
  handed_to_person: number;
  resolved_pct: number | null;
  spent: ImproveMoney;
  spend_per_conversation: ImproveMoney | null;
  series: PerformanceDay[];
};

export type AgentConversation = {
  id: string;
  started_at: string;
  last_activity_at: string;
  channel_type: string | null;
  duration_seconds: number | null;
  messages_count: number;
  outcome: "handed_to_person" | "resolved_without_person";
  in_progress: boolean;
  /** Un código (`escalated`, `taken_by_person`, `no_balance`…); la consola pone las palabras. */
  handoff_reason: string | null;
  spent: ImproveMoney | null;
};

export type AgentConversationPage = { items: AgentConversation[]; next_cursor: string | null };

export type SuggestedTest = {
  name: string;
  persona: string;
  first_message: string;
  plan: string;
  criteria: Record<string, unknown>[];
  critical: boolean;
};

export type ImprovementAction = "accept" | "discard";

export type Improvement = {
  id: string;
  /** Las sugerencias semanales y las correcciones de comportamiento de la Bandeja. */
  kind: "suggestion" | "correction";
  week: string | null;
  /** La paráfrasis, sin datos personales. */
  topic: string;
  summary: string | null;
  /** Solo en una corrección: la lección que escribió la persona del cliente y desde dónde. */
  lesson: string | null;
  origin: string | null;
  conversations_count: number;
  contacts_count: number;
  proposal_id: string | null;
  diff: { ops?: ProposalOp[] };
  test: SuggestedTest | null;
  created_at: string;
};

export type Improvements = { items: Improvement[]; allowed: ImprovementAction[] };
export type ImprovementAccepted = { id: string; status: "accepted"; draft_revision: number; test_id: string };
export type ImprovementDiscarded = { id: string; status: "discarded"; suppress_until: string | null };

/** El periodo de Rendimiento: 30 días por defecto (51.1); 7, 30 o 90 en la píldora. */
export const PERFORMANCE_PERIODS = [7, 30, 90] as const;
export type PerformancePeriod = (typeof PERFORMANCE_PERIODS)[number];
