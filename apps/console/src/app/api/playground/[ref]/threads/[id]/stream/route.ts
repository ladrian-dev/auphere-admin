import { z } from "zod";

import { tokenFor } from "@/lib/backend";
import { playgroundStreamPath } from "@/lib/backend/playground";
import { env } from "@/lib/env";
import { can, resolvePrincipal } from "@/lib/principal";

/**
 * SSE proxy of one playground run (CP-16). The browser never talks to the
 * API: this handler verifies the principal + `playground:run`, mints a
 * 60 s token for it and pipes the backend stream through untouched
 * (`ReadableStream` passthrough, no buffering). The API re-checks
 * ownership (member's operator + client under the partner) before
 * emitting a byte.
 */
export const dynamic = "force-dynamic";

const params = z.object({
  ref: z.string().min(1).max(255),
  id: z.string().uuid(),
});
const query = z.object({
  run_id: z.string().uuid(),
  since_seq: z.coerce.number().int().min(0).default(0),
});

function json(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

export async function GET(request: Request, ctx: { params: Promise<{ ref: string; id: string }> }): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, "Not signed in");
  const principal = res.principal;
  if (!can(principal.role, "playground:run")) return json(403, "Missing permission playground:run");

  const p = params.safeParse(await ctx.params);
  const url = new URL(request.url);
  const q = query.safeParse(Object.fromEntries(url.searchParams));
  if (!p.success || !q.success) return json(422, "Invalid stream parameters");

  const token = await tokenFor(principal);
  const upstream = await fetch(`${env().NEXUS_BACKEND_URL}${playgroundStreamPath(p.data.ref, p.data.id, q.data.run_id, q.data.since_seq)}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    cache: "no-store",
    signal: request.signal,
    // @ts-expect-error — undici option: keep the response streaming.
    duplex: "half",
  });
  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    let detail = "Stream unavailable";
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* not JSON */
    }
    return json(upstream.status || 502, detail);
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-store, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
