import "server-only";

import { tokenFor } from "./backend";
import { env } from "./env";
import { can, resolvePrincipal, type Permission } from "./principal";

function json(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

/**
 * Stream a downloadable backend resource (CSV, receipt) to the browser
 * (lane home-usage: CP-22/25/28). The browser never talks to the API: the
 * handler verifies the principal + permission, mints a 60 s token and
 * pipes the upstream body untouched, forwarding only `content-type` and
 * `content-disposition`.
 */
export async function proxyDownload(request: Request, permission: Permission, backendPath: string): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, "Not signed in");
  if (!can(res.principal.role, permission)) return json(403, `Missing permission ${permission}`);
  const token = await tokenFor(res.principal);
  const upstream = await fetch(`${env().NEXUS_BACKEND_URL}${backendPath}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal: request.signal,
  });
  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    let detail = "Download unavailable";
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* not JSON */
    }
    return json(upstream.status || 502, detail);
  }
  const headers = new Headers({ "cache-control": "no-store" });
  for (const h of ["content-type", "content-disposition"]) {
    const v = upstream.headers.get(h);
    if (v) headers.set(h, v);
  }
  return new Response(upstream.body, { status: 200, headers });
}
