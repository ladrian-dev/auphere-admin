import { describe, expect, it } from "vitest";

import { headerMembershipPill } from "../send-only";

describe("the membership pill in a send-only client's header (spec 077)", () => {
  it("without a membership there is no pill: the absence is designed", () => {
    expect(headerMembershipPill(null)).toBeNull();
  });

  it("a membership that could not be read says so, muted, instead of vanishing like «none»", () => {
    expect(headerMembershipPill("error")).toEqual({ label: "Membresía: sin leer", tone: "muted" });
  });

  it("a membership read says its state, as the billing card does", () => {
    expect(headerMembershipPill({ status: "active", active: true })).toEqual({ label: "Membresía: activa", tone: "positive" });
    expect(headerMembershipPill({ status: "past_due", active: false })).toEqual({
      label: "Membresía: impagada",
      tone: "danger",
    });
  });
});
