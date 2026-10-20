import { firstRoute, knownModules, tabPlan } from "@/lib/modules";

/**
 * Spec 031 (T043, R3.1–R3.7): the tabs are the client's modules, in the API's
 * order, from `/me.nav` — never a fixed list in the app.
 */
describe("tabs from /me.nav", () => {
  it("follow the order of nav", () => {
    expect(tabPlan(["usage", "panel", "inbox"]).map((t) => t.module)).toEqual(["usage", "panel", "inbox"]);
    expect(tabPlan(["inbox", "panel"]).filter((t) => !t.hidden).map((t) => t.module)).toEqual(["inbox", "panel"]);
  });

  it("declare the absent modules too, hidden and last (native tabs cannot be added later)", () => {
    expect(tabPlan(["panel"])).toEqual([
      { module: "panel", hidden: false },
      { module: "inbox", hidden: true },
      { module: "usage", hidden: true },
    ]);
  });

  it("with one module there is one visible tab — the layout hides the bar", () => {
    expect(tabPlan(["usage"]).filter((t) => !t.hidden)).toHaveLength(1);
  });

  it("ignore a module this version does not know, without an empty tab", () => {
    expect(knownModules(["bookings", "panel"])).toEqual(["panel"]);
    expect(tabPlan(["bookings", "panel"]).map((t) => t.module)).not.toContain("bookings");
  });

  it("land on the first module of nav", () => {
    expect(firstRoute(["inbox", "panel"])).toBe("/bandeja");
    expect(firstRoute(["usage"])).toBe("/consumo");
  });

  it("a different nav is a different key: the bar remounts on the first module (R3.3, R3.5)", () => {
    const key = (nav: string[]) => knownModules(nav).join(",");
    expect(key(["panel", "inbox", "usage"])).not.toBe(key(["panel", "usage"]));
    expect(firstRoute(["panel", "usage"])).toBe("/inicio");
  });

  it("no module the app can show is no access (R3.7)", () => {
    expect(firstRoute([])).toBeNull();
    expect(firstRoute(["bookings"])).toBeNull();
  });
});
