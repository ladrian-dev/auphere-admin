import { describe, expect, it } from "vitest";

import { statusActionNeedsConfirm } from "../lifecycle-status";

describe("statusActionNeedsConfirm (QA-15)", () => {
  it("is true for paused and archived", () => {
    expect(statusActionNeedsConfirm("paused")).toBe(true);
    expect(statusActionNeedsConfirm("archived")).toBe(true);
  });
  it("is false for active (reactivate / unarchive / activate)", () => {
    expect(statusActionNeedsConfirm("active")).toBe(false);
  });
});
