import { afterEach, describe, expect, it, vi } from "vitest";

import { logRequestError, requestErrorRecord } from "@/lib/request-error-log";

const context = { routerKind: "App Router", routePath: "/(console)/reservas", routeType: "render" } as const;

/**
 * Spec 056 (10.2, `contracts/events.md` §5): what the console writes when a
 * request fails on the server — the digest the error page shows, the route and
 * the cause's code. Never `error.message` (it carries the API URL and a slice
 * of its body), headers or cookies.
 */
describe("console.request_error", () => {
  afterEach(() => vi.restoreAllMocks());

  it("a network failure says its code, never its message", () => {
    const error = Object.assign(new TypeError("fetch failed: https://api.staging/console/lite/reservas?token=SECRET"), {
      digest: "3141592653",
      cause: { code: "UND_ERR_CONNECT_TIMEOUT" },
    });
    const record = requestErrorRecord(error, context);
    expect(record).toEqual({
      event: "console.request_error",
      digest: "3141592653",
      route: "/(console)/reservas",
      route_type: "render",
      cause_code: "UND_ERR_CONNECT_TIMEOUT",
    });
    expect(JSON.stringify(record)).not.toContain("SECRET");
    expect(JSON.stringify(record)).not.toContain("fetch failed");
  });

  it("the API's answer is its status; anything else, its kind", () => {
    const backend = Object.assign(new Error("Backend 503 at https://api/x: {detail}"), { status: 503 });
    expect(requestErrorRecord(backend, context).cause_code).toBe("http_503");
    const timeout = new DOMException("The operation was aborted due to timeout", "TimeoutError");
    expect(requestErrorRecord(timeout, context).cause_code).toBe("TimeoutError");
    expect(requestErrorRecord("a string thrown", context)).toMatchObject({ digest: null, cause_code: "unknown" });
  });

  it("goes out as one JSON line on the server's error output", () => {
    const write = vi.spyOn(console, "error").mockImplementation(() => undefined);
    logRequestError(Object.assign(new Error("secret body"), { digest: "d1" }), context);
    expect(write).toHaveBeenCalledTimes(1);
    const line = write.mock.calls[0]![0] as string;
    expect(JSON.parse(line)).toMatchObject({ event: "console.request_error", digest: "d1", cause_code: "Error" });
    expect(line).not.toContain("secret body");
  });
});
