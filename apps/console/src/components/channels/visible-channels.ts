/**
 * F2 partner UI: only WhatsApp is a product card. TikTok / IG / web / MCP
 * custom stay out of the console (not even "coming soon").
 */
export const F2_VISIBLE_CHANNEL_TYPES = ["whatsapp"] as const;

/** Spec 049: Instagram and Messenger, only for the partners Auphere switched
 *  on (the API sends `overview.meta_social` only to them). */
export const META_SOCIAL_CHANNEL_TYPES = ["instagram", "messenger"] as const;

export type F2Channel = { type: string; status: string; unlink_pending?: string[] };

export function isF2VisibleChannel(type: string, extra: readonly string[] = []): boolean {
  return (F2_VISIBLE_CHANNEL_TYPES as readonly string[]).includes(type) || extra.includes(type);
}

/**
 * A disconnected number leaves the page (owner, 2026-10-04): what the partner
 * needs to see is the WhatsApp that answers, not the history of the ones that
 * did. The one exception is a number Meta has not finished letting go
 * (`unlink_pending`, spec 021): its card is the only place to retry, so it
 * stays until Meta is done.
 */
export function f2VisibleChannels<T extends F2Channel>(channels: T[], extra: readonly string[] = []): T[] {
  return channels.filter((c) => isF2VisibleChannel(c.type, extra) && (c.status !== "disconnected" || (c.unlink_pending?.length ?? 0) > 0));
}

/** One WhatsApp slot: M is always 1; N is 1 if any WhatsApp is active. */
export function f2ChannelCounter(channels: F2Channel[]): { n: number; m: number } {
  const visible = f2VisibleChannels(channels);
  const n = visible.some((c) => c.status === "active") ? 1 : 0;
  return { n, m: 1 };
}

/** Staging: Meta Embedded Signup does not run. CTA has no href and no click. */
export function f2SignupEnabled(): false {
  return false;
}
