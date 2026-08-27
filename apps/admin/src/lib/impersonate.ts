/**
 * BFF-only helpers for the admin impersonation cookie.
 *
 * The API never Set-Cookie. The value is the impersonation session UUID,
 * not a partner JWT, and it does not replace ``nexus_operator``.
 */
import "server-only";

import { cookies } from "next/headers";

import { IMPERSONATE_COOKIE } from "./impersonate-cookie";

const SECURE = process.env.NODE_ENV === "production";

export { IMPERSONATE_COOKIE, matchImpersonationBanner } from "./impersonate-cookie";

export async function getImpersonateSessionId(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(IMPERSONATE_COOKIE)?.value ?? null;
}

export async function setImpersonateCookie(
  sessionId: string,
  maxAgeSeconds: number,
): Promise<void> {
  const jar = await cookies();
  jar.set(IMPERSONATE_COOKIE, sessionId, {
    httpOnly: true,
    secure: SECURE,
    sameSite: "lax",
    path: "/",
    maxAge: maxAgeSeconds,
  });
}

export async function clearImpersonateCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(IMPERSONATE_COOKIE);
}
