import { describe, expect, it } from "vitest";

import { CLIENT_MODULES, firstModulePath, toResolution } from "@/lib/principal-access";

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
    expect(firstModulePath(["reservas", "usage"])).toBe("/reservas");
    expect(firstModulePath([])).toBe("/");
  });

  // Spec 043 (T020): Reservas sits between the Inbox and Consumo, with its calendar.
  it("paints Reservas with its own label and path", () => {
    const items = liteNav(["panel", "inbox", "reservas", "usage"]).flatMap((g) => g.items);
    expect(items.map((i) => i.href)).toEqual(["/", "/inbox", "/reservas", "/usage"]);
    expect(items[2]?.labelKey).toBe("nav.reservas");
  });

  // Spec 056 (requisito 2.1): Agentes y Negocio left the client's bar. A module
  // name the console does not know never reaches it (`toResolution` drops it).
  it("has no Agentes nor Negocio", () => {
    const hrefs = liteNav(["panel", "inbox", "reservas", "usage"]).flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs).not.toContain("/agentes");
    expect(hrefs).not.toContain("/negocio");
    expect(CLIENT_MODULES).toEqual(["panel", "inbox", "reservas", "usage"]);
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
      modules: ["inbox", "agenda", "agents", "panel", "business", "inbox"],
    } as Parameters<typeof toResolution>[0]);
    expect(res.kind).toBe("ok");
    if (res.kind === "ok" && res.principal.kind === "client") {
      // Spec 056: `agents` y `business` son tan desconocidos como `agenda`.
      expect(res.principal.modules).toEqual(["inbox", "panel"]);
    }
  });
});
