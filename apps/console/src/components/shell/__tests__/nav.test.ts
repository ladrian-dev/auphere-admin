import { describe, expect, it } from "vitest";

import { isActive, navForPrincipal, navForRole } from "../nav";

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

  it("lists the client's modules in sidebar order", () => {
    expect(hrefs(navForPrincipal({ kind: "client", modules: ["usage", "inbox", "panel"] }))).toEqual([
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

  it("keeps the partner navigation as it was", () => {
    expect(navForPrincipal({ kind: "partner", role: "owner" })).toEqual(navForRole("owner"));
  });
});
