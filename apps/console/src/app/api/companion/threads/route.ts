import { z } from "zod";

import { badRequest, readJson, withCompanion } from "../_guard";

export const dynamic = "force-dynamic";

const createBody = z.object({
  title: z.string().min(1).max(200).optional(),
  // The partner's own reference for a client — NEVER a tenant id. The API
  // does not accept one and resolves the client under the principal.
  client_ref: z.string().min(1).max(255).optional(),
  mode: z.enum(["consult", "build"]).optional(),
});

/** Threads of the calling member. Metadata only — never a transcript. */
export async function GET(request: Request): Promise<Response> {
  const includeArchived = new URL(request.url).searchParams.get("include_archived") === "true";
  return withCompanion((b) => b.listCompanionThreads({ include_archived: includeArchived }));
}

export async function POST(request: Request): Promise<Response> {
  const body = createBody.safeParse(await readJson(request));
  if (!body.success) return badRequest("Invalid thread");
  return withCompanion((b) => b.createCompanionThread(body.data));
}
