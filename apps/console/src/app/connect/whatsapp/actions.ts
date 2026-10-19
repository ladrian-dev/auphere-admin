"use server";

import { cookies } from "next/headers";
import { z } from "zod";

import { BackendError, consoleService } from "@/lib/backend";

import { OWNER_LINK_COOKIE, TOKEN_SHAPE } from "./link-cookie";

export type OwnerConnectResult =
  | { ok: true; phone: string | null }
  | { ok: false; reason: "dead" | "number_in_use" | "quota" | "held" | "error" };

/**
 * Spec 040: the owner finished Meta's popup on their own device. No session:
 * the token is the authorization and the API checks it (single use, expiry,
 * revocation). The console server forwards with its service credential.
 */
export async function ownerConnectAction(raw: unknown): Promise<OwnerConnectResult> {
  const jar = await cookies();
  const token = jar.get(OWNER_LINK_COOKIE)?.value ?? "";
  if (!TOKEN_SHAPE.test(token)) return { ok: false, reason: "dead" };
  const body = z
    .object({
      code: z.string().min(1).max(2048),
      waba_id: z.string().min(1).max(64),
      phone_number_id: z.string().max(64).optional(),
      business_id: z.string().max(64).optional(),
    })
    .safeParse(raw);
  if (!body.success) return { ok: false, reason: "error" };
  const signup = body.data;
  try {
    const done = await consoleService.channelSignupComplete(token, signup);
    // Used: the cookie goes too.
    jar.delete({ name: OWNER_LINK_COOKIE, path: "/connect" });
    return { ok: true, phone: done.display_phone_number };
  } catch (err) {
    if (err instanceof BackendError) {
      const detail = (err.body as { detail?: unknown } | null)?.detail;
      const code = detail && typeof detail === "object" && "code" in detail ? String((detail as { code: unknown }).code) : "";
      if (err.status === 404 || err.status === 410) return { ok: false, reason: "dead" };
      if (code === "number_in_use") return { ok: false, reason: "number_in_use" };
      if (code === "channel_quota_full") return { ok: false, reason: "quota" };
      if (code === "number_held_by_previous_owner") return { ok: false, reason: "held" };
    }
    return { ok: false, reason: "error" };
  }
}
