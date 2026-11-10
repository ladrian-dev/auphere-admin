import { z } from "zod";

import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

const query = z.object({
  // Sin cursor es la primera página: «{n} más como esta» la pide así, sin juntar.
  cursor: z.string().max(512).optional(),
  actor: z.string().max(255).optional(),
  person: z.string().max(255).optional(),
  action: z.string().max(80).optional(),
  client: z.string().max(255).optional(),
  category: z.string().max(40).optional(),
  days: z.enum(["7", "30", "90", "all"]).optional(),
  group: z.enum(["true", "false"]).optional(),
  limit: z.coerce.number().int().min(1).max(200).default(50),
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
  const { group, ...rest } = q.data;
  return withPermission("audit:read", (b) => b.auditV2({ ...rest, ...(group ? { group: group === "true" } : {}) }));
}
