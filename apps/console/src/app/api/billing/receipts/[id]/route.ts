import { z } from "zod";

import { receiptDownloadPath } from "@/lib/backend/home-usage";
import { proxyDownload } from "@/lib/download-proxy";

export const dynamic = "force-dynamic";

/** Receipt download (CP-25): the API only resolves the partner's own receipts. */
export async function GET(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const id = z.string().uuid().safeParse((await ctx.params).id);
  if (!id.success) return new Response(JSON.stringify({ detail: "Invalid receipt id" }), { status: 422 });
  return proxyDownload(request, "billing:read", receiptDownloadPath(id.data));
}
