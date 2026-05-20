/**
 * BFF proxy: ``DELETE /api/qa/runs/{runId}`` (ADR-021 Fase 1).
 *
 * Cancels an in-flight QA run. The backend signals the asyncio task,
 * the streaming endpoint emits ``run.completed`` with
 * ``status: "cancelled"`` and closes; the ``on_complete`` hook stamps
 * the ``qa.runs`` row.
 */
import { NextResponse } from "next/server";

import { QAForbidden, requireQAOperator } from "@/lib/qa-access";
import { QAApiError, qaApi } from "@/lib/qa-api";

export async function DELETE(
  _req: Request,
  context: { params: Promise<{ runId: string }> },
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
  const { runId } = await context.params;

  try {
    await qaApi.cancelRun({
      operatorId: access.operatorId,
      runId,
    });
    return new NextResponse(null, { status: 204 });
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
