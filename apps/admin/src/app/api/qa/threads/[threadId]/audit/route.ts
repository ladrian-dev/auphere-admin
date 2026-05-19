/**
 * Proxy: ``GET /api/qa/threads/{threadId}/audit``.
 *
 * Resolves the session, forwards to the FastAPI endpoint with the
 * operator id header. RLS enforces that the operator only ever sees
 * audit rows for threads they own, so we don't need to re-check
 * ownership here — a 404 from the backend means "not yours".
 */
import { NextResponse } from "next/server";

import { qaApi } from "@/lib/qa-api";
import { getSession } from "@/lib/session";

export async function GET(
  req: Request,
  context: { params: Promise<{ threadId: string }> },
) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });
  }
  const { threadId } = await context.params;
  const url = new URL(req.url);
  const limitRaw = url.searchParams.get("limit");
  const limit = limitRaw ? Number(limitRaw) : undefined;
  try {
    const rows = await qaApi.getThreadAudit({
      operatorId: session.user.id,
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
