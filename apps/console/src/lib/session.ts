import "server-only";

import { cookies } from "next/headers";

/**
 * The console's whole session state: ONE cookie holding an opaque token
 * that only the API can resolve (`POST /console/auth/session`).
 *
 * This app has no database. Before (ADR-030 D2) it ran better-auth on a
 * `console_auth` schema through Drizzle, which forced Vercel to reach
 * Postgres — and the production Aurora is private. Now the browser holds
 * a cookie, the BFF holds nothing, and identity lives in the API
 * (`services/console_identity.py`, ADR-032).
 *
 * Cookie rules: `httpOnly` (no script ever reads it), `sameSite=lax` (the
 * invitation link is a top-level GET and must survive it), `secure` in
 * production only — a dev console on plain http would silently drop it.
 */
export const SESSION_COOKIE = "nexus-console.session";
/** Matches the API's absolute session TTL. */
export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7;

const isProd = process.env.NODE_ENV === "production";

export async function getSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

export async function setSessionToken(token: string, expiresAt?: string): Promise<void> {
  const store = await cookies();
  const expires = expiresAt ? new Date(expiresAt) : undefined;
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: isProd,
    sameSite: "lax",
    path: "/",
    // Trust the API's expiry when it sent one; fall back to the same TTL.
    ...(expires && !Number.isNaN(expires.getTime())
      ? { expires }
      : { maxAge: SESSION_MAX_AGE_SECONDS }),
  });
}

export async function clearSessionToken(): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", {
    httpOnly: true,
    secure: isProd,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}
