import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadRunIds, rememberRunId } from "../client";
import { useCompanion } from "../use-companion";
import * as f from "./fixtures";

/**
 * The connection loop: correction C1 and §§4.3 / 5.2 of the contract.
 *
 * These are the behaviours that cannot be checked by reading the code and
 * that cost the most when wrong: where the run index comes from, which run
 * the drawer follows after a `resume`, and what actually cancels work.
 */
type WireEvent = ReturnType<typeof f.ev>;

function sseBody(events: WireEvent[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const text = events.map((e) => `id: ${e.seq}\nevent: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join("");
  return new ReadableStream({
    start(controller) {
      controller.enqueue(enc.encode(text));
      controller.close();
    },
  });
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function stream(events: WireEvent[]): Response {
  return new Response(sseBody(events), { status: 200, headers: { "content-type": "text/event-stream" } });
}

const fetchMock = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

/**
 * Route by `METHOD url`, not by url alone: `/threads/{id}/runs` serves the
 * run listing on GET and starts a run on POST, so a url-only matcher would
 * silently answer one with the other.
 */
function router(handlers: Array<[RegExp, () => Response]>) {
  return (url: string, init?: RequestInit) => {
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url}`;
    for (const [re, fn] of handlers) if (re.test(key)) return Promise.resolve(fn());
    throw new Error(`unrouted ${key}`);
  };
}

const eventsOf = (runId: string, events: WireEvent[]) =>
  json({ run_id: runId, events, next_seq: events.length + 1, available_from: null });

describe("useCompanion — the run index comes from the server (§5.2)", () => {
  it("enumerates the thread's runs over HTTP and replays them in order", async () => {
    fetchMock.mockImplementation(
      router([
        [/GET \/api\/companion\/threads\/t1\/runs/, () => json(f.threadRuns("t1", [{ run_id: "run-a" }, { run_id: "run-b" }]))],
        [/\/runs\/run-a\/events/, () => eventsOf("run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "de A"), f.runCompleted(3, "run-a")])],
        [/\/runs\/run-b\/events/, () => eventsOf("run-b", [f.runStarted(1, "run-b"), f.textDelta(2, "de B"), f.runCompleted(3, "run-b")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t1");
    });

    await waitFor(() => expect(result.current.status).toBe("ready"));
    const texts = result.current.state.items.filter((i) => i.kind === "assistant").map((i) => (i.kind === "assistant" ? i.text : ""));
    expect(texts).toEqual(["de A", "de B"]);
    expect(result.current.partial).toBe(false);
    // …and the server's answer refreshes the cache.
    expect(loadRunIds("t1")).toEqual(["run-a", "run-b"]);
  });

  it("rebuilds a SHARED thread in full on a machine that has never seen it", async () => {
    // This is the whole point of §5.2: `?companion=<thread>` opened by a
    // teammate. `localStorage` is empty here, and the timeline must still
    // be complete — NOT the partial state.
    expect(loadRunIds("t-shared")).toEqual([]);
    fetchMock.mockImplementation(
      router([
        [/GET \/api\/companion\/threads\/t-shared\/runs/, () => json(f.threadRuns("t-shared", [{ run_id: "run-x" }]))],
        [/\/runs\/run-x\/events/, () => eventsOf("run-x", [f.runStarted(1, "run-x"), f.textDelta(2, "conversación completa"), f.runCompleted(3, "run-x")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t-shared");
    });

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.partial).toBe(false);
    expect(result.current.state.items.find((i) => i.kind === "assistant")).toMatchObject({ text: "conversación completa" });
  });

  it("attaches to the live run when the SERVER says it is still running", async () => {
    fetchMock.mockImplementation(
      router([
        [/GET \/api\/companion\/threads\/t1\/runs/, () => json(f.threadRuns("t1", [{ run_id: "run-a", status: "running" }]))],
        [/\/runs\/run-a\/events/, () => eventsOf("run-a", [f.runStarted(1, "run-a")])],
        [/\/runs\/run-a\/stream/, () => stream([f.textDelta(2, "sigo aquí"), f.runCompleted(3, "run-a")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t1");
    });
    await waitFor(() => expect(result.current.state.runStatus).toBe("completed"));
    expect(result.current.state.items.find((i) => i.kind === "assistant")).toMatchObject({ text: "sigo aquí" });
  });

  it("does NOT attach when the server says the run finished, even if the replay looks live", async () => {
    // A run whose `run.completed` rotated out of the log would otherwise
    // look alive forever and hold an open stream for nothing.
    fetchMock.mockImplementation(
      router([
        [/GET \/api\/companion\/threads\/t1\/runs/, () => json(f.threadRuns("t1", [{ run_id: "run-a", status: "completed" }]))],
        [/\/runs\/run-a\/events/, () => eventsOf("run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "sin cierre")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t1");
    });
    expect(result.current.status).toBe("ready");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/stream"))).toBe(false);
  });
});

describe("useCompanion — the degraded path (cache, not norm)", () => {
  it("falls back to the cached index when the listing fails, and says the thread is partial", async () => {
    rememberRunId("t1", "run-a");
    fetchMock.mockImplementation(
      router([
        [/GET \/api\/companion\/threads\/t1\/runs/, () => json({ detail: "boom" }, 500)],
        [/\/runs\/run-a\/events/, () => eventsOf("run-a", [f.runStarted(1, "run-a"), f.textDelta(2, "lo que vi antes"), f.runCompleted(3, "run-a")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t1");
    });

    await waitFor(() => expect(result.current.status).toBe("ready"));
    // What this browser saw is shown…
    expect(result.current.state.items.find((i) => i.kind === "assistant")).toMatchObject({ text: "lo que vi antes" });
    // …but completeness is not claimed.
    expect(result.current.partial).toBe(true);
  });

  it("shows an empty, partial thread when the listing fails and nothing is cached", async () => {
    fetchMock.mockImplementation(router([[/GET \/api\/companion\/threads\/t1\/runs/, () => json({ detail: "offline" }, 502)]]));
    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t1");
    });
    expect(result.current.status).toBe("ready");
    expect(result.current.partial).toBe(true);
    expect(result.current.state.items).toHaveLength(0);
  });

  it("treats an opaque 404 as an error, not as a hole to paper over", async () => {
    fetchMock.mockImplementation(router([[/GET \/api\/companion\/threads\/t-foreign\/runs/, () => json({ detail: "Not found" }, 404)]]));
    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t-foreign");
    });
    expect(result.current.status).toBe("error");
    expect(result.current.partial).toBe(false);
  });

  it("marks PARTIAL when a run's log rotated past the requested cursor", async () => {
    fetchMock.mockImplementation(
      router([
        [/GET \/api\/companion\/threads\/t1\/runs/, () => json(f.threadRuns("t1", [{ run_id: "run-a" }]))],
        [/\/runs\/run-a\/events/, () => json({ run_id: "run-a", events: [f.textDelta(40, "cola")], next_seq: 41, available_from: 38 })],
      ]),
    );
    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.openThread("t1");
    });
    expect(result.current.partial).toBe(true);
  });
});

describe("useCompanion — sending a turn", () => {
  it("remembers the run id and follows its stream", async () => {
    fetchMock.mockImplementation(
      router([
        [/POST \/api\/companion\/threads\/t1\/runs/, () => json({ run_id: "run-1", thread_id: "t1", status: "running" })],
        [/\/runs\/run-1\/stream/, () => stream([f.runStarted(1, "run-1"), f.textDelta(2, "hola"), f.runCompleted(3, "run-1")])],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    act(() => result.current.setThreadId("t1"));
    await act(async () => {
      await result.current.send("¿qué tal?", null, "consult");
    });

    await waitFor(() => expect(result.current.state.runStatus).toBe("completed"));
    expect(loadRunIds("t1")).toEqual(["run-1"]);
    expect(result.current.state.items.find((i) => i.kind === "user")).toMatchObject({ text: "¿qué tal?" });
    expect(result.current.state.items.find((i) => i.kind === "assistant")).toMatchObject({ text: "hola" });
  });
});

describe("useCompanion — stopping", () => {
  it("calls DELETE, because aborting the stream would not reach the API", async () => {
    fetchMock.mockImplementation(
      router([
        [/POST \/api\/companion\/threads\/t1\/runs/, () => json({ run_id: "run-1", thread_id: "t1", status: "running" })],
        [/\/runs\/run-1\/stream/, () => stream([f.runStarted(1, "run-1")])],
        [/DELETE \/api\/companion\/runs\/run-1$/, () => new Response(null, { status: 204 })],
      ]),
    );
    const { result } = renderHook(() => useCompanion());
    act(() => result.current.setThreadId("t1"));
    await act(async () => {
      await result.current.send("largo", null, "consult");
    });
    await act(async () => {
      await result.current.stop();
    });

    const deleteCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "DELETE");
    expect(deleteCall?.[0]).toBe("/api/companion/runs/run-1");
  });
});

describe("useCompanion — resuming a confirmation (§4.3)", () => {
  it("attaches to the NEW run returned by the 202, not the paused one", async () => {
    fetchMock.mockImplementation(
      router([
        [/POST \/api\/companion\/threads\/t1\/runs/, () => json({ run_id: "run-a", thread_id: "t1", status: "running" })],
        [/\/runs\/run-a\/stream/, () => stream([f.runStarted(1, "run-a"), f.hitlRequested(2)])],
        [/POST \/api\/companion\/runs\/run-a\/resume/, () => json({ run_id: "run-b", thread_id: "t1", action_id: "9c1e", status: "confirmed" })],
        [
          /\/runs\/run-b\/stream/,
          () => stream([f.hitlResolved(1), f.verifyResult(2, "9c1e", true), f.textDelta(3, "hecho"), f.runCompleted(4, "run-b")]),
        ],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    act(() => result.current.setThreadId("t1"));
    await act(async () => {
      await result.current.send("publica la v8", null, "build");
    });
    await waitFor(() => expect(result.current.state.items.some((i) => i.kind === "action")).toBe(true));

    await act(async () => {
      await result.current.decide("9c1e", "confirm");
    });

    // The resume is addressed to the PAUSED run…
    expect(fetchMock.mock.calls.some(([url]) => String(url) === "/api/companion/runs/run-a/resume")).toBe(true);
    // …and the drawer then follows the NEW one.
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/runs/run-b/stream"))).toBe(true));
    await waitFor(() => expect(result.current.state.runStatus).toBe("completed"));

    const action = result.current.state.items.find((i) => i.kind === "action");
    expect(action).toMatchObject({ state: "resolved", decision: "confirm" });
    expect(result.current.state.items.filter((i) => i.kind === "action")).toHaveLength(1);
    expect(loadRunIds("t1")).toEqual(["run-a", "run-b"]);
  });

  it("surfaces a 412 without sealing the card, so the user can be told why", async () => {
    fetchMock.mockImplementation(
      router([
        [/POST \/api\/companion\/threads\/t1\/runs/, () => json({ run_id: "run-a", thread_id: "t1", status: "running" })],
        [/\/runs\/run-a\/stream/, () => stream([f.runStarted(1, "run-a"), f.hitlRequested(2)])],
        [/POST \/api\/companion\/runs\/run-a\/resume/, () => json({ detail: "drift", code: "state_changed" }, 412)],
      ]),
    );
    const { result } = renderHook(() => useCompanion());
    act(() => result.current.setThreadId("t1"));
    await act(async () => {
      await result.current.send("publica", null, "build");
    });
    await waitFor(() => expect(result.current.state.items.some((i) => i.kind === "action")).toBe(true));

    await act(async () => {
      await result.current.decide("9c1e", "confirm");
    });

    expect(result.current.decisionFailure).toEqual({ status: 412, code: "state_changed" });
    expect(result.current.state.items.find((i) => i.kind === "action")).toMatchObject({ state: "pending" });
  });
});
