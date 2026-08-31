import { describe, expect, it } from "vitest";

import { auditActionLabel, auditActionOptions } from "../audit-actions";

describe("auditActionOptions (QA-21)", () => {
  it("uses human summaries as labels, not the machine code", () => {
    const opts = auditActionOptions([
      { action: "console.client.status", summary: "Suspendió un cliente" },
      { action: "knowledge.add_url", summary: "Añadió un documento" },
    ]);
    expect(opts.map((o) => o.label)).toEqual(["Añadió un documento", "Suspendió un cliente"]);
    expect(auditActionLabel("console.client.status", opts)).toBe("Suspendió un cliente");
    expect(opts.some((o) => o.label === "console.client.status")).toBe(false);
  });
});
