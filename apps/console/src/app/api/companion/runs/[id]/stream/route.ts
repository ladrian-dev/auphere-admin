import { z } from "zod";

import { tokenFor } from "@/lib/backend";
import { companionStreamPath } from "@/lib/backend/companion";
import { env } from "@/lib/env";
import { can, resolvePrincipal } from "@/lib/principal";

/**
 * SSE proxy of one Companion run (CO-01). The browser never talks to the
 * API: this handler verifies the principal + `companion:use`, mints a 60 s
 * token for it and pipes the backend stream through untouched
 * (`ReadableStream` passthrough, no buffering). The API re-checks
 * ownership of the run under the caller's principal before emitting a byte.
 *
 * `maxDuration` is EXPLICIT and that is the whole point of this file
 * existing separately from the playground's proxy. A Companion turn can
 * run for minutes; Vercel's default function ceiling cuts the connection
 * mid-stream, and until CO-01 nobody had pinned it. Note what the ceiling
 * does and does not cost us now: hitting it kills this *view* of the run,
 * not the run — the work lives on AWS and the log is durable, so the
 * drawer reconnects with `since_seq` and loses nothing. That is why the
 * number can stay sane instead of being pushed to the platform maximum.
 */
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const params = z.object({ id: z.string().uuid() });
const query = z.object({ since_seq: z.coerce.number().int().min(0).default(0) });

function json(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

export async function GET(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, "Not signed in");
  const principal = res.principal;
  if (!can(principal.role, "companion:use")) return json(403, "Missing permission companion:use");

  const p = params.safeParse(await ctx.params);
  const url = new URL(request.url);
  const q = query.safeParse(Object.fromEntries(url.searchParams));
  if (!p.success || !q.success) return json(422, "Invalid stream parameters");

  const token = await tokenFor(principal);
  const upstream = await fetch(`${env().NEXUS_BACKEND_URL}${companionStreamPath(p.data.id, q.data.since_seq)}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    cache: "no-store",
    // Aborting this request does NOT cancel the run — cancellation is
    // `DELETE /console/companion/runs/{id}` and nothing else. Forwarding
    // the signal only tears down this view.
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
