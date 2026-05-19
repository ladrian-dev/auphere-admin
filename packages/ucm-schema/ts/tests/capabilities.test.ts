import { describe, expect, it } from "vitest";
import {
  CHANNELS,
  channelSupports,
  getChannel,
  inferCapabilities,
} from "../src/index.js";

describe("capability matrix", () => {
  it("every channel supports text", () => {
    for (const name of Object.keys(CHANNELS) as Array<keyof typeof CHANNELS>) {
      expect(CHANNELS[name].capabilities.has("text")).toBe(true);
    }
  });

  it("voice supports only text", () => {
    expect(getChannel("voice").capabilities.size).toBe(1);
  });

  it("instagram lacks list and cta_url", () => {
    const ig = getChannel("instagram");
    expect(channelSupports(ig, "interactive.list")).toBe(false);
    expect(channelSupports(ig, "interactive.cta_url")).toBe(false);
    expect(channelSupports(ig, "flow")).toBe(false);
  });

  it("unknown channel throws", () => {
    expect(() => getChannel("snail-mail" as never)).toThrow();
  });

  it("inferCapabilities per type", () => {
    expect(inferCapabilities("text", { body: "x", format: "plain" })).toEqual(["text"]);
    expect(inferCapabilities("text", { body: "x", format: "markdown" })).toEqual([
      "text",
      "text.markdown",
    ]);
    expect(inferCapabilities("media", { kind: "video" })).toEqual(["media.video"]);
    expect(inferCapabilities("media", {})).toEqual(["media.image"]);
    expect(inferCapabilities("quick_replies", {})).toEqual(["interactive.buttons"]);
    expect(inferCapabilities("list", {})).toEqual(["interactive.list"]);
    expect(inferCapabilities("cta_url", {})).toEqual(["interactive.cta_url"]);
    expect(inferCapabilities("location", {})).toEqual(["location"]);
    expect(inferCapabilities("flow", {})).toEqual(["flow"]);
    expect(inferCapabilities("composite", {})).toEqual([]);
    expect(inferCapabilities("carousel", {})).toEqual([]);
  });
});
