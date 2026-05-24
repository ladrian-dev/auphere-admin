/**
 * Bloque C — SSE proxy → FastAPI
 * ``/admin/tenants/:tenant_id/conversations/:conv_id/stream``.
 *
 * Per-conversation live event stream (new messages, agent toggle).
 * Mirrors the per-tenant stream proxy in ``api/conversations/stream``
 * but path-scopes to a single conversation so the detail view
 * receives only its own events without filtering on the client.
 *
 * Auth: Better Auth session is validated server-side; the admin
 * Bearer token is injected here and never reaches the browser.
 */

import { NextRequest } from "next/server";

import { auth } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8000";
const ADMIN_TOKEN = process.env.NEXUS_ADMIN_TOKEN ?? "dev-admin-token-change-me";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ conv_id: string }> },
) {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) {
    return new Response("unauthorized", { status: 401 });
  }

  const { conv_id } = await params;
  const tenantId = request.nextUrl.searchParams.get("tenant_id");
  if (!tenantId || !UUID_RE.test(tenantId)) {
    return new Response("missing or invalid tenant_id", { status: 400 });
  }
  if (!UUID_RE.test(conv_id)) {
    return new Response("invalid conversation id", { status: 400 });
  }

  const target = `${BACKEND_URL}/admin/tenants/${tenantId}/conversations/${conv_id}/stream`;
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      headers: {
        Authorization: `Bearer ${ADMIN_TOKEN}`,
        Accept: "text/event-stream",
      },
      cache: "no-store",
      signal: request.signal,
    });
  } catch (err) {
    return new Response(`upstream fetch failed: ${(err as Error).message}`, {
      status: 502,
    });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response(`backend returned ${upstream.status}`, {
      status: upstream.status === 404 ? 404 : 502,
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
