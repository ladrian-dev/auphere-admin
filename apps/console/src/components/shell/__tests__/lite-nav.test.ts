import { describe, expect, it } from "vitest";

import { firstModulePath, toResolution } from "@/lib/principal-access";

import { liteNav } from "../lite-nav";

/**
 * Spec 031 (R3.1, R3.2): the order of a client's modules has ONE source — the
 * API (`ClientAccess.ordered_modules()`). The console and the phone app paint it
 * as it comes; neither re-sorts it.
 */
describe("liteNav", () => {
  it("paints the modules in the order the API sent", () => {
    const hrefs = liteNav(["usage", "panel"]).flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs).toEqual(["/usage", "/"]);
  });

  it("paints nothing for a client without modules", () => {
    expect(liteNav([])).toEqual([]);
  });

  it("lands on the first module the API sent", () => {
    expect(firstModulePath(["inbox", "panel"])).toBe("/inbox");
    expect(firstModulePath(["usage"])).toBe("/usage");
  });
});

describe("toResolution keeps the API order", () => {
  it("drops unknown and repeated modules without re-sorting", () => {
    const res = toResolution({
      kind: "client",
      access: "ok",
      user_id: "u",
      email: "v@x.test",
      display_name: "Valeria",
      locale: "es",
      membership_id: "m",
      partner_id: "p",
      partner_slug: "s",
      partner_name: "Partner",
      console_enabled: true,
      role: "client",
      client_name: "Mi negocio",
      modules: ["inbox", "reservas", "panel", "inbox"],
    } as Parameters<typeof toResolution>[0]);
    expect(res.kind).toBe("ok");
    if (res.kind === "ok" && res.principal.kind === "client") {
      expect(res.principal.modules).toEqual(["inbox", "panel"]);
    }
  });
});
