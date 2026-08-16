"use server";

import { z } from "zod";

import { BackendError, consoleService } from "./backend";
import { clearSessionToken, getSessionToken, setSessionToken } from "./session";

/**
 * Sign in / sign out as Server Actions (ADR-032).
 *
 * The browser never talks to the API: it posts here, this server calls
 * `/console/auth/*` with a 60-second service token and writes the
 * `httpOnly` cookie. Nothing about the credential reaches client JS.
 *
 * The failure vocabulary is deliberately narrow — `invalid` covers a
 * wrong password, an unknown e-mail AND a locked account, exactly as the
 * API answers, so the console cannot leak which of the three it was.
 */

const credentials = z.object({
  email: z.string().email(),
  // No minimum here: enforcing the 12-character policy at sign-in would
  // turn a short password into a different answer than a wrong one.
  password: z.string().min(1).max(256),
});

export type SignInResult = { ok: true } | { ok: false; reason: "invalid" | "rate_limited" | "error" };

export async function signInAction(raw: unknown): Promise<SignInResult> {
  const parsed = credentials.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  try {
    const result = await consoleService.login(parsed.data);
    await setSessionToken(result.token, result.expires_at);
    return { ok: true };
  } catch (err) {
    if (err instanceof BackendError) {
      if (err.status === 401) return { ok: false, reason: "invalid" };
      if (err.status === 429) return { ok: false, reason: "rate_limited" };
      return { ok: false, reason: "error" };
    }
    throw err;
  }
}

/** Idempotent: kills the session in the API and drops the cookie either way. */
export async function signOutAction(): Promise<void> {
  const token = await getSessionToken();
  if (token) {
    try {
      await consoleService.logout(token);
    } catch (err) {
      // A backend hiccup must not strand the user in a session they asked
      // to end: the cookie goes regardless, and the token expires on its own.
      if (!(err instanceof BackendError)) throw err;
    }
  }
  await clearSessionToken();
}
