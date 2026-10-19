import { describe, expect, it } from "vitest";

import { categoryName, connectorState, isChannelOnly, urgency } from "../labels";

describe("connector labels (spec 035, R4)", () => {
  it("channel rows of the catalog stay out of Conectores", () => {
    expect(isChannelOnly({ provider_meta: { channel_only: true } })).toBe(true);
    expect(isChannelOnly({ provider_meta: {} })).toBe(false);
  });

  it("reads Chatwoot's Activado / Deshabilitado and the states that need someone", () => {
    expect(connectorState("connected")).toMatchObject({ label: "Activado", active: true });
    expect(connectorState(null)).toMatchObject({ label: "Deshabilitado", active: false });
    expect(connectorState("needs_reauth").tone).toBe("danger");
  });

  it("puts what broke first", () => {
    const order = (["connected", null, "error", "pending"] as const).slice().sort((a, b) => urgency(a) - urgency(b));
    expect(order).toEqual(["error", "pending", "connected", null]);
  });

  it("names categories like the partner console", () => {
    expect(categoryName("booking")).toBe("Citas");
    expect(categoryName("unknown")).toBe("unknown");
  });
});
