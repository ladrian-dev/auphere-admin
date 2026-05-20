import { describe, expect, it } from "vitest";
import {
  UCM_TYPES,
  UCM_VERSION,
  UCMMessageSchema,
  isSupportedUcmVersion,
} from "../src/index.js";
import { VALID, INVALID } from "./fixtures.js";

describe("UCM types", () => {
  for (const [key, fixture] of Object.entries(VALID)) {
    it(`parses valid fixture: ${key}`, () => {
      const r = UCMMessageSchema.safeParse(fixture);
      expect(r.success).toBe(true);
      if (r.success) {
        expect(r.data.ucm_version).toBe(UCM_VERSION);
        expect(UCM_TYPES).toContain(r.data.type);
      }
    });
  }

  for (const [key, fixture] of Object.entries(INVALID)) {
    it(`rejects invalid fixture: ${key}`, () => {
      const r = UCMMessageSchema.safeParse(fixture);
      expect(r.success).toBe(false);
    });
  }

  it("composite recurses correctly", () => {
    const r = UCMMessageSchema.parse(VALID["composite"]);
    expect(r.type).toBe("composite");
    if (r.type === "composite") {
      expect(r.content.children).toHaveLength(2);
      expect(r.content.children[0]!.type).toBe("text");
      expect(r.content.children[1]!.type).toBe("quick_replies");
    }
  });

  it("isSupportedUcmVersion", () => {
    expect(isSupportedUcmVersion("1.0.0")).toBe(true);
    expect(isSupportedUcmVersion("0.9.0")).toBe(false);
    expect(isSupportedUcmVersion(null)).toBe(false);
    expect(isSupportedUcmVersion(123)).toBe(false);
  });
});
