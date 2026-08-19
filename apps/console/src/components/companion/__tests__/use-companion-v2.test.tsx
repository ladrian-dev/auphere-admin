import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCompanion } from "../use-companion";

/**
 * The connection loop under the **pause** of §6 of CONTRACT-V2.
 *
 * The whole point of the 409 (and of it being a 409 and not a 429) is that
 * reaching the cap must not look like a failure and must not cost a second
 * request. Both of those are behaviours of this hook, not of a component,
 * and neither can be checked by reading the code.
 */
function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const fetchMock = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

/** The 409 exactly as §6.2 describes it: the snapshot travels in the body
 *  so the drawer needs no follow-up `GET /budget`. */
const PAUSED_409 = {
  code: "budget_paused",
  detail: "Companion budget exhausted",
  used: 2000000,
  cap: 2000000,
  period: "2026-08",
  resets_at: "2026-09-01T00:00:00Z",
};

function router(handlers: Array<[RegExp, () => Response]>) {
  return (url: string, init?: RequestInit) => {
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url}`;
    for (const [re, fn] of handlers) if (re.test(key)) return Promise.resolve(fn());
    throw new Error(`unrouted ${key}`);
  };
}

describe("useCompanion — 409 budget_paused (v2 §6.2)", () => {
  it("records the pause from the 409 body and makes NO second request for it", async () => {
    fetchMock.mockImplementation(
      router([
        // Most specific first: `POST …/threads` also prefixes
        // `POST …/threads/t1/runs`, so a looser rule listed above would
        // answer the run start with the thread it just created.
        [/POST \/api\/companion\/threads\/t1\/runs/, () => json(PAUSED_409, 409)],
        [/POST \/api\/companion\/threads$/, () => json({ id: "t1", mode: "consult" })],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.send("hola", null, "consult");
    });

    await waitFor(() => expect(result.current.state.paused).not.toBeNull());
    expect(result.current.state.paused).toMatchObject({
      used: 2000000,
      cap: 2000000,
      period: "2026-08",
      resetsAt: "2026-09-01T00:00:00Z",
    });
    // The snapshot came with the refusal; asking for it again would be
    // exactly the round trip the contract removed.
    const calls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(calls.filter((u) => u.includes("/api/companion/budget"))).toHaveLength(0);
  });

  it("is NOT an error: no error status, no red notice, no lost thread", async () => {
    fetchMock.mockImplementation(
      router([
        // Most specific first: `POST …/threads` also prefixes
        // `POST …/threads/t1/runs`, so a looser rule listed above would
        // answer the run start with the thread it just created.
        [/POST \/api\/companion\/threads\/t1\/runs/, () => json(PAUSED_409, 409)],
        [/POST \/api\/companion\/threads$/, () => json({ id: "t1", mode: "consult" })],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.send("hola", null, "consult");
    });

    await waitFor(() => expect(result.current.state.paused).not.toBeNull());
    // 409 and not 429 on purpose: retrying changes nothing, so this must
    // not travel the `stream_failed` path that paints a failure.
    expect(result.current.state.runStatus).not.toBe("error");
    expect(result.current.state.items.filter((i) => i.kind === "notice" && i.code === "error")).toHaveLength(0);
    // Nothing happened in the conversation, so nothing is added to it.
    expect(result.current.state.items).toHaveLength(0);
    // And the thread is still there.
    expect(result.current.threadId).toBe("t1");
  });

  it("a 409 that is NOT the pause still fails the way it used to", async () => {
    fetchMock.mockImplementation(
      router([
        [/POST \/api\/companion\/threads\/t1\/runs/, () => json({ code: "thread_archived", detail: "gone" }, 409)],
        [/POST \/api\/companion\/threads$/, () => json({ id: "t1", mode: "consult" })],
      ]),
    );

    const { result } = renderHook(() => useCompanion());
    await act(async () => {
      await result.current.send("hola", null, "consult");
    });

    await waitFor(() => expect(result.current.state.runStatus).toBe("error"));
    expect(result.current.state.paused).toBeNull();
  });
});
