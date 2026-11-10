/**
 * Spec 056 (10.2, `contracts/events.md` §5): the line the console writes when a
 * request fails on the server, `console.request_error`. The Reservas failure of
 * 2026-11-06 left nothing: the error page showed Next's sentence and Vercel's
 * logs were gone within the hour. Now the error page's `digest` has its line,
 * with the route and what caused it.
 *
 * Only these fields, on purpose: `error.message` carries the API URL and a slice
 * of its body (`BackendError`), and the request's headers carry the session
 * cookie. Pure, so it is tested without Next (`instrumentation.ts` calls it).
 */
export type RequestErrorContext = { routePath: string; routeType: string };

export type RequestErrorRecord = {
  event: "console.request_error";
  digest: string | null;
  route: string;
  route_type: string;
  cause_code: string;
};

function field(value: unknown, name: string): unknown {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>)[name] : undefined;
}

/** What caused it, as a code: the network's (`ECONNRESET`), the API's status (`http_503`) or the error's kind. */
function causeCode(error: unknown): string {
  const code = field(field(error, "cause"), "code");
  if (typeof code === "string" && code) return code;
  const status = field(error, "status");
  if (typeof status === "number") return `http_${status}`;
  const name = field(error, "name");
  return typeof name === "string" && name ? name : "unknown";
}

export function requestErrorRecord(error: unknown, context: RequestErrorContext): RequestErrorRecord {
  const digest = field(error, "digest");
  return {
    event: "console.request_error",
    digest: typeof digest === "string" ? digest : null,
    route: context.routePath,
    route_type: context.routeType,
    cause_code: causeCode(error),
  };
}

export function logRequestError(error: unknown, context: RequestErrorContext): void {
  console.error(JSON.stringify(requestErrorRecord(error, context)));
}
