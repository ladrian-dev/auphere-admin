import { describe, expect, it } from "vitest";

import { currentTab } from "../profile-tabs";

describe("profile tabs (spec 035)", () => {
  const segs = ["", "agent", "channels", "connectors"];
  it("keeps a tab lit on its sub-pages", () => {
    expect(currentTab("/tenants/t1", "/tenants/t1", segs)).toBe("");
    expect(currentTab("/tenants/t1/channels/new/whatsapp", "/tenants/t1", segs)).toBe("channels");
    expect(currentTab("/tenants/t1/agent", "/tenants/t1", segs)).toBe("agent");
  });
});
