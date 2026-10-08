import { tokenFor } from "@/lib/backend";
import { inboxStreamPath } from "@/lib/backend/inbox";
import { env } from "@/lib/env";
import { resolvePrincipal } from "@/lib/principal";

/**
 * SSE proxy of the client's Inbox (spec 030, D17). The browser never talks to
 * the API: this handler checks a client person with the `inbox` module, mints
 * a 60 s token and pipes the backend stream through untouched. The API
 * subscribes only to the channel of that person's client; the events carry
 * no bodies — the console re-reads what changed through its RLS routes.
 *
 * The token only opens the stream: once open, the API holds the connection.
 * When it drops, `EventSource` reconnects on its own and this handler mints a
 * fresh one, so a person whose access was withdrawn stops at the next retry.
 */
export const dynamic = "force-dynamic";

function json(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

export async function GET(request: Request): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, "Not signed in");
  const principal = res.principal;
  if (principal.kind !== "client" || !principal.modules.includes("inbox")) return json(403, "Missing module inbox");

  const upstream = await fetch(`${env().NEXUS_BACKEND_URL}${inboxStreamPath}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${await tokenFor(principal)}`, Accept: "text/event-stream" },
    cache: "no-store",
    signal: request.signal,
    // @ts-expect-error — undici option: keep the response streaming.
    duplex: "half",
  });
  if (!upstream.ok || !upstream.body) return json(upstream.status || 502, "Stream unavailable");

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
