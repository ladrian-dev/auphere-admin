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

import { qaApi, type QAThreadCreateInput } from "@/lib/qa-api";
import { getSession } from "@/lib/session";

export async function POST(req: Request) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ detail: "unauthenticated" }, { status: 401 });
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
      operatorId: session.user.id,
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
