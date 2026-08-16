import { z } from "zod";

import { auditCsvPath } from "@/lib/backend/home-usage";
import { proxyDownload } from "@/lib/download-proxy";

export const dynamic = "force-dynamic";

const query = z.object({
  actor: z.string().max(255).optional(),
  action: z.string().max(80).optional(),
  client: z.string().max(255).optional(),
  after: z.string().datetime({ offset: true }).optional(),
  before: z.string().datetime({ offset: true }).optional(),
  lang: z.enum(["es", "en"]).default("es"),
});

/** CSV of the audit trail (CP-28) — same filters as the page, streamed. */
export async function GET(request: Request): Promise<Response> {
  const q = query.safeParse(Object.fromEntries(new URL(request.url).searchParams));
  if (!q.success) return new Response(JSON.stringify({ detail: "Invalid parameters" }), { status: 422 });
  return proxyDownload(request, "audit:read", auditCsvPath(q.data));
}
