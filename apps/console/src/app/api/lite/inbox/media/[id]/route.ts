import { z } from "zod";

import { inboxMediaPath } from "@/lib/backend/inbox";
import { proxyClientDownload } from "@/lib/download-proxy";

export const dynamic = "force-dynamic";

const params = z.object({ id: z.string().uuid() });

/**
 * Spec 030 (R8.3): a file of the client's own conversation, streamed from the
 * API. No storage link ever reaches the browser; the API's RLS decides whose
 * message it is, and another client's id is the same 404 as a made-up one.
 */
export async function GET(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const p = params.safeParse(await ctx.params);
  if (!p.success) return new Response(JSON.stringify({ detail: "Invalid id" }), { status: 422 });
  return proxyClientDownload(request, "inbox", inboxMediaPath(p.data.id));
}
