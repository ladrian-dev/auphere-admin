import { describe, expect, it } from "vitest";
import { UCMMessageSchema, degrade, validate, type ChannelProfile } from "../src/index.js";
import { VALID } from "./fixtures.js";

const parse = (k: string) => UCMMessageSchema.parse(VALID[k]);

describe("degrade", () => {
  it("text passes through on web", () => {
    const r = degrade(parse("text_plain"), "web");
    expect(r.changed).toBe(false);
  });

  it("text.markdown → text on whatsapp", () => {
    const r = degrade(parse("text_markdown"), "whatsapp");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("text");
    if (r.ucm.type === "text") {
      expect(r.ucm.content.format).toBe("plain");
    }
  });

  it("quick_replies_5 → list on whatsapp", () => {
    const r = degrade(parse("quick_replies_5"), "whatsapp");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("list");
    // and the degraded form must itself validate cleanly on whatsapp
    const v = validate(r.ucm, "whatsapp");
    expect(v.ok).toBe(true);
  });

  it("quick_replies → text on voice (no buttons)", () => {
    const r = degrade(parse("quick_replies_3"), "voice");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("text");
    if (r.ucm.type === "text") {
      expect(r.ucm.content.body).toBe(parse("quick_replies_3").fallback_text);
    }
  });

  it("list → text on instagram", () => {
    const r = degrade(parse("list_small"), "instagram");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("text");
  });

  it("flow falls back everywhere except web & whatsapp", () => {
    const ucm = parse("flow");
    for (const ch of ["instagram", "messenger", "voice"] as const) {
      const r = degrade(ucm, ch);
      expect(r.changed).toBe(true);
      expect(r.ucm.type).toBe("text");
    }
    for (const ch of ["web", "whatsapp"] as const) {
      const r = degrade(ucm, ch);
      expect(r.changed).toBe(false);
    }
  });

  it("composite recurses and degrades children on voice", () => {
    const r = degrade(parse("composite"), "voice");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("composite");
    if (r.ucm.type === "composite") {
      const types = r.ucm.content.children.map((c) => c.type);
      expect(types).toEqual(["text", "text"]);
    }
  });

  it("cta_url passes on whatsapp", () => {
    const r = degrade(parse("cta_url"), "whatsapp");
    expect(r.changed).toBe(false);
  });

  it("cta_url → text on instagram (no capability)", () => {
    const r = degrade(parse("cta_url"), "instagram");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("text");
  });

  it("media → text on voice", () => {
    const r = degrade(parse("media_image"), "voice");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("text");
  });

  it("location → text on voice", () => {
    const r = degrade(parse("location"), "voice");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("text");
  });

  it("text body truncated to voice limit", () => {
    const payload = UCMMessageSchema.parse({
      ucm_version: "1.0.0",
      message_id: "x",
      type: "text",
      capabilities_required: ["text"],
      fallback_text: "fb",
      metadata: {},
      content: { body: "y".repeat(700), format: "plain" },
    });
    const r = degrade(payload, "voice");
    expect(r.changed).toBe(true);
    if (r.ucm.type === "text") {
      expect(r.ucm.content.body.length).toBe(600);
      expect(r.ucm.content.body.endsWith("…")).toBe(true);
    }
  });

  it("list truncated on whatsapp when sections > 10 rows", () => {
    const rows = (n: number) =>
      Array.from({ length: n }).map((_, i) => ({ id: `r${i}`, title: `R${i}` }));
    const payload = UCMMessageSchema.parse({
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
          { title: "S1", rows: rows(8) },
          { title: "S2", rows: rows(3) },
        ],
      },
    });
    const r = degrade(payload, "whatsapp");
    expect(r.changed).toBe(true);
    if (r.ucm.type === "list") {
      const total = r.ucm.content.sections.reduce((a, s) => a + s.rows.length, 0);
      expect(total).toBe(10);
    }
  });

  it("composite is flattened when deeper than channel allows", () => {
    const payload = UCMMessageSchema.parse({
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
    });
    const r = degrade(payload, "whatsapp");
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("composite");
    if (r.ucm.type === "composite") {
      expect(r.ucm.content.children.every((c) => c.type !== "composite")).toBe(true);
    }
  });
});

// ---- defensive paths exercised via custom ChannelProfile ----
// Some degrade branches are defensive: they handle hypothetical future
// channels with tighter limits than the schema itself enforces. We exercise
// them by passing a custom ChannelProfile directly to degrade/validate.

const TIGHT: ChannelProfile = {
  name: "whatsapp",
  capabilities: new Set([
    "text",
    "interactive.buttons",
    "interactive.list",
    "interactive.cta_url",
    "media.image",
  ]),
  limits: {
    quickRepliesMaxButtons: 2,
    quickRepliesTitleMaxChars: 5,
    listMaxRowsTotal: 4,
    listRowTitleMaxChars: 5,
    listRowDescriptionMaxChars: 10,
    listButtonTextMaxChars: 5,
    ctaUrlButtonTitleMaxChars: 5,
    textBodyMaxChars: 20,
    compositeMaxDepth: 1,
  },
};

const BUTTONS_ONLY: ChannelProfile = {
  name: "instagram",
  capabilities: new Set(["text", "interactive.buttons"]),
  limits: { quickRepliesMaxButtons: 2, textBodyMaxChars: 200 },
};

describe("degrade defensive paths (custom profiles)", () => {
  it("quick_replies title truncated when channel cap < schema cap", () => {
    const ucm = UCMMessageSchema.parse({
      ucm_version: "1.0.0",
      message_id: "x",
      type: "quick_replies",
      capabilities_required: ["interactive.buttons"],
      fallback_text: "fb",
      metadata: {},
      content: {
        body: "Pick",
        buttons: [
          { id: "a", title: "Yeshhh" },
          { id: "b", title: "Nooooo" },
        ],
      },
    });
    const r = degrade(ucm, TIGHT);
    expect(r.changed).toBe(true);
    if (r.ucm.type === "quick_replies") {
      for (const b of r.ucm.content.buttons) {
        expect(b.title.length).toBeLessThanOrEqual(5);
      }
    }
  });

  it("quick_replies → text when no list and too many buttons", () => {
    const ucm = UCMMessageSchema.parse({
      ucm_version: "1.0.0",
      message_id: "x",
      type: "quick_replies",
      capabilities_required: ["interactive.buttons"],
      fallback_text: "a/b/c",
      metadata: {},
      content: {
        body: "Pick",
        buttons: [
          { id: "a", title: "A" },
          { id: "b", title: "B" },
          { id: "c", title: "C" },
        ],
      },
    });
    const r = degrade(ucm, BUTTONS_ONLY);
    expect(r.changed).toBe(true);
    expect(r.ucm.type).toBe("text");
  });

  it("media caption + cta_url button + list button_text all truncate", () => {
    const m = degrade(
      UCMMessageSchema.parse({
        ucm_version: "1.0.0",
        message_id: "x",
        type: "media",
        capabilities_required: ["media.image"],
        fallback_text: "fb",
        metadata: {},
        content: {
          kind: "image",
          url: "https://x.com/i.jpg",
          caption: "this caption is more than twenty chars",
        },
      }),
      TIGHT,
    );
    expect(m.changed).toBe(true);

    const c = degrade(
      UCMMessageSchema.parse({
        ucm_version: "1.0.0",
        message_id: "x",
        type: "cta_url",
        capabilities_required: ["interactive.cta_url"],
        fallback_text: "fb",
        metadata: {},
        content: {
          body: "Reserva",
          button_title: "Reservar ya",
          url: "https://x.com/r",
        },
      }),
      TIGHT,
    );
    expect(c.changed).toBe(true);

    const l = degrade(
      UCMMessageSchema.parse({
        ucm_version: "1.0.0",
        message_id: "x",
        type: "list",
        capabilities_required: ["interactive.list"],
        fallback_text: "fb",
        metadata: {},
        content: {
          body: "Pick",
          button_text: "Ver más opciones",
          sections: [{ title: "S", rows: [{ id: "a", title: "longer title" }] }],
        },
      }),
      TIGHT,
    );
    expect(l.changed).toBe(true);
  });

  it("validate also accepts a ChannelProfile directly", () => {
    const ucm = UCMMessageSchema.parse({
      ucm_version: "1.0.0",
      message_id: "x",
      type: "text",
      capabilities_required: ["text"],
      fallback_text: "fb",
      metadata: {},
      content: { body: "y".repeat(50), format: "plain" },
    });
    const r = validate(ucm, TIGHT);
    expect(r.ok).toBe(false);
  });
});
