/**
 * Tipos puros de lo que pasa entre el borrador y los clientes de verdad (spec
 * 047, historias 8 y 9; T089 y T094): el playground, las pruebas, la revisión,
 * «Guardar» con su puerta, el historial y restaurar. Sin imports con efectos:
 * valen para componentes de cliente y para los tests. Reflejan
 * `api/console/agent_{playground,tests,review,publish}.py`. El cliente de la API
 * es `./agent-quality.ts`.
 */

// ── el playground (requisito 20) ────────────────────────────────────────────

/** «Lo que habría hecho: …», en el lenguaje del negocio (20.3). */
export type PlaygroundAction = { tool: string; phrase: string };

/** Un turno: lo que escribió el cliente simulado o las burbujas del agente (20.4). */
export type PlaygroundTurn = {
  role: "customer" | "agent";
  bubbles: string[];
  several_bubbles: boolean;
  actions: PlaygroundAction[];
};

/** Una cita de la agenda simulada; `when` ya viene dicho en la zona del negocio. */
export type SimBooking = { id: string; service: string; when: string; status: "confirmed" | "cancelled" | string };
export type SimService = { name: string; bookable: boolean; duration_min: number | null; price: string | null };

export type PlaygroundPermission = "send" | "set_time" | "close";

/** Una conversación simulada. `now` es la hora simulada con su desfase, en la zona del negocio. */
export type PlaygroundSession = {
  session_id: string;
  version_number: number;
  is_draft: boolean;
  timezone: string;
  now: string;
  agenda: SimBooking[];
  services: SimService[];
  transcript: PlaygroundTurn[];
  created_by: string | null;
  /** Vacío para quien solo lee (20.5): la ve sin poder escribir. */
  allowed: PlaygroundPermission[];
};

export type PlaygroundReply = { turn: PlaygroundTurn; now: string; agenda: SimBooking[] };

// ── las pruebas (requisito 21) ──────────────────────────────────────────────

export type TestStatus = "passed" | "flaky" | "failed" | "unknown" | "not_run" | "not_applicable";
export const TEST_STATUSES: readonly TestStatus[] = ["passed", "flaky", "failed", "unknown", "not_run", "not_applicable"];

export type TestCriterion = { key: string; text: string };

export type AgentTest = {
  id: string;
  /** `case` (del caso), `sector` (de la batería del nicho), `person` (añadida)… */
  kind: string;
  name: string;
  persona: string;
  first_message: string;
  plan: string;
  expected_state: Record<string, unknown>;
  criteria: TestCriterion[];
  critical: boolean;
  not_applicable_reason: string | null;
  sector_test_ref: string | null;
  stale: boolean;
  status: TestStatus;
  /** Cuántas de las repeticiones pasaron y cuántas decidió el juez (21.4). */
  passes: number;
  decided: number;
  /** Lo que se comprobó: el estado final, no lo que dijo el agente (21.3, 21.5). */
  why_failed: string | null;
};

export type TestSummary = Record<TestStatus, number> & {
  total: number;
  stale: number;
  critical_failed: string[];
  /** Tasa de la última pasada, en %; `null` sin ninguna decidida. */
  rate: number | null;
};

export type TestSuite = {
  summary: TestSummary;
  tests: AgentTest[];
  /** Sin calibrar, el juez no decide: solo cuenta el estado final (21.8). */
  judge_calibrated: boolean;
  allowed: ("add" | "edit" | "run")[];
};

export type TestBody = {
  name: string;
  persona?: string;
  first_message: string;
  plan?: string;
  expected_state?: Record<string, unknown>;
  criteria?: TestCriterion[];
  critical?: boolean;
};
export type TestPatch = Partial<Omit<TestBody, "persona">> & { not_applicable_reason?: string };
export type TestRunScope = "all" | "affected" | "one";
export type TestRunAccepted = { job_id: string; run_id: string; tests: number };

// ── la revisión (requisito 22) ──────────────────────────────────────────────

export type ReviewFix =
  | { kind: "link"; target: string; integration?: string; service_id?: string; channel_id?: string; [key: string]: unknown }
  | { kind: "edit"; pointer: string | null }
  | { kind: "proposal"; proposal_id: string };

export type ReviewFinding = {
  code: string;
  severity: "block" | "warn";
  message: string;
  pointer?: string;
  fix?: ReviewFix;
};

/** Una comprobación que corrió de verdad (22.3): sin «✓» fijos. */
export type ReviewCheck = { check: string; ok: boolean; findings: number };

export type AgentReview = { version_number: number | null; findings: ReviewFinding[]; checks: ReviewCheck[]; blocking: number };

// ── «Guardar» y la puerta (requisitos 23 y 24) ─────────────────────────────

export type PublishAction = "save" | "save_and_connect" | "save_changes";
export type DiffRow = { part: string; label: string; change: "add" | "remove" | "replace" | string; added?: string[]; removed?: string[] };

export type GateConditionName = "validator" | "critical_tests" | "regression" | "ai_disclosure" | "review";
export type GateCondition = { condition: GateConditionName | string; ok: boolean };
export type GateItem = { condition: string; code: string; message: string; pointer?: string | null };
export type Gate = {
  conditions: GateCondition[];
  /** No se puede saltar: hay que arreglarlo. */
  hard: GateItem[];
  /** Solo owner o admin, con el motivo (23.3). */
  overridable: GateItem[];
  /** Pruebas normales en rojo: «Guardar igualmente» con confirmación (23.2). */
  normal_failures: string[];
  rate: number | null;
  reference_rate: number | null;
};

export type PublishPreview = {
  action: PublishAction;
  has_draft: boolean;
  has_channels: boolean;
  diff: DiffRow[];
  gate: Gate | null;
  can_override: boolean;
};

export type PublishBody = { note?: string; accept_normal_failures?: boolean; override_reason?: string };

/** El trabajo `publish` o `tests` visto por la consola (`GET /console/jobs/{id}`). */
export type QualityJob = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  agent_id: string | null;
  progress: { step?: string | null; blocks?: ({ key: string } & Record<string, unknown>)[] } | null;
  result: Record<string, unknown> | null;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
};

export type PublishResult = { agent_id?: string; number: number; undo_until: string; gate: Gate };

export type HistoryEntry = {
  number: number;
  status: "staged" | "active" | "archived" | string;
  author: string | null;
  created_at: string;
  published_at: string | null;
  published_by: string | null;
  note: string | null;
  changed: string[];
  model_policy: Record<string, unknown> | null;
  tests: { rate: number | null; conditions: GateCondition[] } | null;
  override_reason: string | null;
};

export type RestoreResult = { draft_number: number; restored_from: number; revision: number | null };
