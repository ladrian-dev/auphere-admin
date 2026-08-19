import type { Call } from "../backend";

/**
 * Lane module `companion` (CO-01). Types mirror
 * `api/console/schemas_companion.py`.
 *
 * Two things are different from every other lane, and both come from the
 * same decision: **the run does not die with the connection**.
 *
 * - `startCompanionRun` returns 202 with a `run_id` and comes back
 *   immediately. The work keeps going on AWS whether or not this browser
 *   is still around.
 * - There are therefore TWO ways to read a run: `getCompanionRunEvents`
 *   (REST history) and the SSE proxy at
 *   `app/api/companion/runs/[id]/stream/route.ts`. Reconnecting correctly
 *   means using both — open the stream, list the history, drop anything
 *   whose `seq` you already have. A stream alone tells you there is a hole
 *   but not where to fill it from.
 *
 * And `cancelCompanionRun` is the ONLY way to stop a run. Aborting the
 * `fetch` never reaches the backend; the drawer's Stop button must call it.
 */
export type CompanionThread = {
  id: string;
  title: string;
  mode: "consult" | "build";
  client_ref: string | null;
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

const enc = encodeURIComponent;
const base = "/console/companion";

/** Backend path of the SSE stream — the route handler forwards it verbatim. */
export function companionStreamPath(runId: string, sinceSeq = 0): string {
  const q = new URLSearchParams({ since_seq: String(sinceSeq) });
  return `${base}/runs/${enc(runId)}/stream?${q.toString()}`;
}

export function companionApi(call: Call) {
  return {
    listCompanionThreads: (p: { include_archived?: boolean } = {}) =>
      call<CompanionThread[]>(`${base}/threads${p.include_archived ? "?include_archived=true" : ""}`),
    createCompanionThread: (body: { title?: string; client_ref?: string; mode?: "consult" | "build" }) =>
      call<CompanionThread>(`${base}/threads`, { method: "POST", body }),
    patchCompanionThread: (threadId: string, body: { title?: string; archived?: boolean; mode?: "consult" | "build" }) =>
      call<CompanionThread>(`${base}/threads/${enc(threadId)}`, { method: "PATCH", body }),
    startCompanionRun: (threadId: string, prompt: string, pageContext?: Record<string, unknown>) =>
      call<CompanionRunStarted>(`${base}/threads/${enc(threadId)}/runs`, {
        method: "POST",
        body: { prompt, page_context: pageContext ?? null },
      }),
    /** Runs of a thread, ascending by `started_at` (§5.2). The source of
     *  the timeline's run index — `localStorage` is only a cache. */
    listCompanionThreadRuns: (threadId: string) =>
      call<CompanionThreadRuns>(`${base}/threads/${enc(threadId)}/runs`),
    getCompanionRunEvents: (runId: string, sinceSeq = 0) =>
      call<CompanionEvents>(`${base}/runs/${enc(runId)}/events?since_seq=${sinceSeq}`),
    cancelCompanionRun: (runId: string) => call<null>(`${base}/runs/${enc(runId)}`, { method: "DELETE" }),
    getCompanionBudget: () => call<CompanionBudget>(`${base}/budget`),
    /** Answer a pending confirmation (§4). 202 → attach to the NEW run.
     *  `note` is singular: `notes` is a forbidden property name (§1.1),
     *  and with `edit`/`cancel` it travels back to the model as the
     *  user's reason, so the plan can be adjusted rather than just refused. */
    resumeCompanionRun: (runId: string, body: { action_id: string; decision: CompanionDecision; note?: string }) =>
      call<CompanionResumed>(`${base}/runs/${enc(runId)}/resume`, { method: "POST", body }),
    /** Read one action. Exists for the PARTIAL state (§5.1): reloading
     *  with a confirmation pending must paint the card without depending
     *  on the Redis log still being alive. */
    getCompanionAction: (actionId: string) => call<CompanionAction>(`${base}/actions/${enc(actionId)}`),
  };
}
