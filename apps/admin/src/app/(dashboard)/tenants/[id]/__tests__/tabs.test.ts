import { describe, expect, it } from "vitest";

import { tenantTabGroups } from "../tabs";

const segs = (groups: ReturnType<typeof tenantTabGroups>) => groups.map((g) => g.tabs.map((t) => t.seg));

describe("the client's tabs (spec 077, 1.3 and 1.6)", () => {
  it("a client that is not send-only keeps exactly its tabs", () => {
    expect(segs(tenantTabGroups())).toEqual([
      ["", "conversations", "playground", "audit", "isolation"],
      ["agent", "capabilities", "access", "billing"],
      ["channels", "connectors", "backchannel"],
    ]);
    expect(tenantTabGroups({}, { sendOnly: false })).toEqual(tenantTabGroups());
  });

  it("a send-only client loses the agent's tabs and gains «Envío por API» under Conectar", () => {
    const groups = tenantTabGroups({ channels: "incident" }, { sendOnly: true });
    expect(segs(groups)).toEqual([
      ["", "conversations", "audit", "isolation"],
      ["access", "billing"],
      ["channels", "connectors", "api"],
    ]);
    const connect = groups.find((g) => g.key === "connect");
    expect(connect?.tabs.find((t) => t.seg === "api")?.label).toBe("Envío por API");
    // The channel's mark survives the filter.
    expect(connect?.tabs.find((t) => t.seg === "channels")?.mark).toBe("incident");
  });

  it("a client with send keys but no mark (New Air) also reaches «Envío por API» and keeps the rest", () => {
    expect(segs(tenantTabGroups({}, { hasSendKeys: true }))).toEqual([
      ["", "conversations", "playground", "audit", "isolation"],
      ["agent", "capabilities", "access", "billing"],
      ["channels", "connectors", "backchannel", "api"],
    ]);
  });
});
