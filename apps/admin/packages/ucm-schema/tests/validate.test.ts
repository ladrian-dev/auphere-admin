import { describe, expect, it } from "vitest";
import { validate } from "../src/index.js";
import { VALID, INVALID } from "./fixtures.js";

describe("validate", () => {
  it.each([
    "text_plain",
    "quick_replies_3",
    "list_small",
    "cta_url",
    "media_image",
    "location",
    "flow",
  ])("%s passes on whatsapp", (key) => {
    const r = validate(VALID[key], "whatsapp");
    expect(r.ok).toBe(true);
  });

  it("quick_replies_5 fails on whatsapp (limit)", () => {
    const r = validate(VALID["quick_replies_5"], "whatsapp");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.issues.some((i) => i.kind === "limit" && i.message.includes("5 buttons"))).toBe(true);
    }
  });

  it("quick_replies_5 passes on instagram (cap=13)", () => {
    const r = validate(VALID["quick_replies_5"], "instagram");
    expect(r.ok).toBe(true);
  });

  it("list is unsupported on instagram (capability)", () => {
    const r = validate(VALID["list_small"], "instagram");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.issues.some((i) => i.kind === "capability")).toBe(true);
    }
  });

  it("text.markdown is unsupported on whatsapp", () => {
    const r = validate(VALID["text_markdown"], "whatsapp");
    expect(r.ok).toBe(false);
  });

  it("flow is unsupported on voice", () => {
    const r = validate(VALID["flow"], "voice");
    expect(r.ok).toBe(false);
  });

  it("shape errors surface as shape issues", () => {
    const r = validate(INVALID["missing_fallback"], "whatsapp");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.issues.every((i) => i.kind === "shape")).toBe(true);
    }
  });

  it("composite depth limit on whatsapp", () => {
    const nested = {
      ucm_version: "1.0.0",
      message_id: "x",
      type: "composite",
      capabilities_required: [],
      fallback_text: "f",
      metadata: {},
      content: {
        children: [
          {
            ucm_version: "1.0.0",
            message_id: "y",
            type: "composite",
            capabilities_required: [],
            fallback_text: "f",
            metadata: {},
            content: {
              children: [
                {
                  ucm_version: "1.0.0",
                  message_id: "z",
                  type: "text",
                  capabilities_required: ["text"],
                  fallback_text: "f",
                  metadata: {},
                  content: { body: "deep", format: "plain" },
                },
              ],
            },
          },
        ],
      },
    };
    const r = validate(nested, "whatsapp");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.issues.some((i) => i.message.includes("composite depth"))).toBe(true);
    }
  });

  it("list with too many rows fails on whatsapp", () => {
    const rows = Array.from({ length: 8 }).map((_, i) => ({ id: `r${i}`, title: `R${i}` }));
    const moreRows = Array.from({ length: 3 }).map((_, i) => ({ id: `s${i}`, title: `S${i}` }));
    const payload = {
      ucm_version: "1.0.0",
      message_id: "x",
      type: "list",
      capabilities_required: ["interactive.list"],
      fallback_text: "f",
      metadata: {},
      content: {
        body: "Pick",
        button_text: "Ver",
        sections: [
          { title: "S1", rows },
          { title: "S2", rows: moreRows },
        ],
      },
    };
    const r = validate(payload, "whatsapp");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.issues.some((i) => i.message.includes("rows total"))).toBe(true);
    }
  });

  it("voice text too long → limit issue", () => {
    const payload = {
      ucm_version: "1.0.0",
      message_id: "x",
      type: "text",
      capabilities_required: ["text"],
      fallback_text: "f",
      metadata: {},
      content: { body: "y".repeat(700), format: "plain" },
    };
    const r = validate(payload, "voice");
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.issues.some((i) => i.kind === "limit" && i.message.includes("text body"))).toBe(
        true,
      );
    }
  });

  it("location and flow basic validation", () => {
    const r1 = validate(VALID["location"], "web");
    expect(r1.ok).toBe(true);
    const r2 = validate(VALID["flow"], "web");
    expect(r2.ok).toBe(true);
  });

  it("composite content children walked", () => {
    const r = validate(VALID["composite"], "voice");
    expect(r.ok).toBe(false);
  });
});
