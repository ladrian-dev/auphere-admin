import { describe, expect, it } from "vitest";

import { brandFor } from "../brand-marks";

describe("brand marks (spec 035)", () => {
  it("finds the six channels and the connector slugs", () => {
    for (const key of ["whatsapp", "tiktok", "instagram", "telegram", "x", "threads"]) {
      expect(brandFor(key)?.path.length).toBeGreaterThan(10);
    }
    expect(brandFor("whatsapp_meta")?.title).toBe("WhatsApp");
    expect(brandFor("tiktok_bm")?.title).toBe("TikTok");
    expect(brandFor("woocommerce")?.title).toBe("WooCommerce");
  });

  it("falls through to the next key, and to nothing for our own apps", () => {
    expect(brandFor("amigable_cobro")).toBeNull();
    expect(brandFor("some_slug", "googlecalendar")?.title).toBe("Google Calendar");
  });
});
