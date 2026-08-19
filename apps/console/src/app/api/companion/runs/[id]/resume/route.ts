import { z } from "zod";

import { badRequest, readJson, withCompanion } from "../../../_guard";

export const dynamic = "force-dynamic";

const resumeBody = z.object({
  action_id: z.string().uuid(),
  decision: z.enum(["confirm", "edit", "cancel"]),
  // Singular on purpose: `notes` is a forbidden property name (§1.1). With
  // `edit` or `cancel` this text goes BACK to the model as the user's
  // reason, so the plan gets adjusted instead of merely refused (§2.4).
  note: z.string().max(2000).optional(),
});

/**
 * Answer a pending confirmation (§4 of the contract).
 *
 * **The 202 carries a NEW `run_id`** — the paused run publishes nothing
 * more, so the drawer attaches to the returned one and `hitl.resolved`
 * arrives as its first event (§4.3). `edit` and `cancel` also return 202
 * and also start a run: the model has to react to the note.
 *
 * Errors the drawer distinguishes: 409 `action_already_decided` /
 * `action_expired` (you ran out of time) versus 412 `state_changed`
 * (someone changed this while you were deciding). `_guard` forwards
 * `detail.code` so those stay tellable apart.
 *
 * **Nothing serves this endpoint yet** — CO-04 builds it in parallel.
 */
export async function POST(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  const body = resumeBody.safeParse(await readJson(request));
  if (!body.success || !z.string().uuid().safeParse(id).success) return badRequest("Invalid decision");
  return withCompanion((b) => b.resumeCompanionRun(id, body.data));
}
