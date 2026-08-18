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
    getCompanionRunEvents: (runId: string, sinceSeq = 0) =>
      call<CompanionEvents>(`${base}/runs/${enc(runId)}/events?since_seq=${sinceSeq}`),
    cancelCompanionRun: (runId: string) => call<null>(`${base}/runs/${enc(runId)}`, { method: "DELETE" }),
    getCompanionBudget: () => call<CompanionBudget>(`${base}/budget`),
  };
}
