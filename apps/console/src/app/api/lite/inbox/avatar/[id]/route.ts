import { z } from "zod";

import { inboxAvatarPath } from "@/lib/backend/inbox";
import { proxyClientDownload } from "@/lib/download-proxy";

export const dynamic = "force-dynamic";

const params = z.object({ id: z.string().uuid() });

/**
 * The profile picture of the person in a conversation (Instagram / Messenger;
 * owner, 2026-10-30), streamed from the API like a message's media: no storage
 * link reaches the browser and another client's conversation is a 404.
 */
export async function GET(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const p = params.safeParse(await ctx.params);
  if (!p.success) return new Response(JSON.stringify({ detail: "Invalid id" }), { status: 422 });
  return proxyClientDownload(request, "inbox", inboxAvatarPath(p.data.id));
}
