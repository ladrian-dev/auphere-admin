/**
 * Tipos puros del constructor de agentes (spec 047, historia 7; T081). Sin
 * imports con efectos: valen para componentes de cliente y para los tests.
 * Reflejan `api/console/schemas_agent_builder.py`, el `GET /console/jobs/{id}`
 * de un trabajo `agent_draft` y `contracts/agent-spec.schema.json`. El cliente
 * de la API es `./builder.ts`.
 */
import type { AgentDraft } from "./agent-draft-types";

// ── «Nuevo agente» ──────────────────────────────────────────────────────────

/** Una plantilla de «Empezar desde una plantilla». `group` es el nombre del
 *  grupo de negocio (los 6 de la spec 046 más «Otro»). */
export type TemplateOption = { id: string; name: string; group: string; is_default: boolean };

/** Lo que ofrece «Nuevo agente»: los ejemplos y las plantillas, con la del
 *  partner primero y nunca aplicada sola (requisito 17.9). */
export type DraftOptions = {
  examples: string[];
  templates: TemplateOption[];
  default_template: string | null;
  name_max: number;
  description_min: number;
  description_max: number;
};

export type DraftStart = "describe" | "template" | "blank";
export type DraftJobBody = { name: string; description?: string; start: DraftStart; template_id?: string };

/** El `202`. Con «Generar borrador» el agente aún no existe (`agent_id` nulo):
 *  nace cuando termina el trabajo (17.2). Con plantilla o en blanco el trabajo
 *  ya viene terminado y trae el agente. */
export type DraftJobAccepted = { job_id: string; status: "queued" | "running" | "done" | "failed"; agent_id: string | null };

// ── el trabajo ──────────────────────────────────────────────────────────────

/** Los bloques del borrador, en el orden en que llegan y se pintan (17.3). */
export const BUILDER_BLOCKS = [
  "identity",
  "voice",
  "instructions",
  "procedures",
  "services",
  "skills",
  "escalation",
  "rules",
  "tests",
  "questions",
] as const;
export type BuilderBlockKey = (typeof BUILDER_BLOCKS)[number];

/** Una conexión que pide una habilidad: «Conectar {conector}» en su fila (17.6). */
export type ConnectRequest = { integration: string; reason: string };

/** Un bloque tal como lo cuenta el trabajo mientras escribe. */
export type BuilderBlock = {
  key: BuilderBlockKey;
  value?: unknown;
  /** `tests` y `questions`: cuántas. */
  count?: number;
  /** `questions`: cuántas descartó. */
  discarded?: number;
  /** `skills`: lo que falta conectar. */
  connect?: ConnectRequest[];
};

export type QuestionScope = "business" | "agent";

/** Una pregunta del constructor (17.4): su porqué, respuestas cerradas cuando
 *  se puede y dónde se guarda la respuesta (17.5). */
export type BuilderQuestion = {
  id: string;
  text: string;
  why: string;
  options: string[] | null;
  target: string;
  scope: QuestionScope;
  /** Una respuesta de negocio se puede guardar en «Solo este agente». */
  can_be_agent_only: boolean;
};

export type DraftJobResult = {
  agent_id: string;
  questions: BuilderQuestion[];
  /** Cuántas preguntas descartó y por qué; nunca una cifra fija (17.4). */
  discarded: { count: number; reasons: string[] };
  connect?: ConnectRequest[];
  dropped_tools?: { tool: string; why: string }[];
  tests?: { case: number };
};

export type DraftJobStatus = "queued" | "running" | "done" | "failed";

/** `GET /console/jobs/{job_id}` de un trabajo `agent_draft`. Un fallo viaja
 *  solo como `error_code` (`builder_unavailable`, `name_taken`…): las palabras
 *  son de la consola. `progress.input` guarda lo que se escribió (15.8). */
export type DraftJob = {
  job_id: string;
  kind: string;
  status: DraftJobStatus;
  agent_id: string | null;
  progress: {
    step?: "reading" | "writing" | null;
    blocks?: BuilderBlock[];
    input?: { name?: string; description?: string };
  } | null;
  result: DraftJobResult | null;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
};

/** Una respuesta. `scope` dice dónde se guarda: la ficha o «Solo este agente». */
export type BuilderAnswer = { question_id: string; value: string; scope?: QuestionScope };
export type AnswersResult = {
  applied: { question_id: string; scope: QuestionScope; target: string }[];
  agent_id: string;
  draft_revision: number;
  tests_stale: number;
};

// ── el AgentSpec v1 (`contracts/agent-spec.schema.json`) ────────────────────

export type EscalationCode = "asks_for_human" | "failed_attempts" | "complaint" | "payment_issue" | "emergency" | "out_of_scope";
export const ESCALATION_CODES: readonly EscalationCode[] = [
  "asks_for_human",
  "failed_attempts",
  "complaint",
  "payment_issue",
  "emergency",
  "out_of_scope",
];
export type EscalationTrigger = EscalationCode | { custom: string };
export type Register = "tu" | "usted" | "vos";
export type SpecSection = { title: string; body: string };
export type SpecProcedure = { id: string; title: string; when: string; steps: string; tools?: string[] };
export type SpecSkill = { key: string; enabled: boolean; integration?: string | null; fallback?: string };
export type SpecFaq = { q: string; a: string };

export type AgentSpec = {
  schema_version: "1";
  mode: "instructions" | "structured";
  identity: { name: string; description: string; goal?: string };
  voice?: { tone?: string; languages?: string[]; register?: Register; greeting?: string };
  instructions?: { sections?: SpecSection[]; legacy_text?: string };
  procedures?: SpecProcedure[];
  services?: { mode: "all" | "list"; service_ids?: string[]; faqs?: SpecFaq[] };
  skills?: SpecSkill[];
  tools?: string[];
  connection_requests?: ConnectRequest[];
  escalation?: { triggers?: EscalationTrigger[]; failed_attempts?: number; message?: string };
  rules?: string[];
  ai_disclosure: { decided: boolean; mode?: "first_message" | "on_ask"; text?: string };
  /** Lo que no edita esta pantalla viaja tal cual (`model_policy`, `memory`,
   *  `team_access`, `reception`, `test_suite`). */
  [key: string]: unknown;
};

/** Los bloques que se editan en línea en la pantalla del agente (17.7). */
export type EditableBlock = "identity" | "voice" | "instructions" | "procedures" | "escalation" | "rules";

/** Cuántas pruebas tiene el agente y cuántas hay que volver a ejecutar (17.7). */
export type DraftTests = { total: number; stale: number; case: number; sector: number };

/** El borrador con su AgentSpec y el estado de sus pruebas. */
export type BuilderDraft = AgentDraft & { spec: AgentSpec | null; tests: DraftTests | null };

/** Un problema del validador sin modelo: dónde (`pointer`) y qué. */
export type SpecProblem = { pointer: string; code: string; message: string };

// ── propuestas (15.2, 15.3) ─────────────────────────────────────────────────

export type ProposalOp = { op: "add" | "remove" | "replace" | "move" | "copy" | "test"; path: string; value?: unknown; from?: string };
export type Proposal = {
  id: string;
  kind: string;
  author: string;
  summary: string | null;
  diff: { ops?: ProposalOp[] } & Record<string, unknown>;
  status: string;
  created_at: string;
  expires_at: string;
  problems?: SpecProblem[];
};
export type ProposalDecision = { id: string; status: string; draft_revision: number | null };
