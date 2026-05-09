/**
 * SSE proxy → FastAPI ``/admin/tenants/:tenant_id/conversations/stream``.
 *
 * Block H wires the live indicator on
 * ``/tenants/[id]/conversations`` to the real backend stream. The
 * backend already emits SSE (block B); the panel hits this route
 * which:
 *
 *  1. Validates the Better Auth session (server-side only).
 *  2. Forwards to the FastAPI URL with the static admin Bearer token.
 *  3. Streams the response body back to the browser unchanged so
 *     ``EventSource`` parses ``event:`` + ``data:`` lines as-is.
 *
 * Vercel Hobby limits SSE to ~5 minutes; the LiveIndicator already
 * degrades to a polling badge on ``error``. When we move to Pro/Edge
 * we can lift the cap.
 *
 * NEVER reach this route from a client that already has a session
 * cookie — the route adds the bearer for the BACKEND auth, not the
 * panel auth. ``Authorization: Bearer NEXUS_ADMIN_TOKEN`` must NEVER
 * leak to the browser.
 */

import { NextRequest } from "next/server";

import { auth } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8000";
const ADMIN_TOKEN = process.env.NEXUS_ADMIN_TOKEN ?? "dev-admin-token-change-me";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(request: NextRequest) {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) {
    return new Response("unauthorized", { status: 401 });
  }

  const tenantId = request.nextUrl.searchParams.get("tenant_id");
  if (!tenantId || !UUID_RE.test(tenantId)) {
    return new Response("missing or invalid tenant_id", { status: 400 });
  }

  const target = `${BACKEND_URL}/admin/tenants/${tenantId}/conversations/stream`;
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      headers: {
        Authorization: `Bearer ${ADMIN_TOKEN}`,
        Accept: "text/event-stream",
      },
      // Disable response buffering — SSE needs streaming.
      cache: "no-store",
      // ``signal`` propagates client disconnection upstream.
      signal: request.signal,
    });
  } catch (err) {
    return new Response(`upstream fetch failed: ${(err as Error).message}`, {
      status: 502,
    });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response(
      `backend returned ${upstream.status}`,
      { status: upstream.status === 404 ? 404 : 502 },
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Vercel-specific hint to disable buffering when running on Edge.
      "X-Accel-Buffering": "no",
    },
  });
}
