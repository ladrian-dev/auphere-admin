import { z } from "zod";

import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

const query = z.object({
  cursor: z.string().max(512),
  actor: z.string().max(255).optional(),
  client: z.string().max(255).optional(),
  category: z.string().max(40).optional(),
  after: z.string().datetime({ offset: true }).optional(),
  before: z.string().datetime({ offset: true }).optional(),
  lang: z.enum(["es", "en"]).default("es"),
});

/**
 * Spec 029: «Ver anteriores» adds the next page under the one on screen
 * instead of replacing it, so the browser asks for it here with the same
 * filters the page was rendered with.
 */
export async function GET(request: Request): Promise<Response> {
  const q = query.safeParse(Object.fromEntries(new URL(request.url).searchParams));
  if (!q.success) return new Response(JSON.stringify({ detail: "Invalid parameters" }), { status: 422 });
  return withPermission("audit:read", (b) => b.auditV2({ limit: 50, ...q.data }));
}
