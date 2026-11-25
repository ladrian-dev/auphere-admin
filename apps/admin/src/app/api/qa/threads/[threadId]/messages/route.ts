/**
 * BFF proxy: ``GET /api/qa/threads/{threadId}/messages`` (ADR-021 Fase 1).
 *
 * Hydrate the operator-visible history of a QA thread. Used by
 * ``qa-runtime`` on mount to seed the assistant-ui ``messages`` array
 * so the operator sees prior turns immediately after a reload.
 */
import { NextRequest, NextResponse } from "next/server";

import { routeOperator } from "@/lib/session";
import { QAApiError, qaApi } from "@/lib/qa-api";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ threadId: string }> },
) {
  const access = await routeOperator("qa");
  if (access instanceof Response) return access;

  const { threadId } = await context.params;
  const limitParam = request.nextUrl.searchParams.get("limit");
  const limit = limitParam ? Math.max(1, Math.min(200, Number(limitParam))) : undefined;

  try {
    const rows = await qaApi.getThreadMessages({
      operatorId: access.id,
      threadId,
      limit,
    });
    return NextResponse.json(rows);
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
  }
}
