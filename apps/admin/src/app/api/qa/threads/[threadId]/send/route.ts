/**
 * Proxy: ``POST /api/qa/threads/{threadId}/send`` (ADR-020 Fase 5 closure).
 *
 * Forwards the composer's message to the FastAPI ``/qa/threads/{id}/send``
 * endpoint, which:
 *   1. Auto-seeds (customer, conversation, channel) on first call.
 *   2. Persists the inbound ``messages`` row.
 *   3. Fires the agent run on the qa-langgraph-server.
 *   4. Returns the final UCM + response + intent + tool_calls.
 *
 * The browser never sees the admin Bearer; the BFF stamps it and
 * the operator id from the Better Auth session.
 *
 * Timeout: the underlying SSE drain can take 30-60s on a Sonnet
 * 4.6 turn. We set the fetch deadline to 90s to leave slack — the
 * backend itself caps at ``settings.qa_langgraph_run_timeout_s``.
 */
import { NextResponse } from "next/server";

import { QAForbidden, requireQAOperator } from "@/lib/qa-access";
import { QAApiError, qaApi } from "@/lib/qa-api";

const SEND_TIMEOUT_MS = 90_000;

export async function POST(
  req: Request,
  context: { params: Promise<{ threadId: string }> },
) {
  let access;
  try {
    access = await requireQAOperator();
  } catch (err) {
    if (err instanceof QAForbidden) {
      return NextResponse.json(
        { detail: err.reason, role: err.role },
        { status: err.status },
      );
    }
    throw err;
  }
  const { threadId } = await context.params;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { detail: "invalid JSON body" },
      { status: 400 },
    );
  }
  const message =
    typeof body === "object" && body && "message" in body
      ? String((body as { message: unknown }).message ?? "")
      : "";
  if (!message.trim()) {
    return NextResponse.json(
      { detail: "message must be a non-empty string" },
      { status: 400 },
    );
  }

  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), SEND_TIMEOUT_MS);
  try {
    const out = await qaApi.sendMessage({
      operatorId: access.operatorId,
      threadId,
      input: { message },
      signal: ac.signal,
    });
    return NextResponse.json(out);
  } catch (err) {
    if (err instanceof QAApiError) {
      return NextResponse.json(
        { detail: err.body ?? err.message },
        { status: err.status },
      );
    }
    return NextResponse.json(
      { detail: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  } finally {
    clearTimeout(t);
  }
}
