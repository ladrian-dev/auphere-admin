import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_WIDTH,
  MAX_WIDTH,
  MIN_WIDTH,
  cacheRunIds,
  clampWidth,
  companionClient,
  loadMode,
  loadRunIds,
  loadWidth,
  rememberRunId,
  saveMode,
  saveWidth,
} from "../client";

describe("width persistence", () => {
  beforeEach(() => window.localStorage.clear());

  it("falls back to the default when nothing is stored", () => {
    expect(loadWidth()).toBe(DEFAULT_WIDTH);
  });

  it("clamps out-of-range values in both directions", () => {
    expect(clampWidth(10)).toBe(MIN_WIDTH);
    expect(clampWidth(99_999)).toBe(MAX_WIDTH);
    saveWidth(99_999);
    expect(loadWidth()).toBe(MAX_WIDTH);
  });

  it("ignores a corrupted value instead of rendering a broken drawer", () => {
    window.localStorage.setItem("nexus.companion.width", "not a number");
    expect(loadWidth()).toBe(DEFAULT_WIDTH);
  });
});

describe("mode persistence", () => {
  beforeEach(() => window.localStorage.clear());

  it("defaults to consult — safe by omission, read-only tools", () => {
    expect(loadMode()).toBe("consult");
    window.localStorage.setItem("nexus.companion.mode", "garbage");
    expect(loadMode()).toBe("consult");
  });

  it("round-trips build", () => {
    saveMode("build");
    expect(loadMode()).toBe("build");
  });
});

describe("run index (a CACHE — the server is the source, §5.2)", () => {
  beforeEach(() => window.localStorage.clear());

  it("cacheRunIds overwrites with what the server said is authoritative", () => {
    rememberRunId("t1", "stale-a");
    rememberRunId("t1", "stale-b");
    cacheRunIds("t1", ["run-x", "run-y", "run-z"]);
    // Not merged with the stale entries — replaced.
    expect(loadRunIds("t1")).toEqual(["run-x", "run-y", "run-z"]);
  });

  it("cacheRunIds stays bounded", () => {
    cacheRunIds("t1", Array.from({ length: 60 }, (_, i) => `run-${i}`));
    const ids = loadRunIds("t1");
    expect(ids).toHaveLength(40);
    expect(ids.at(-1)).toBe("run-59");
  });

  it("keeps run ids in order and never duplicates", () => {
    rememberRunId("t1", "run-a");
    rememberRunId("t1", "run-b");
    rememberRunId("t1", "run-a");
    expect(loadRunIds("t1")).toEqual(["run-a", "run-b"]);
  });

  it("keeps threads separate", () => {
    rememberRunId("t1", "run-a");
    rememberRunId("t2", "run-z");
    expect(loadRunIds("t1")).toEqual(["run-a"]);
    expect(loadRunIds("t2")).toEqual(["run-z"]);
  });

  it("is bounded so a long thread cannot grow the key forever", () => {
    for (let i = 0; i < 60; i += 1) rememberRunId("t1", `run-${i}`);
    const ids = loadRunIds("t1");
    expect(ids).toHaveLength(40);
    expect(ids.at(-1)).toBe("run-59");
  });

  it("returns an empty list for a thread it has never seen — the partial state", () => {
    expect(loadRunIds("unknown")).toEqual([]);
  });

  it("survives corrupted JSON", () => {
    window.localStorage.setItem("nexus.companion.runs.t1", "{not json");
    expect(loadRunIds("t1")).toEqual([]);
  });
});

describe("companionClient", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  function respond(status: number, body: unknown): Response {
    return new Response(body === null ? null : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }

  it("stops a run through DELETE — never by aborting the stream", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const res = await companionClient.cancelRun("run-a");
    expect(res.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith("/api/companion/runs/run-a", expect.objectContaining({ method: "DELETE" }));
  });

  it("carries detail.code through so 409 and 412 stay tellable apart (§4.2)", async () => {
    fetchMock.mockResolvedValue(respond(409, { detail: "expired", code: "action_expired" }));
    const res = await companionClient.resumeRun("run-a", { action_id: "9c1e", decision: "confirm" });
    expect(res).toMatchObject({ ok: false, status: 409, code: "action_expired" });

    fetchMock.mockResolvedValue(respond(412, { detail: "drift", code: "state_changed" }));
    const stale = await companionClient.resumeRun("run-a", { action_id: "9c1e", decision: "confirm" });
    expect(stale).toMatchObject({ ok: false, status: 412, code: "state_changed" });
  });

  it("never throws on a network failure — the drawer must not take the shell down", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    await expect(companionClient.listThreads()).resolves.toMatchObject({ ok: false, status: 0, detail: "network" });
  });

  it("sends page_context with the turn (correction C4)", async () => {
    fetchMock.mockResolvedValue(respond(200, { run_id: "r", thread_id: "t", status: "running" }));
    await companionClient.startRun("t1", "hola", {
      route: "/clients/boreal/agent",
      client_ref: "boreal",
      tab: "agent",
      selection: null,
    });
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      prompt: "hola",
      page_context: { route: "/clients/boreal/agent", client_ref: "boreal" },
    });
    // The API accepts no tenant id, and neither does this client.
    expect(JSON.stringify(body)).not.toContain("tenant_id");
    expect(JSON.stringify(body)).not.toContain("partner_id");
  });

  it("resumes from a run's own cursor in the stream URL", () => {
    expect(companionClient.streamUrl("run-a", 42)).toBe("/api/companion/runs/run-a/stream?since_seq=42");
  });

  it("lists a thread's runs with a plain GET (§5.2)", async () => {
    fetchMock.mockResolvedValue(
      respond(200, { thread_id: "t1", runs: [{ run_id: "run-a", status: "completed", started_at: "2026-08-18T14:00:00Z", ended_at: null }] }),
    );
    const res = await companionClient.threadRuns("t1");
    expect(res.ok && res.data.runs[0]?.run_id).toBe("run-a");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/companion/threads/t1/runs");
    expect((init as RequestInit | undefined)?.method).toBeUndefined();
  });
});
