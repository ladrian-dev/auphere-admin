import { describe, expect, it } from "vitest";

import { isMissingKey, missingItems } from "../health";

describe("clients/health (spec 016)", () => {
  it("returns one item per missing piece, in the API's order, with its fix", () => {
    const items = missingItems({ missing: ["activation", "quota", "whatsapp", "agent"] }, "panaderia la espiga");
    expect(items.map((i) => i.key)).toEqual(["agent", "whatsapp", "quota", "activation"]);
    expect(items[0]).toMatchObject({ href: "/clients/panaderia%20la%20espiga/agent", permission: "agents:write", blocking: true });
    expect(items[1]).toMatchObject({ href: "/clients/panaderia%20la%20espiga/channels", permission: "channels:write", blocking: true });
    expect(items[2]).toMatchObject({
      label: "clients.detail.missing.quota",
      fix: "clients.health.fix.quota",
      href: "/usage?client=panaderia%20la%20espiga",
      permission: "usage:write",
      blocking: false,
    });
    expect(items[3]).toMatchObject({ href: null, permission: "clients:write", blocking: true });
  });
  it("ignores what it does not know instead of inventing a link", () => {
    expect(missingItems({ missing: ["something_new"] }, "x")).toEqual([]);
    expect(isMissingKey("quota")).toBe(true);
    expect(isMissingKey("something_new")).toBe(false);
  });
  it("is empty when nothing is missing", () => {
    expect(missingItems({ missing: [] }, "x")).toEqual([]);
  });
});
