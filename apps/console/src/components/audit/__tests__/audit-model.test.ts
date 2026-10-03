import { describe, expect, it } from "vitest";

import type { AuditEntry } from "@/lib/backend";

import { actorName, dayKey, foldRepeats, initials, splitActor, whenLabel } from "../audit-model";

const words = { today: "Hoy", yesterday: "Ayer" };
const now = new Date("2026-10-03T10:00:00Z");

function entry(at: string, action: string, over: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: `${at}-${action}-${over.actor ?? ""}-${over.external_client_ref ?? ""}`,
    at,
    actor: "ana@x.com",
    action,
    target: "x",
    external_client_ref: "lola",
    client_name: "Lola",
    summary: `ana@x.com hizo ${action}`,
    ...over,
  };
}

describe("when", () => {
  it("puts an instant in the viewer's day, not in UTC's", () => {
    // 23:30 UTC on the 2nd is already the 3rd in Madrid.
    expect(dayKey("2026-10-02T23:30:00Z", "Europe/Madrid")).toBe("2026-10-03");
    expect(dayKey("2026-10-02T23:30:00Z", "UTC")).toBe("2026-10-02");
  });

  it("says Hoy and Ayer, and the date otherwise", () => {
    expect(whenLabel("2026-10-03T09:12:00Z", now, "UTC", "es", words)).toBe("Hoy, 09:12");
    expect(whenLabel("2026-10-02T20:32:00Z", now, "UTC", "es", words)).toBe("Ayer, 20:32");
    expect(whenLabel("2026-10-01T15:38:00Z", now, "UTC", "es", words)).toBe("1 oct, 15:38");
    expect(whenLabel("2025-12-24T10:00:00Z", now, "UTC", "es", words)).toContain("2025");
  });
});

describe("foldRepeats", () => {
  it("folds consecutive repeats of the same thing, never across a day", () => {
    const rows = foldRepeats(
      [
        entry("2026-10-03T09:00:00Z", "capability"),
        entry("2026-10-03T08:59:00Z", "capability"),
        entry("2026-10-03T08:58:00Z", "capability"),
        entry("2026-10-03T08:00:00Z", "publish"),
        entry("2026-10-03T07:00:00Z", "capability"),
        entry("2026-10-02T09:00:00Z", "capability"),
      ],
      "UTC",
    );
    expect(rows.map((r) => [r.item.action, r.repeats.length])).toEqual([
      ["capability", 2],
      ["publish", 0],
      ["capability", 0],
      ["capability", 0],
    ]);
  });

  it("does not fold the same action on another client or by another person", () => {
    const rows = foldRepeats(
      [
        entry("2026-10-03T09:00:00Z", "capability"),
        entry("2026-10-03T08:59:00Z", "capability", { external_client_ref: "espiga" }),
        entry("2026-10-03T08:58:00Z", "capability", { actor: "luis@x.com" }),
      ],
      "UTC",
    );
    expect(rows).toHaveLength(3);
  });
});

describe("the person in the row", () => {
  it("takes the person off the front of the sentence", () => {
    expect(splitActor("ana@x.com movió 5 US$ de A a B.", "ana@x.com")).toEqual({ lead: true, rest: "movió 5 US$ de A a B." });
    expect(splitActor("El agente pidió revisar un pago.", "ana@x.com")).toEqual({ lead: false, rest: "El agente pidió revisar un pago." });
  });

  it("shows names, not emails, when the team knows them", () => {
    const people = { "ana@x.com": "Ana Ruiz" };
    expect(actorName("ana@x.com", people)).toBe("Ana Ruiz");
    expect(actorName("Companion · ana@x.com", people)).toBe("Companion · Ana Ruiz");
    expect(actorName("Auphere", people)).toBe("Auphere");
    expect(initials("Ana Ruiz")).toBe("AR");
    expect(initials("ana@x.com")).toBe("A");
  });
});
