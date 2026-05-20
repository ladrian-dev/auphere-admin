/**
 * BFF proxy: ``GET /api/qa/threads/{threadId}/stream`` (ADR-021 Fase 1).
 *
 * Streams the backend's SSE response from
 * ``GET /qa/threads/{threadId}/stream?run_id=&since_seq=`` straight
 * through to the browser. The browser opens this via ``EventSource``.
 *
 * Why a separate proxy route (vs ``EventSource`` directly to the
 * backend): the admin Bearer must NEVER leak to the browser. This
 * route adds the Bearer + the operator id from the Better Auth
 * session, then streams the body unchanged.
 *
 * Vercel Hobby caps SSE around 5 minutes. A QA turn closes inside
 * 60s typical; the qa-runtime client reconnects with ``since_seq``
 * if the connection drops. Same pattern as
 * ``app/api/conversations/stream/route.ts``.
 */
import { NextRequest } from "next/server";

import { QAForbidden, requireQAOperator } from "@/lib/qa-access";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8000";
const ADMIN_TOKEN =
  process.env.NEXUS_ADMIN_TOKEN ?? "dev-admin-token-change-me";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ threadId: string }> },
) {
  let access;
  try {
    access = await requireQAOperator();
  } catch (err) {
    if (err instanceof QAForbidden) {
      return new Response(err.reason, { status: err.status });
    }
    throw err;
  }

  const { threadId } = await context.params;
  if (!UUID_RE.test(threadId)) {
    return new Response("invalid threadId", { status: 400 });
  }

  const runId = request.nextUrl.searchParams.get("run_id");
  if (!runId || !UUID_RE.test(runId)) {
    return new Response("missing or invalid run_id", { status: 400 });
  }
  const sinceSeq = request.nextUrl.searchParams.get("since_seq") ?? "0";

  const target = new URL(`${BACKEND_URL}/qa/threads/${threadId}/stream`);
  target.searchParams.set("run_id", runId);
  target.searchParams.set("since_seq", sinceSeq);

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), {
      headers: {
        Authorization: `Bearer ${ADMIN_TOKEN}`,
        "X-Operator-Id": access.operatorId,
        Accept: "text/event-stream",
      },
      // Pass the client's abort signal through so closing the
      // browser EventSource tears down the upstream request.
      signal: request.signal,
      cache: "no-store",
    });
  } catch (err) {
    return new Response(
      `upstream connect failed: ${err instanceof Error ? err.message : String(err)}`,
      { status: 502 },
    );
  }

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return new Response(text || `upstream ${upstream.status}`, {
      status: upstream.status,
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
