/**
 * Spec 040: the owner's signup link carries a token. The page must not keep it
 * in its address — Meta's SDK runs on that page and reads where it is — so the
 * link lands on a route that moves the token into this cookie and redirects
 * to the same page without it. httpOnly (no script reads it), limited to
 * `/connect`, one hour: enough to finish Meta's steps.
 */
export const OWNER_LINK_COOKIE = "nx_owner_link";
export const OWNER_LINK_MAX_AGE = 60 * 60;
export const TOKEN_SHAPE = /^[A-Za-z0-9_-]{16,128}$/;

/** Spec 085: Instagram and Messenger have their own owner page, `/connect/{kind}`. */
export const SOCIAL_LINK_KINDS = ["instagram", "messenger"] as const;
export type SocialLinkKind = (typeof SOCIAL_LINK_KINDS)[number];

export function isSocialLinkKind(kind: string): kind is SocialLinkKind {
  return (SOCIAL_LINK_KINDS as readonly string[]).includes(kind);
}

/**
 * Spec 085 (R8): one cookie per channel, so two links open in the same
 * browser — WhatsApp's and Instagram's — do not overwrite each other.
 * WhatsApp's keeps its name.
 */
export function ownerLinkCookie(channel: "whatsapp" | SocialLinkKind): string {
  return channel === "whatsapp" ? OWNER_LINK_COOKIE : `${OWNER_LINK_COOKIE}_${channel}`;
}
