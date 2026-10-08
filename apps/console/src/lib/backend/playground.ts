import type { Call } from "../backend";
import { q } from "../backend";

/**
 * Lane module `playground` (CP-16). Types mirror
 * `api/console/schemas_playground.py` — metadata only: no message bodies
 * (the transcript travels ONLY over the SSE stream, proxied by
 * `app/api/playground/[ref]/threads/[id]/stream/route.ts`), no tenant ids,
 * tokens instead of dollars (C9). Spread into `backendFor` in `lib/backend.ts`.
 */
export type PlaygroundThread = {
  id: string;
  title: string;
  archived_at: string | null;
  last_run_at: string | null;
  turn_count: number;
  created_at: string;
  updated_at: string;
};

export type PlaygroundRunStarted = { run_id: string; thread_id: string; status: string };

export type PlaygroundBudget = {
  used: number;
  cap: number;
  remaining: number;
  percent: number;
  exhausted: boolean;
  period: string;
  resets_at: string;
};

const enc = encodeURIComponent;
const base = (ref: string) => `/console/clients/${enc(ref)}/playground`;

/** Backend path of the SSE stream — the route handler forwards it verbatim. */
export function playgroundStreamPath(ref: string, threadId: string, runId: string, sinceSeq = 0): string {
  const q = new URLSearchParams({ run_id: runId, since_seq: String(sinceSeq) });
  return `${base(ref)}/threads/${enc(threadId)}/stream?${q.toString()}`;
}

export function playgroundApi(call: Call) {
  return {
    /** Spec 030: with `agent`, only that agent's threads (old ones without one are the principal's). */
    listPlaygroundThreads: (ref: string, p: { include_archived?: boolean; agent?: string } = {}) =>
      call<PlaygroundThread[]>(`${base(ref)}/threads${q({ include_archived: p.include_archived || undefined, agent: p.agent })}`),
    /** Spec 030: the thread is pinned to `agent` (the principal without it). */
    createPlaygroundThread: (ref: string, body: { title?: string }, agent?: string) =>
      call<PlaygroundThread>(`${base(ref)}/threads${agent ? `?agent=${enc(agent)}` : ""}`, { method: "POST", body }),
    patchPlaygroundThread: (ref: string, threadId: string, body: { title?: string; archived?: boolean }) =>
      call<PlaygroundThread>(`${base(ref)}/threads/${enc(threadId)}`, { method: "PATCH", body }),
    startPlaygroundRun: (ref: string, threadId: string, prompt: string) =>
      call<PlaygroundRunStarted>(`${base(ref)}/threads/${enc(threadId)}/runs`, { method: "POST", body: { prompt } }),
    cancelPlaygroundRun: (ref: string, runId: string) =>
      call<null>(`${base(ref)}/runs/${enc(runId)}`, { method: "DELETE" }),
    getPlaygroundBudget: () => call<PlaygroundBudget>("/console/playground/budget"),
  };
}
