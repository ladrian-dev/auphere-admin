/**
 * BFF proxy: ``POST /api/qa/threads/{threadId}/runs`` (ADR-021 Fase 1).
 *
 * Kicks off a streaming turn on the QA Playground. The backend creates
 * the ``qa.runs`` row + spawns the in-process driver task, then
 * returns ``{run_id}`` quickly. The browser then opens an SSE stream
 * against ``GET /api/qa/threads/{threadId}/stream?run_id=...`` to
 * consume the live events.
 *
 * Auth: ``routeOperator("qa")`` (spec 079): 401 without a session, 403 without ``qa``.
 * The browser never sees the backend's admin Bearer.
 */
import { NextResponse } from "next/server";

import { routeOperator } from "@/lib/session";
import { QAApiError, qaApi } from "@/lib/qa-api";

const START_TIMEOUT_MS = 30_000;

export async function POST(
  req: Request,
  context: { params: Promise<{ threadId: string }> },
) {
  const access = await routeOperator("qa");
  if (access instanceof Response) return access;
  const { threadId } = await context.params;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid JSON body" }, { status: 400 });
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
  const t = setTimeout(() => ac.abort(), START_TIMEOUT_MS);
  try {
    const out = await qaApi.startRun({
      operatorId: access.id,
      threadId,
      input: { message },
      signal: ac.signal,
    });
    return NextResponse.json(out, { status: 202 });
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
