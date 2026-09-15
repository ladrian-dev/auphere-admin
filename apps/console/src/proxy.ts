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

// Lo que puede abrir alguien que **todavía no es nadie**. Cada entrada es una
// decisión, no una comodidad, y `src/__tests__/proxy-public-routes.test.ts`
// las fija una por una.
//
// `/api/session/whoami` (spec 002): la cáscara de escritorio pregunta quién
// está dentro; sin sesión la respuesta es un 401 en JSON, no una redirección
// a /login — una página HTML no es una persona.
//
// `/signup` y `/auth/google/callback` (spec 006) faltaban, y el alta llegó a
// staging sin ellas. El efecto era total y silencioso: la única gente para la
// que existe el registro —la que no tiene cuenta— rebotaba a `/login` antes de
// ver el formulario, y la vuelta de Google, que llega con `?code=&state=` y sin
// cookie, rebotaba igual. Todo verde y nada funcionando: ninguna prueba de
// componente ni de la API pasa por esta capa. **Una ruta nueva que un
// desconocido deba alcanzar se añade aquí en el mismo commit que la crea.**
const PUBLIC = [
  "/login",
  "/invite",
  "/signup",
  "/auth/google/callback",
  "/no-access",
  "/healthz",
  "/api/session/whoami",
  // `/desktop-auth` (spec 009): donde la aplicación manda el navegador para
  // empezar el inicio de sesión. Quien llega **todavía no tiene sesión** — es
  // lo que viene a conseguir —, así que si rebotara a `/login` sin recordar a
  // dónde iba, el retorno a la aplicación se perdería.
  "/desktop-auth",
  // `/api/desktop/redeem` (spec 009): donde ese mismo inicio de sesión TERMINA.
  // La cáscara canjea el código y lo que se lleva es la cookie — o sea que
  // llega sin ella por definición. Sin esta línea, rebotaría a `/login` y la
  // aplicación se quedaría fuera con la persona ya dentro del navegador.
  "/api/desktop/redeem",
];

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
