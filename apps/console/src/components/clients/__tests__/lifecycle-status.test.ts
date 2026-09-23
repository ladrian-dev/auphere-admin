import { describe, expect, it } from "vitest";

import { deleteIsOffered, statusActionNeedsConfirm } from "../lifecycle-status";

describe("statusActionNeedsConfirm (QA-15)", () => {
  it("is true for paused and archived", () => {
    expect(statusActionNeedsConfirm("paused")).toBe(true);
    expect(statusActionNeedsConfirm("archived")).toBe(true);
  });
  it("is false for active (reactivate / unarchive / activate)", () => {
    expect(statusActionNeedsConfirm("active")).toBe(false);
  });
});

describe("deleteIsOffered", () => {
  it("only for an archived client, and only with the permission", () => {
    expect(deleteIsOffered("archived", true)).toBe(true);
    expect(deleteIsOffered("active", true)).toBe(false);
    expect(deleteIsOffered("paused", true)).toBe(false);
    expect(deleteIsOffered("archived", false)).toBe(false);
  });
});
