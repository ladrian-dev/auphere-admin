import { describe, expect, it } from "vitest";

import { inviteConflictMessage } from "../invite-conflict";

describe("inviteConflictMessage (QA-18)", () => {
  it("409 uses the already-member copy", () => {
    expect(inviteConflictMessage(409, "raw", "Ya es miembro.")).toBe("Ya es miembro.");
  });
  it("other errors keep the fallback", () => {
    expect(inviteConflictMessage(500, "raw", "Ya es miembro.")).toBe("raw");
  });
});
