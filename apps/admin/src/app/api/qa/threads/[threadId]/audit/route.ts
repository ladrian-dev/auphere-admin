/**
 * Proxy: ``GET /api/qa/threads/{threadId}/audit``.
 *
 * Resolves the session, forwards to the FastAPI endpoint with the
 * operator id header. RLS enforces that the operator only ever sees
 * audit rows for threads they own, so we don't need to re-check
 * ownership here — a 404 from the backend means "not yours".
 */
import { NextResponse } from "next/server";

import { QAForbidden, requireQAOperator } from "@/lib/qa-access";
import { qaApi } from "@/lib/qa-api";

export async function GET(
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
  const url = new URL(req.url);
  const limitRaw = url.searchParams.get("limit");
  const limit = limitRaw ? Number(limitRaw) : undefined;
  try {
    const rows = await qaApi.getThreadAudit({
      operatorId: access.operatorId,
      threadId,
      limit,
    });
    return NextResponse.json(rows);
  } catch (err) {
    const status =
      typeof err === "object" && err && "status" in err
        ? (err as { status: number }).status
        : 500;
    return NextResponse.json(
      { detail: err instanceof Error ? err.message : String(err) },
      { status },
    );
  }
}
