"use server";

import { z } from "zod";

import { BackendError, consoleService } from "@/lib/backend";
import { setSessionToken } from "@/lib/session";

const input = z.object({
  token: z.string().regex(/^[A-Za-z0-9_-]{16,128}$/),
  name: z.string().min(1).max(120).optional(),
  password: z.string().min(12).max(256),
});

export type AcceptResult =
  | { ok: true }
  | {
      ok: false;
      reason: "not_found" | "already_member" | "account_exists" | "rate_limited" | "invalid" | "error";
      message?: string;
    };

/**
 * Accept an invitation (CP-02/CP-26, reworked by ADR-032).
 *
 * The account no longer exists in this app: the API creates the principal
 * in `console_auth.principals`, turns the invitation into a membership and
 * returns a session token, all in one call. This action's whole job is to
 * validate the input server-side and put that token in the cookie.
 *
 * The e-mail is NOT sent: it comes from the invitation row. That closes
 * the old `email_mismatch` case by construction — there is nothing left to
 * mismatch.
 */
export async function acceptInvitationAction(raw: unknown): Promise<AcceptResult> {
  const parsed = input.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  const { token, name, password } = parsed.data;

  try {
    const accepted = await consoleService.acceptInvitation(token, {
      password,
      display_name: name ?? null,
    });
    await setSessionToken(accepted.token, accepted.expires_at);
    return { ok: true };
  } catch (err) {
    if (err instanceof BackendError) {
      if (err.status === 404) return { ok: false, reason: "not_found" };
      if (err.status === 429) return { ok: false, reason: "rate_limited" };
      if (err.detail.startsWith("account_exists")) return { ok: false, reason: "account_exists" };
      if (err.detail.startsWith("already_member")) return { ok: false, reason: "already_member" };
      return { ok: false, reason: "error", message: err.detail };
    }
    throw err;
  }
}
