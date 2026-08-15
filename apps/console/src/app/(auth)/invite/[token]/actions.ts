"use server";

import { headers } from "next/headers";
import { z } from "zod";

import { auth } from "@/lib/auth";
import { BackendError, consoleService } from "@/lib/backend";
import { getSession } from "@/lib/session";

const input = z.object({
  token: z.string().regex(/^[A-Za-z0-9_-]{16,128}$/),
  name: z.string().min(1).max(120).optional(),
  password: z.string().min(12).optional(),
});

export type AcceptResult =
  | { ok: true }
  | { ok: false; reason: "not_found" | "email_mismatch" | "already_member" | "invalid" | "error"; message?: string };

/**
 * Accept an invitation (CP-02/CP-26). Server-side, Zod-validated:
 *  1. resolve the invitation with the service token (404 → not_found);
 *  2. if the browser is not signed in as the invited e-mail, create the
 *     account with Better Auth's server API (public sign-up is closed);
 *  3. call the API to turn the invitation into a membership;
 *  4. the session is now a full principal → redirect happens client-side.
 */
export async function acceptInvitationAction(raw: unknown): Promise<AcceptResult> {
  const parsed = input.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  const { token, name, password } = parsed.data;

  const invitation = await consoleService.lookupInvitation(token);
  if (!invitation) return { ok: false, reason: "not_found" };

  const session = await getSession();
  let who: { id: string; email: string; name: string | null };
  const signedInMatches = session?.user.email.toLowerCase() === invitation.email.toLowerCase();
  if (signedInMatches && session) {
    who = { id: session.user.id, email: session.user.email, name: session.user.name };
  } else {
    if (!name || !password) return { ok: false, reason: "invalid" };
    try {
      // Server-side sign-up (public sign-up is closed). ``nextCookies``
      // sets the session cookie on this action's response.
      const created = await auth.api.signUpEmail({
        body: { email: invitation.email, password, name },
        headers: await headers(),
      });
      who = { id: created.user.id, email: created.user.email, name: created.user.name };
    } catch (err) {
      // Account already exists for that e-mail (invited person had one):
      // they must sign in first — the page explains it.
      const message = err instanceof Error ? err.message : "sign-up failed";
      return { ok: false, reason: "error", message };
    }
  }

  try {
    await consoleService.acceptInvitation(token, {
      user_id: who.id,
      email: who.email,
      display_name: who.name,
    });
  } catch (err) {
    if (err instanceof BackendError) {
      if (err.status === 404) return { ok: false, reason: "not_found" };
      if (err.detail.startsWith("email_mismatch")) return { ok: false, reason: "email_mismatch" };
      if (err.detail.startsWith("already_member")) return { ok: false, reason: "already_member" };
      return { ok: false, reason: "error", message: err.detail };
    }
    throw err;
  }
  return { ok: true };
}
