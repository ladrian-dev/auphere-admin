import { describe, expect, it } from "vitest";

import { meterLabel } from "../meter-label";

const t = (key: string, vars?: Record<string, string | number>) => (vars ? `${key}:${JSON.stringify(vars)}` : key);

describe("meterLabel", () => {
  it("maps the known meters to copy keys", () => {
    expect(meterLabel("channel.message", t)).toBe("meter.channel.message");
    expect(meterLabel("llm.input_tokens", t)).toBe("meter.llm.input_tokens");
    expect(meterLabel("voice.minutes", t)).toBe("meter.voice.minutes");
  });
  it("labels media by kind and leaves the unknown untouched", () => {
    expect(meterLabel("media.image", t)).toBe('meter.media:{"kind":"image"}');
    expect(meterLabel("something.new", t)).toBe("something.new");
  });
});
