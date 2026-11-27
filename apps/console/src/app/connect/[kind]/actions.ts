"use server";

import { cookies } from "next/headers";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { consoleService, type ChannelSignupSocialResult } from "@/lib/backend";
import type { MetaSocialConnectResult } from "@/lib/backend/channels";

import { TOKEN_SHAPE, ownerLinkCookie, type SocialLinkKind } from "../whatsapp/link-cookie";

const kind = z.enum(["instagram", "messenger"]);

/**
 * Spec 085: the owner finished Meta's window on their own device. No session:
 * the token is the authorization and the API checks it (single use, expiry,
 * revocation, and the pending choice tied to this link). It comes from the
 * channel's cookie, never from the page (7.1, 7.4). The console server
 * forwards with its service credential.
 */
async function token(of: SocialLinkKind): Promise<string | null> {
  const value = (await cookies()).get(ownerLinkCookie(of))?.value ?? "";
  return TOKEN_SHAPE.test(value) ? value : null;
}

async function settle(of: SocialLinkKind, res: ActionResult<ChannelSignupSocialResult>): Promise<ActionResult<MetaSocialConnectResult>> {
  if (!res.ok) return res;
  // Used: the cookie goes too.
  if (res.data.status === "connected") (await cookies()).delete({ name: ownerLinkCookie(of), path: "/connect" });
  return {
    ok: true,
    data: {
      status: res.data.status,
      channel: null,
      nonce: res.data.nonce,
      accounts: res.data.accounts,
      display_name: res.data.display_name,
    },
  };
}

const dead: ActionResult<MetaSocialConnectResult> = { ok: false, status: 404, message: "link_unknown", code: "link_unknown" };

export async function ownerSocialConnectAction(raw: unknown): Promise<ActionResult<MetaSocialConnectResult>> {
  const body = z.object({ kind, code: z.string().min(1).max(2048) }).parse(raw);
  const value = await token(body.kind);
  if (!value) return dead;
  return settle(body.kind, await run(() => consoleService.channelSignupMetaSocial(value, body.code)));
}

export async function ownerSocialCompleteAction(raw: unknown): Promise<ActionResult<MetaSocialConnectResult>> {
  const body = z.object({ kind, nonce: z.string().min(8).max(64), accountId: z.string().min(1).max(64) }).parse(raw);
  const value = await token(body.kind);
  if (!value) return dead;
  return settle(body.kind, await run(() => consoleService.channelSignupMetaSocialComplete(value, body.nonce, body.accountId)));
}
