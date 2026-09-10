import type { PageContext } from "@/components/companion/page-context";
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
// Los tipos del cable tienen un solo dueño desde la spec 003: el paquete.
export type {
  CompanionActionDto as CompanionAction,
  CompanionBudget,
  CompanionDecision,
  CompanionEnabled,
  CompanionEvent,
  CompanionEvents,
  CompanionResumed,
  CompanionRunStarted,
  CompanionRunSummary,
  CompanionThread,
  CompanionThreadRuns,
} from "@nexus/companion-ui";
import type {
  CompanionActionDto as CompanionAction,
  CompanionBudget,
  CompanionDecision,
  CompanionEnabled,
  CompanionEvents,
  CompanionResumed,
  CompanionRunStarted,
  CompanionThread,
  CompanionThreadRuns,
} from "@nexus/companion-ui";

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
    startCompanionRun: (threadId: string, prompt: string, pageContext?: PageContext) =>
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
    /**
     * The flag, off `GET /console/me` (§10 of CONTRACT-V2).
     *
     * Narrowed rather than asserted: anything that is not literally `true`
     * — an older API without the field included — reads as off. That is
     * the contract's default (`false`) and the safe direction: we would
     * rather hide a feature a partner has than advertise one it has not.
     */
    getCompanionEnabled: async (): Promise<CompanionEnabled> => {
      const me = await call<Record<string, unknown>>("/console/me");
      return { companion_enabled: me.companion_enabled === true };
    },
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
