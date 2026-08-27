/**
 * Admin-host impersonation cookie. Session id only — never a partner JWT
 * and never the console cookie. In production the ``__Host-`` prefix
 * matches ``nexus_operator`` (Secure + Path=/ + host-locked).
 */
export const IMPERSONATE_COOKIE =
  process.env.NODE_ENV === "production"
    ? "__Host-nexus_impersonate"
    : "nexus_impersonate";

export const PARTNER_COOKIE_NAMES = [
  "nexus-console.session",
  "nexus_console",
  "__Host-nexus_console",
] as const;

export type ImpersonationSession = {
  id: string;
  partner_id: string;
  reason: string;
  expires_at: string;
  revoked_at: string | null;
};

export function matchImpersonationBanner(
  cookieSessionId: string | null | undefined,
  partnerId: string,
  active: ImpersonationSession[],
): ImpersonationSession | null {
  if (!cookieSessionId) return null;
  const row = active.find((item) => item.id === cookieSessionId);
  if (!row) return null;
  if (row.revoked_at) return null;
  if (row.partner_id !== partnerId) return null;
  if (Date.parse(row.expires_at) <= Date.now()) return null;
  return row;
}
