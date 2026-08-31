/**
 * F2 partner UI: only WhatsApp is a product card. TikTok / IG / web / MCP
 * custom stay out of the console (not even "coming soon").
 */
export const F2_VISIBLE_CHANNEL_TYPES = ["whatsapp"] as const;

export type F2Channel = { type: string; status: string };

export function isF2VisibleChannel(type: string): boolean {
  return (F2_VISIBLE_CHANNEL_TYPES as readonly string[]).includes(type);
}

export function f2VisibleChannels<T extends F2Channel>(channels: T[]): T[] {
  return channels.filter((c) => isF2VisibleChannel(c.type));
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
