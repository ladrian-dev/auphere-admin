/**
 * Lo que la API devuelve por `/console/companion/*` (metadatos, nunca cuerpos
 * de mensaje de cliente final). Un solo dueño: la consola y la aplicación de
 * escritorio importan estos tipos de aquí.
 */

export type CompanionThread = {
  id: string;
  title: string;
  mode: "consult" | "build";
  client_ref: string | null;
  /** Spec 003 — el hilo de un teammate; `null` en el Companion clásico. */
  teammate_id?: string | null;
  archived_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CompanionRunStarted = { run_id: string; thread_id: string; status: string };

/**
 * The runs of one thread (§5.2 of the contract, added in v1.1).
 *
 * This is what makes the timeline belong to the THREAD rather than to a
 * run, and therefore what makes `?companion=<thread>` shareable inside the
 * team: without it the browser cannot enumerate a thread's runs, so
 * opening a shared link on another machine would show an empty
 * conversation. A `localStorage` index was the stopgap; the server is the
 * source.
 *
 * Ascending by `started_at`, no pagination in Ola 1, opaque 404 when the
 * thread is not the principal's.
 */
export type CompanionRunSummary = {
  run_id: string;
  status: string;
  started_at: string;
  ended_at: string | null;
};

export type CompanionThreadRuns = { thread_id: string; runs: CompanionRunSummary[] };

/** One event of the durable run log. `data` is deliberately untyped: the
 *  payload shape depends on `event`, and the backend publishes against a
 *  closed catalogue that guarantees what may appear in it. */
export type CompanionEvent = { seq: number; event: string; data: Record<string, unknown> };

export type CompanionEvents = {
  run_id: string;
  events: CompanionEvent[];
  next_seq: number;
  /** Set only when the log rotated past the requested `since_seq`. */
  available_from: number | null;
};

export type CompanionBudget = {
  used: number;
  cap: number;
  remaining: number;
  percent: number;
  exhausted: boolean;
  period: string;
  resets_at: string;
};

/**
 * The per-partner flag of §10 of `docs/companion/CONTRACT-V2.md`.
 *
 * `partners.companion_enabled` defaults to **false** — the pilot is
 * internal — and `GET /console/me` gained the field. The console reads it
 * to decide whether to mount the bubble at all: an off bubble is ABSENCE,
 * not a disabled button with a tooltip, because a disabled button is an
 * advert for something you cannot have.
 *
 * It is served through its own BFF route rather than by widening the
 * shared `Me` type, for two reasons. That type lives in `lib/backend.ts`,
 * outside this agent's zone; and reading it defensively here
 * (`companion_enabled !== true` ⟹ off) is exactly the behaviour we want
 * while the API field does not exist yet: no field, no bubble, which is
 * the contract's own default.
 */
export type CompanionEnabled = { companion_enabled: boolean };

/**
 * One proposed write awaiting a human (CO-04). Mirrors
 * `CompanionActionOut` of §5 of `docs/companion/CONTRACT-V1.md`.
 *
 * **Nothing emits this yet** — CO-04 builds the write path in parallel.
 * It is typed against the frozen contract and doubled in tests; Phase 2
 * validates the real integration.
 *
 * Note the names: `preview` (not `payload`) and `note` (not `notes` /
 * `reason` / `message`). Those four are forbidden response property names
 * in every `/console/*` route — see §1.1 of the contract.
 */
export type CompanionAction = {
  action_id: string;
  thread_id: string;
  run_id: string | null;
  kind: string;
  title: string;
  preview: Record<string, unknown>;
  diff: Array<Record<string, unknown>> | null;
  impact: Array<Record<string, unknown>>;
  risk: "low" | "medium" | "high";
  reversible: boolean;
  status: string;
  state_hash: string;
  proposed_at: string;
  expires_at: string;
  decided_at: string | null;
  decided_by: string | null;
  applied_at: string | null;
  ok: boolean | null;
};

/**
 * 202 of `POST …/runs/{run_id}/resume`. **`run_id` is a NEW run** that
 * continues the same thread (§4.3): the paused run publishes nothing more,
 * so the drawer has to attach to the one returned here. `hitl.resolved`
 * is the first event of that new run.
 */
export type CompanionResumed = {
  run_id: string;
  thread_id: string;
  action_id: string;
  status: string;
};

export type CompanionDecision = "confirm" | "edit" | "cancel";

