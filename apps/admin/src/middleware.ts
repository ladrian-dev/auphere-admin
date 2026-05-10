/**
 * Edge middleware — gates everything outside ``/login`` and the auth
 * API behind a Better Auth session cookie.
 *
 * We do a cheap cookie-presence check (no DB hit). Server Components
 * and Server Actions still call ``auth.api.getSession`` for the real
 * verification; the middleware just bounces unauthenticated visitors
 * before they pull any layout.
 */

import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/auth"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }
  // Better Auth prepends ``__Secure-`` to the cookie name when
  // ``defaultCookieAttributes.secure`` is true (production HTTPS), so the
  // actual cookie ends up as ``__Secure-nexus.session_token``. Match by
  // suffix to handle both the dev (no prefix) and prod (prefix) shapes.
  const sessionCookie = request.cookies
    .getAll()
    .find((c) => c.name === "nexus.session_token" || c.name.endsWith(".nexus.session_token") || c.name.endsWith("-nexus.session_token"));
  if (!sessionCookie) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("from", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match every request except:
     * - ``_next/static`` / ``_next/image`` / favicon (Next internals)
     * - any file with an extension (assets)
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)",
  ],
};
