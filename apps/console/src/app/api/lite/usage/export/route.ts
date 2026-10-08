import { z } from "zod";

import { liteUsageCsvPath } from "@/lib/backend/lite";
import { proxyClientDownload } from "@/lib/download-proxy";

export const dynamic = "force-dynamic";

const query = z.object({
  days: z.coerce.number().int().min(1).max(366).default(30),
  lang: z.enum(["es", "en"]).default("es"),
});

/** Spec 030 (R5.4): the client's usage CSV — only its own rows, streamed from the API. */
export async function GET(request: Request): Promise<Response> {
  const q = query.safeParse(Object.fromEntries(new URL(request.url).searchParams));
  if (!q.success) return new Response(JSON.stringify({ detail: "Invalid parameters" }), { status: 422 });
  return proxyClientDownload(request, "usage", liteUsageCsvPath(q.data));
}
