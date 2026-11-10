import { describe, expect, it } from "vitest";

import { PARTNER_MODULES } from "@/lib/principal-access";

import { isActive, navForPartner, navForPrincipal, navForRole } from "../nav";

describe("nav", () => {
  it("filters items by role", () => {
    const billing = navForRole("billing").flatMap((g) => g.items.map((i) => i.href));
    expect(billing).toEqual(["/", "/usage", "/team", "/billing"]);
    // Notifications live in the top-bar bell, not in the sidebar.
    expect(navForRole("owner").flatMap((g) => g.items.map((i) => i.href))).not.toContain("/notifications");
    const builder = navForRole("builder").flatMap((g) => g.items.map((i) => i.href));
    expect(builder).not.toContain("/billing");
    expect(builder).toContain("/keys");
  });
  it("active detection", () => {
    const [operate] = navForRole("owner");
    const home = operate!.items[0]!;
    const clients = operate!.items[1]!;
    expect(isActive("/", home)).toBe(true);
    expect(isActive("/clients", home)).toBe(false);
    expect(isActive("/clients/x/agent", clients)).toBe(true);
  });
});

/**
 * Spec 030 (R3.1, R3.3): la barra de una persona de cliente tiene exactamente
 * los módulos de su cliente, en el orden Panel, Bandeja de entrada, Consumo,
 * en un solo grupo y sin nada del partner.
 */
describe("navForPrincipal — consola lite", () => {
  const hrefs = (groups: ReturnType<typeof navForPrincipal>) => groups.flatMap((g) => g.items.map((i) => i.href));

  // Spec 031 (R3.2): the order comes from the API (`ordered_modules()`), which
  // sends Panel, Bandeja, Consumo; the bar paints it as it comes.
  it("lists the client's modules in the order the API sent", () => {
    expect(hrefs(navForPrincipal({ kind: "client", modules: ["panel", "inbox", "usage"] }))).toEqual([
      "/",
      "/inbox",
      "/usage",
    ]);
    expect(hrefs(navForPrincipal({ kind: "client", modules: ["usage"] }))).toEqual(["/usage"]);
  });

  it("never shows a partner item to a client", () => {
    const partnerOnly = ["/clients", "/audit", "/knowledge", "/workstation", "/team", "/billing", "/keys"];
    const lite = hrefs(navForPrincipal({ kind: "client", modules: ["panel", "inbox", "usage"] }));
    for (const href of partnerOnly) expect(lite).not.toContain(href);
    expect(navForPrincipal({ kind: "client", modules: ["panel"] })).toHaveLength(1);
  });

  it("keeps the partner navigation as it was when every module is on", () => {
    expect(navForPrincipal({ kind: "partner", role: "owner", modules: PARTNER_MODULES })).toEqual(navForRole("owner"));
  });

  it("spec 032: shows only the modules Auphere gave the partner, in order", () => {
    const hrefs = (role: "owner" | "analyst", modules: (typeof PARTNER_MODULES)[number][]) =>
      navForPartner(role, modules).flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs("owner", ["billing", "panel", "usage"])).toEqual(["/", "/usage", "/billing"]);
    // Modules AND permissions: an analyst never sees billing, module or not.
    expect(hrefs("analyst", ["panel", "billing"])).toEqual(["/"]);
    // The Companion is not a sidebar entry.
    expect(hrefs("owner", ["panel", "companion"])).toEqual(["/"]);
  });
});
