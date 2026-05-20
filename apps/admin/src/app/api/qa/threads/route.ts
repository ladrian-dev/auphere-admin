/**
 * Proxy: ``POST /api/qa/threads``.
 *
 * The browser cannot talk to the FastAPI ``/qa/*`` surface directly
 * because the admin Bearer token must never leave the server. This
 * proxy resolves the Better Auth session, attaches the bearer and the
 * ``X-Operator-Id`` header, and forwards to the backend.
 *
 * Same shape as the qa-api: takes ``{tenant_id, title?}``, returns a
 * ``QAThread``.
 */
import { NextResponse } from "next/server";

import { QAForbidden, requireQAOperator } from "@/lib/qa-access";
import { qaApi, type QAThreadCreateInput } from "@/lib/qa-api";

export async function POST(req: Request) {
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
  const body = (await req.json().catch(() => null)) as QAThreadCreateInput | null;
  if (!body?.tenant_id) {
    return NextResponse.json(
      { detail: "tenant_id is required" },
      { status: 400 },
    );
  }
  try {
    const thread = await qaApi.createThread({
      operatorId: access.operatorId,
      input: body,
    });
    return NextResponse.json(thread, { status: 201 });
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
