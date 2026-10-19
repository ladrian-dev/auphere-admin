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
