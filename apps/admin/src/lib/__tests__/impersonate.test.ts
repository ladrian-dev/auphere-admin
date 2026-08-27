import { describe, expect, it } from "vitest";

import {
  IMPERSONATE_COOKIE,
  PARTNER_COOKIE_NAMES,
  matchImpersonationBanner,
  type ImpersonationSession,
} from "../impersonate-cookie";

function live(over: Partial<ImpersonationSession> = {}): ImpersonationSession {
  return {
    id: "sess-1",
    partner_id: "partner-a",
    reason: "soporte ticket AU-1",
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    revoked_at: null,
    ...over,
  };
}

describe("impersonate cookie", () => {
  it("is nexus_impersonate on the admin host, never a partner cookie", () => {
    expect(IMPERSONATE_COOKIE === "nexus_impersonate" || IMPERSONATE_COOKIE === "__Host-nexus_impersonate").toBe(true);
    expect(IMPERSONATE_COOKIE).not.toContain("console");
    expect(IMPERSONATE_COOKIE).not.toContain("operator");
    expect(PARTNER_COOKIE_NAMES).not.toContain(IMPERSONATE_COOKIE);
  });

  it("shows the banner only when the cookie is live and the partner matches", () => {
    const active = [live()];
    expect(matchImpersonationBanner("sess-1", "partner-a", active)?.id).toBe("sess-1");
    expect(matchImpersonationBanner("sess-1", "partner-b", active)).toBeNull();
    expect(matchImpersonationBanner("other", "partner-a", active)).toBeNull();
    expect(matchImpersonationBanner(undefined, "partner-a", active)).toBeNull();
  });

  it("hides the banner for expired or revoked sessions", () => {
    const expired = live({
      expires_at: new Date(Date.now() - 1_000).toISOString(),
    });
    const revoked = live({ revoked_at: new Date().toISOString() });
    expect(matchImpersonationBanner("sess-1", "partner-a", [expired])).toBeNull();
    expect(matchImpersonationBanner("sess-1", "partner-a", [revoked])).toBeNull();
    expect(matchImpersonationBanner("sess-1", "partner-a", [])).toBeNull();
  });
});
