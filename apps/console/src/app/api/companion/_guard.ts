import { BackendError, backendFor } from "@/lib/backend";
import { can, resolvePrincipal } from "@/lib/principal";

/**
 * Shared gate of the Companion BFF (CO-03).
 *
 * The drawer lives in the console SHELL, not in a route, so its calls are
 * `fetch` from the browser rather than server actions — see D1 of
 * `docs/companion/PLAN-CO-03.md`. What must not change between the two
 * patterns is the security shape, and it does not: the principal is
 * resolved on the server, `companion:use` is checked, and a fresh 60-second
 * EdDSA token is minted per call. The browser never holds a backend
 * credential.
 *
 * Errors are forwarded with their status AND their `detail.code` when the
 * API sends one. The drawer needs to tell 409 `action_expired` ("you ran
 * out of time") from 412 `state_changed` ("someone changed this while you
 * were deciding") — §4.2 says they are different causes and the UI paints
 * them differently.
 */
export type Backend = ReturnType<typeof backendFor>;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

/**
 * FastAPI `detail` may be a string or an object carrying `code`.
 *
 * `extra` is everything else the object carried, and it is forwarded on
 * purpose. §6.2 of CONTRACT-V2 puts the budget snapshot inside the 409
 * `budget_paused` body — `{code, used, cap, period, resets_at}` —
 * specifically **so the drawer can explain the pause without a second
 * request**. Reducing the body to `{detail, code}`, as this did before,
 * silently threw that snapshot away and would have forced the extra
 * `GET /budget` the contract says is unnecessary.
 *
 * Only own enumerable keys of an object `detail` travel, and `detail` and
 * `message` are consumed rather than repeated.
 */
function describe(err: BackendError): { detail: string; code: string | null; extra: Record<string, unknown> } {
  const body = err.body as { detail?: unknown } | null;
  const detail = body && typeof body === "object" ? body.detail : null;
  if (typeof detail === "string") return { detail, code: null, extra: {} };
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    const extra: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(d)) {
      // `detail`, `message` and `code` are consumed into their own fields
      // below; everything else travels so the drawer can read it.
      if (k !== "detail" && k !== "message" && k !== "code") extra[k] = v;
    }
    return {
      detail: typeof d.detail === "string" ? d.detail : typeof d.message === "string" ? d.message : err.message,
      code: typeof d.code === "string" ? d.code : null,
      extra,
    };
  }
  return { detail: err.detail, code: null, extra: {} };
}

export async function withCompanion(fn: (backend: Backend) => Promise<unknown>): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, { detail: "Not signed in" });
  if (!can(res.principal.role, "companion:use")) {
    return json(403, { detail: "Missing permission companion:use" });
  }
  try {
    const data = await fn(backendFor(res.principal));
    if (data === null || data === undefined) return new Response(null, { status: 204 });
    return json(200, data);
  } catch (err) {
    if (err instanceof BackendError) {
      const { detail, code, extra } = describe(err);
      return json(err.status, code ? { ...extra, detail, code } : { ...extra, detail });
    }
    // Never leak a stack to the browser; the digest is in the server log.
    if (process.env.NODE_ENV !== "production") console.error("companion bff", err);
    return json(502, { detail: "The Companion service is unavailable" });
  }
}

/**
 * The same gate WITHOUT the `companion:use` check.
 *
 * Used by exactly one route: the per-partner flag of §10 of CONTRACT-V2.
 * The two questions are different and must not be collapsed — "your role
 * cannot use the Companion" is answered by CO-03 with a disabled bubble
 * and an explanation, while "this partner does not have the Companion"
 * means the bubble is never mounted at all. Requiring the permission here
 * would turn the second into the first for every analyst.
 *
 * Still a signed-in principal, still a fresh 60-second token per call,
 * still no backend credential in the browser.
 */
export async function withPrincipal(fn: (backend: Backend) => Promise<unknown>): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, { detail: "Not signed in" });
  try {
    const data = await fn(backendFor(res.principal));
    if (data === null || data === undefined) return new Response(null, { status: 204 });
    return json(200, data);
  } catch (err) {
    if (err instanceof BackendError) {
      const { detail, code, extra } = describe(err);
      return json(err.status, code ? { ...extra, detail, code } : { ...extra, detail });
    }
    if (process.env.NODE_ENV !== "production") console.error("companion bff", err);
    return json(502, { detail: "The Companion service is unavailable" });
  }
}

/** Parse a JSON body without letting a malformed one become a 500. */
export async function readJson(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const parsed: unknown = await request.json();
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export const badRequest = (detail: string): Response => json(422, { detail });
