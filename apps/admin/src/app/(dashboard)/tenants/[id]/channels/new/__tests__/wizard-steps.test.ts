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

describe("a send-only client's channel wizard (spec 077, 2.2)", () => {
  it("has no agent step: connecting finishes", () => {
    expect(stepOf("/tenants/t1/channels/new", true)).toBe(0);
    expect(stepOf("/tenants/t1/channels/new/whatsapp", true)).toBe(1);
    expect(stepOf("/tenants/t1/channels/new/whatsapp/done", true)).toBe(2);
    // The agent step redirects to done; the rail never shows a step that is not there.
    expect(stepOf("/tenants/t1/channels/new/whatsapp/agent", true)).toBe(2);
  });
});
