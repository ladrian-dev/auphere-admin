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

/** FastAPI `detail` may be a string or an object carrying `code`. */
function describe(err: BackendError): { detail: string; code: string | null } {
  const body = err.body as { detail?: unknown } | null;
  const detail = body && typeof body === "object" ? body.detail : null;
  if (typeof detail === "string") return { detail, code: null };
  if (detail && typeof detail === "object") {
    const d = detail as { code?: unknown; detail?: unknown; message?: unknown };
    return {
      detail: typeof d.detail === "string" ? d.detail : typeof d.message === "string" ? d.message : err.message,
      code: typeof d.code === "string" ? d.code : null,
    };
  }
  return { detail: err.detail, code: null };
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
      const { detail, code } = describe(err);
      return json(err.status, code ? { detail, code } : { detail });
    }
    // Never leak a stack to the browser; the digest is in the server log.
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
