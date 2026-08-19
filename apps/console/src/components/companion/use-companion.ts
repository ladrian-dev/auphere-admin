"use client";

import * as React from "react";

import type { CompanionThread } from "@/lib/backend/companion";

import { SseParser } from "../playground/sse";
import { cacheRunIds, companionClient, loadRunIds, rememberRunId } from "./client";
import type { PageContext } from "./page-context";
import { type CompanionState, companionReducer, emptyCompanionState } from "./state";
import type { Decision } from "./types";

/**
 * The connection loop of the drawer — correction C1, implemented.
 *
 * The shape that matters, and the reason it is not "just a `fetch`":
 *
 * ```
 * openThread:  GET …/threads/{id}/runs → REST history of each run → dedupe
 *              by (run_id, seq) → attach live to the last one if running
 * send:        POST …/runs → 202 {run_id} → remember it → stream it
 * decide:      POST …/resume → 202 {run_id: NEW} → remember → stream THAT
 * stop:        DELETE …/runs/{id}   ← the only thing that cancels work
 * ```
 *
 * Three traps this avoids on purpose:
 *
 * 1. **Aborting the stream does not stop the run.** The abort controller
 *    here only tears down a view; Stop is a separate endpoint.
 * 2. **After a `resume` the 202 carries a NEW `run_id`** (§4.3). The paused
 *    run publishes nothing more, so following it would hang forever.
 * 3. **Reconnecting resumes from that run's own last `seq`**, never from 0,
 *    or every reconnect would replay the turn.
 *
 * The run index is **server-owned** (§5.2 of the contract, v1.1), which is
 * what lets a shared `?companion=<thread>` link rebuild the whole
 * conversation on a machine that has never seen it. `localStorage` is a
 * fallback for when that call fails, and taking it marks the timeline
 * partial — see D2 of `docs/companion/PLAN-CO-03.md`.
 */
const MAX_RECONNECTS = 3;

export type Status = "loading" | "error" | "ready";

export function useCompanion() {
  const [state, dispatch] = React.useReducer(companionReducer, emptyCompanionState);
  const [threads, setThreads] = React.useState<CompanionThread[]>([]);
  const [threadId, setThreadId] = React.useState<string | null>(null);
  // "ready", not "loading": until a thread is opened there is nothing to
  // load, and the empty state (with its page-derived suggestions) is the
  // correct thing to show. `openThread` flips this to "loading" itself.
  // Starting at "loading" left a drawer opened without `?companion=` stuck
  // on skeletons forever, so the empty state could never render.
  const [status, setStatus] = React.useState<Status>("ready");
  const [errorDetail, setErrorDetail] = React.useState<string | null>(null);
  const [partial, setPartial] = React.useState(false);
  const [reconnecting, setReconnecting] = React.useState(false);
  const [deciding, setDeciding] = React.useState(false);
  const [decisionFailure, setDecisionFailure] = React.useState<{ status: number; code: string | null } | null>(null);

  const stateRef = React.useRef(state);
  stateRef.current = state;
  const abortRef = React.useRef<AbortController | null>(null);
  const activeRunRef = React.useRef<string | null>(null);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  const streamRun = React.useCallback(async (runId: string) => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    activeRunRef.current = runId;
    let attempts = 0;
    let done = false;

    while (!done && !ac.signal.aborted) {
      // Resume from THIS run's cursor, never from zero.
      const since = stateRef.current.lastSeq[runId] ?? 0;
      try {
        const resp = await fetch(companionClient.streamUrl(runId, since), {
          headers: { Accept: "text/event-stream" },
          signal: ac.signal,
          cache: "no-store",
        });
        if (!resp.ok || !resp.body) throw new Error(`stream ${resp.status}`);
        setReconnecting(false);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        const parser = new SseParser();
        for (;;) {
          const { value, done: eof } = await reader.read();
          if (eof) break;
          for (const ev of parser.push(decoder.decode(value, { stream: true }))) {
            dispatch({ type: "event", runId, ev, now: Date.now() });
            if (ev.event === "run.completed") done = true;
          }
          if (done) break;
        }
      } catch {
        if (ac.signal.aborted) return;
      }
      if (done) break;
      attempts += 1;
      if (attempts > MAX_RECONNECTS) {
        dispatch({ type: "stream_failed", runId, detail: "network", now: Date.now() });
        break;
      }
      setReconnecting(true);
      await new Promise((r) => setTimeout(r, 400 * attempts));
    }

    setReconnecting(false);
    if (abortRef.current === ac) {
      abortRef.current = null;
      activeRunRef.current = null;
    }
  }, []);

  /**
   * Open a thread: enumerate its runs from the SERVER, replay their
   * history, then follow the live one. All three, in that order.
   *
   * The run list comes from `GET …/threads/{id}/runs` (§5.2, contract
   * v1.1). That is what makes the timeline belong to the thread rather
   * than to this browser, and therefore what makes `?companion=<thread>`
   * work when a teammate opens it on another machine: the conversation
   * rebuilds in full instead of appearing empty.
   *
   * `localStorage` is kept only as a **fallback for when that call
   * fails** — a degraded path, not the norm. On that path the timeline is
   * marked partial, because a run started elsewhere would be missing from
   * the cache and we must not imply we have the whole thread.
   */
  const openThread = React.useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      dispatch({ type: "reset" });
      setStatus("loading");
      setErrorDetail(null);
      setDecisionFailure(null);
      setThreadId(id);

      const listed = await companionClient.threadRuns(id);
      let runIds: string[];
      let lastServerStatus: string | null = null;

      if (listed.ok) {
        // Already ascending by `started_at` (§5.2) — concatenate in order.
        runIds = listed.data.runs.map((r) => r.run_id);
        lastServerStatus = listed.data.runs.at(-1)?.status ?? null;
        cacheRunIds(id, runIds);
        setPartial(false);
      } else if (listed.status === 404 || listed.status === 401 || listed.status === 403) {
        // Opaque 404 (not ours, or gone) is not a hole to paper over.
        setStatus("error");
        setErrorDetail(listed.detail);
        return;
      } else {
        runIds = loadRunIds(id);
        setPartial(true);
      }

      let failed = false;
      for (const runId of runIds) {
        const res = await companionClient.runEvents(runId, 0);
        if (!res.ok) {
          // A rotated-away or unknown run is a hole, not a failure of the
          // whole thread: keep going and mark the timeline partial.
          if (res.status === 404 || res.status === 410) setPartial(true);
          else failed = true;
          continue;
        }
        if (res.data.available_from !== null) setPartial(true);
        for (const ev of res.data.events) {
          dispatch({ type: "event", runId, ev, now: Date.now() });
        }
      }

      if (failed && runIds.length > 0) {
        setStatus("error");
        setErrorDetail("network");
        return;
      }
      setStatus("ready");

      // Attach to the last run only if it is still going. The server's own
      // status is more trustworthy than what the replay implies: a run
      // whose `run.completed` rotated out of the log would otherwise look
      // live forever.
      const last = runIds[runIds.length - 1];
      const stillRunning =
        lastServerStatus !== null ? lastServerStatus === "running" : stateRef.current.runStatus === "running";
      if (last && stillRunning) void streamRun(last);
    },
    [streamRun],
  );

  const refreshThreads = React.useCallback(async () => {
    const res = await companionClient.listThreads();
    if (!res.ok) {
      setStatus("error");
      setErrorDetail(res.detail);
      return [];
    }
    setThreads(res.data);
    return res.data;
  }, []);

  const send = React.useCallback(
    async (text: string, pageContext: PageContext | null, mode: "consult" | "build") => {
      let id = threadId;
      if (!id) {
        const created = await companionClient.createThread({
          mode,
          client_ref: pageContext?.client_ref ?? undefined,
        });
        if (!created.ok) {
          setStatus("error");
          setErrorDetail(created.detail);
          return;
        }
        id = created.data.id;
        setThreads((prev) => [created.data, ...prev]);
        setThreadId(id);
        setStatus("ready");
        setPartial(false);
      }

      const res = await companionClient.startRun(id, text, pageContext);
      if (!res.ok) {
        dispatch({ type: "stream_failed", runId: id, detail: res.detail, now: Date.now() });
        return;
      }
      const runId = res.data.run_id;
      rememberRunId(id, runId);
      dispatch({ type: "prompt", runId, text, now: Date.now() });
      void streamRun(runId);
    },
    [streamRun, threadId],
  );

  /** The ONLY cancellation. Aborting the stream would not reach the API. */
  const stop = React.useCallback(async () => {
    const runId = activeRunRef.current ?? stateRef.current.activeRun;
    if (!runId) return;
    await companionClient.cancelRun(runId);
  }, []);

  const decide = React.useCallback(
    async (actionId: string, decision: Decision, note?: string) => {
      const card = stateRef.current.items.find((i) => i.kind === "action" && i.id === actionId);
      // Resume is addressed to the run that is PAUSED — the one that asked.
      const runId = card?.runId ?? activeRunRef.current ?? stateRef.current.activeRun;
      if (!runId || !threadId) return;
      setDeciding(true);
      setDecisionFailure(null);
      const res = await companionClient.resumeRun(runId, { action_id: actionId, decision, note });
      setDeciding(false);
      if (!res.ok) {
        setDecisionFailure({ status: res.status, code: res.code });
        return;
      }
      // §4.3: the 202 carries a NEW run. Follow that one.
      rememberRunId(threadId, res.data.run_id);
      void streamRun(res.data.run_id);
    },
    [streamRun, threadId],
  );

  return {
    state,
    threads,
    threadId,
    status,
    errorDetail,
    partial,
    reconnecting,
    deciding,
    decisionFailure,
    setThreads,
    setThreadId,
    openThread,
    refreshThreads,
    send,
    stop,
    decide,
  } as const;
}

export type CompanionController = ReturnType<typeof useCompanion>;
export type { CompanionState };
