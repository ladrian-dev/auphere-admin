/**
 * Next 16 proxy (formerly "middleware") — a cheap redirector, nothing more
 * (research §8.1: this layer is not a security boundary). Real verification happens in
 * Server Components / Actions / Route Handlers via ``requirePrincipal``,
 * and again in the API.
 *
 * Also stamps a per-request CSP nonce (CP-32) so scripts can run without
 * ``unsafe-inline``.
 */
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC = ["/login", "/invite", "/no-access", "/healthz"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV !== "production";
  const csp = [
    "default-src 'self'",
    // connect.facebook.net: Meta Embedded Signup SDK (lane channels, CP-17).
    // Loaded by a nonce'd script via createElement, which 'strict-dynamic'
    // already trusts; the host is listed for browsers without strict-dynamic.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://connect.facebook.net${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    // Dev only: Next's HMR websocket is a different scheme, so 'self' does not cover it.
    `connect-src 'self' https://graph.facebook.com https://www.facebook.com${isDev ? " ws://localhost:* wss://localhost:*" : ""}`,
    // facebook.com → the hidden frame the FB SDK mounts (CP-17).
    "frame-src 'self' https://www.facebook.com https://web.facebook.com",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);

  if (!PUBLIC.some((p) => pathname.startsWith(p))) {
    // Name duplicated from ``lib/session.ts`` on purpose: that module
    // imports ``next/headers``, which does not exist in this runtime.
    // Presence only — whether the token is still valid is the API's answer.
    const hasSession = Boolean(request.cookies.get("nexus-console.session")?.value);
    if (!hasSession) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      url.searchParams.set("from", pathname);
      const redirect = NextResponse.redirect(url);
      redirect.headers.set("Content-Security-Policy", csp);
      return redirect;
    }
  }
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
