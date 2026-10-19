import { describe, expect, it } from "vitest";

import { stepOf } from "../wizard-steps";

describe("channel wizard steps (spec 035, R2)", () => {
  it("maps each route to its step, like Chatwoot's inbox wizard", () => {
    expect(stepOf("/tenants/t1/channels/new")).toBe(0);
    expect(stepOf("/tenants/t1/channels/new/whatsapp")).toBe(1);
    expect(stepOf("/tenants/t1/channels/new/whatsapp/agent")).toBe(2);
    expect(stepOf("/tenants/t1/channels/new/whatsapp/done")).toBe(3);
  });
});
