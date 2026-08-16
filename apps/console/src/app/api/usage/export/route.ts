import { z } from "zod";

import { usageCsvPath } from "@/lib/backend/home-usage";
import { proxyDownload } from "@/lib/download-proxy";

export const dynamic = "force-dynamic";

const query = z.object({
  days: z.coerce.number().int().min(1).max(366).default(30),
  client: z.string().max(255).optional(),
  source: z.enum(["channel", "qa"]).optional(),
  lang: z.enum(["es", "en"]).default("es"),
});

/** CSV of the usage report (CP-22) — streamed from the API. */
export async function GET(request: Request): Promise<Response> {
  const q = query.safeParse(Object.fromEntries(new URL(request.url).searchParams));
  if (!q.success) return new Response(JSON.stringify({ detail: "Invalid parameters" }), { status: 422 });
  return proxyDownload(request, "usage:read", usageCsvPath(q.data));
}
