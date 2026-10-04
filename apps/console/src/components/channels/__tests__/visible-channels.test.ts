import { describe, expect, it } from "vitest";

import { f2ChannelCounter, f2SignupEnabled, f2VisibleChannels, isF2VisibleChannel } from "../visible-channels";

describe("F2 visible channels", () => {
  it("only WhatsApp is visible; TikTok/IG/web/MCP custom are out", () => {
    expect(isF2VisibleChannel("whatsapp")).toBe(true);
    for (const type of ["tiktok", "instagram", "web", "mcp", "mcp_custom", "coming_soon"]) {
      expect(isF2VisibleChannel(type)).toBe(false);
    }
    const visible = f2VisibleChannels([
      { type: "whatsapp", status: "active" },
      { type: "tiktok", status: "active" },
      { type: "instagram", status: "active" },
      { type: "web", status: "active" },
      { type: "mcp", status: "active" },
    ]);
    expect(visible.map((c) => c.type)).toEqual(["whatsapp"]);
  });

  it("a disconnected number leaves the page unless Meta still has steps to finish", () => {
    const visible = f2VisibleChannels([
      { type: "whatsapp", status: "active" },
      { type: "whatsapp", status: "disconnected", unlink_pending: [] },
      { type: "whatsapp", status: "disconnected" },
      { type: "whatsapp", status: "disconnected", unlink_pending: ["unsubscribe"] },
      { type: "whatsapp", status: "degraded" },
    ]);
    expect(visible.map((c) => `${c.status}:${c.unlink_pending?.length ?? 0}`)).toEqual(["active:0", "disconnected:1", "degraded:0"]);
  });

  it("counter is N de 1 (M always 1)", () => {
    expect(f2ChannelCounter([])).toEqual({ n: 0, m: 1 });
    expect(f2ChannelCounter([{ type: "whatsapp", status: "active" }])).toEqual({ n: 1, m: 1 });
    expect(f2ChannelCounter([{ type: "whatsapp", status: "disconnected" }])).toEqual({ n: 0, m: 1 });
    expect(
      f2ChannelCounter([
        { type: "whatsapp", status: "active" },
        { type: "whatsapp", status: "active" },
        { type: "tiktok", status: "active" },
      ]),
    ).toEqual({ n: 1, m: 1 });
  });

  it("signup CTA stays disabled in this hop", () => {
    expect(f2SignupEnabled()).toBe(false);
  });
});
