import { describe, expect, it } from "vitest";

import { isActive, navForRole } from "../nav";

describe("nav", () => {
  it("filters items by role", () => {
    const billing = navForRole("billing").flatMap((g) => g.items.map((i) => i.href));
    expect(billing).toEqual(["/", "/usage", "/team", "/billing"]);
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
