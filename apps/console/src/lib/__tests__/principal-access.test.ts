import { describe, expect, it } from "vitest";

import type { ApiPrincipal } from "@/lib/backend";
import { toResolution } from "@/lib/principal-access";

/**
 * The console no longer decides who has access — the API does, and this
 * mapping is the only place where its answer becomes a rendering decision.
 * Getting `disabled` wrong would show the panel to a partner whose console
 * is switched off; getting `ok` wrong would lock out a legitimate owner.
 */
const base: ApiPrincipal = {
  user_id: "9f0f6a58-9c1e-4a2f-9c48-3ef0c8f1a111",
  email: "owner@partner.test",
  display_name: "Owner",
  locale: "es",
  access: "ok",
  membership_id: "1bcbdb44-62be-4707-827a-18ba8cc96864",
  partner_id: "dc24a0ff-c7a3-4c34-a8cb-aa13d80356ec",
  partner_slug: "demo",
  partner_name: "Demo Partner",
  partner_status: "active",
  role: "owner",
  permissions: ["clients:read", "clients:write"],
  console_enabled: true,
};

describe("toResolution", () => {
  it("maps a usable membership to a principal", () => {
    const res = toResolution(base);
    expect(res.kind).toBe("ok");
    if (res.kind !== "ok") throw new Error("unreachable");
    expect(res.principal).toMatchObject({
      userId: base.user_id,
      email: base.email,
      name: "Owner",
      locale: "es",
      partnerSlug: "demo",
      role: "owner",
      consoleEnabled: true,
    });
  });

  it("keeps the partner name on `disabled` — the copy needs it", () => {
    const res = toResolution({ ...base, access: "disabled", console_enabled: false });
    expect(res).toEqual({ kind: "disabled", email: base.email, partnerName: "Demo Partner" });
  });

  it("distinguishes no membership from a suspended one", () => {
    expect(toResolution({ ...base, access: "no_membership", role: null, membership_id: null })).toEqual({
      kind: "no-membership",
      email: base.email,
    });
    expect(toResolution({ ...base, access: "suspended" })).toEqual({
      kind: "suspended",
      email: base.email,
    });
  });

  it("falls back to no-membership when `ok` arrives without partner fields", () => {
    // Contract drift must degrade to /no-access, never to a shell with
    // empty ids that would then mint tokens for partner_id "".
    expect(toResolution({ ...base, partner_id: null }).kind).toBe("no-membership");
    expect(toResolution({ ...base, role: null }).kind).toBe("no-membership");
    expect(toResolution({ ...base, membership_id: null }).kind).toBe("no-membership");
  });

  it("only accepts the two locales the console renders", () => {
    const en = toResolution({ ...base, locale: "en" });
    const nonsense = toResolution({ ...base, locale: "de" });
    expect(en.kind === "ok" && en.principal.locale).toBe("en");
    expect(nonsense.kind === "ok" && nonsense.principal.locale).toBe("es");
  });
});
