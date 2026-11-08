import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/env", () => ({ env: () => ({ NEXUS_BACKEND_URL: "http://api.test" }) }));
vi.mock("@/lib/jwt", () => ({ mintServiceToken: async () => "svc", mintPrincipalToken: async () => "p" }));
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

const { consoleService } = await import("@/lib/backend");

const principal = { user_id: "u", email: "x@y.test", access: "ok" };
const ok = () =>
  new Response(JSON.stringify({ principal, expires_at: "2026-11-14T10:00:00Z" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
const status = (code: number) => new Response(JSON.stringify({ detail: "x" }), { status: code });

/**
 * Spec 056 (10.2): the session lookup runs on EVERY console request (the root
 * layout reads the principal). The Reservas failure of 2026-11-06 left no trace;
 * one of its candidates was this call: no time limit and every error but 401
 * thrown at once. Now: one retry for a network failure, a timeout or a 5xx,
 * within a time limit; a 401 is still «no session», and a 4xx is not retried.
 * It also carries when the session ends (spec 056, 15.1).
 */
describe("consoleService.session", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("answers the principal with when the session ends, under a time limit", async () => {
    fetchMock.mockResolvedValueOnce(ok());
    expect(await consoleService.session("tok")).toEqual({ ...principal, session_expires_at: "2026-11-14T10:00:00Z" });
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("a network failure once is retried, and the second answer is the one", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed")).mockResolvedValueOnce(ok());
    expect(await consoleService.session("tok")).toMatchObject({ user_id: "u" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a timeout once is retried", async () => {
    fetchMock.mockRejectedValueOnce(new DOMException("The operation was aborted due to timeout", "TimeoutError")).mockResolvedValueOnce(ok());
    expect(await consoleService.session("tok")).toMatchObject({ user_id: "u" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a 502 once is retried; twice, it is thrown", async () => {
    fetchMock.mockResolvedValueOnce(status(502)).mockResolvedValueOnce(ok());
    expect(await consoleService.session("tok")).toMatchObject({ user_id: "u" });
    fetchMock.mockReset();
    fetchMock.mockResolvedValueOnce(status(503)).mockResolvedValueOnce(status(503));
    await expect(consoleService.session("tok")).rejects.toMatchObject({ status: 503 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a 401 is no session, and a 4xx is not retried", async () => {
    fetchMock.mockResolvedValueOnce(status(401));
    expect(await consoleService.session("tok")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fetchMock.mockReset();
    fetchMock.mockResolvedValueOnce(status(422));
    await expect(consoleService.session("tok")).rejects.toMatchObject({ status: 422 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
