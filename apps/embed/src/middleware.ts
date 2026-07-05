import { NextResponse, type NextRequest } from "next/server";

/**
 * Dynamic per-partner CSP (ADR-028).
 *
 * The loader opens `/broadcast?p=<partner_slug>`. We resolve the slug to
 * the partner's `allowed_origins` (union of its active API keys) and
 * emit `frame-ancestors` accordingly, so ONLY those origins can embed
 * this app. The config endpoint is edge-cacheable (s-maxage=300).
 *
 * Fail-closed: no slug, unknown slug or config fetch failure all end in
 * `frame-ancestors 'none'` — the page renders but no one can frame it.
 * Defense in depth: even a mis-framed page is inert without a valid
 * session JWT delivered over the origin-checked postMessage bridge.
 */

const API_BASE = process.env.NEXT_PUBLIC_NEXUS_API_URL ?? "http://localhost:8000";

const ORIGIN_RE = /^https:\/\/[a-z0-9.-]+(:\d+)?$|^http:\/\/localhost(:\d+)?$/i;

async function resolveAllowedOrigins(slug: string): Promise<string[]> {
  const response = await fetch(
    `${API_BASE}/v1/embed/partner-config?p=${encodeURIComponent(slug)}`,
    { next: { revalidate: 300 } },
  );
  if (!response.ok) return [];
  const body = (await response.json()) as { allowed_origins?: unknown };
  if (!Array.isArray(body.allowed_origins)) return [];
  // Belt and braces: only well-formed origins make it into the header.
  return body.allowed_origins.filter(
    (origin): origin is string => typeof origin === "string" && ORIGIN_RE.test(origin),
  );
}

export async function middleware(request: NextRequest) {
  const slug = request.nextUrl.searchParams.get("p") ?? "";
  let ancestors = "'none'";
  if (slug) {
    try {
      const origins = await resolveAllowedOrigins(slug);
      if (origins.length > 0) ancestors = origins.join(" ");
    } catch {
      // fetch failure → fail closed
    }
  }

  const response = NextResponse.next();
  response.headers.set(
    "Content-Security-Policy",
    `frame-ancestors ${ancestors}; base-uri 'self'; form-action 'self'`,
  );
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export const config = {
  // Only document routes need the header — skip assets.
  matcher: ["/broadcast", "/signup"],
};
