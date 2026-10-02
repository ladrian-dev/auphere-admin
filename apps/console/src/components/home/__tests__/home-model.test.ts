import { describe, expect, it } from "vitest";

import { attentionRows, creditRunway, dayBars, spendShares, roundDays, statusTone, trendDelta } from "../home-model";

describe("Reglas del Inicio (spec 026)", () => {
  it("compara con el periodo anterior sin inventar variaciones", () => {
    expect(trendDelta(12, 10)).toEqual({ kind: "up", pct: 20 });
    expect(trendDelta(5, 10)).toEqual({ kind: "down", pct: 50 });
    expect(trendDelta(10, 10)).toEqual({ kind: "same", pct: 0 });
    expect(trendDelta(10, null)).toEqual({ kind: "none", pct: 0 });
    expect(trendDelta(10, 0)).toEqual({ kind: "none", pct: 0 });
  });

  it("da a cada estado su tono", () => {
    expect(statusTone("active")).toBe("positive");
    expect(statusTone("provisioning")).toBe("warning");
    expect(statusTone("paused")).toBe("danger");
    expect(statusTone("archived")).toBe("muted");
  });

  it("cada día es un total, hoy va marcado y el detalle son sus tres clientes con más conversaciones", () => {
    const trend = {
      days: ["2026-10-01", "2026-10-02"],
      series: [10, 4],
      current: 14,
      previous: null,
      by_client: [
        { external_client_ref: "a", client_name: "A", series: [6, 0] },
        { external_client_ref: "b", client_name: null, series: [3, 4] },
        { external_client_ref: null, client_name: null, series: [1, 0] },
      ],
    };
    const { bars, average, max } = dayBars(trend, "Resto");
    expect(average).toBe(7);
    expect(max).toBe(10);
    expect(bars[0]!.top).toEqual([{ label: "A", value: 6 }, { label: "b", value: 3 }, { label: "Resto", value: 1 }]);
    expect(bars[1]).toMatchObject({ total: 4, today: true, top: [{ label: "b", value: 4 }] });
  });

  it("redondea los días como lo diría una persona", () => {
    expect(roundDays(0.4)).toBe(0);
    expect(roundDays(6.6)).toBe(7);
    expect(roundDays(23)).toBe(25);
  });
});

describe("attentionRows", () => {
  const item = (ref: string, kind: "out_of_quota" | "failed_messages", count: number | null = null) => ({
    kind,
    severity: kind === "out_of_quota" ? 1 : 5,
    external_client_ref: ref,
    client_name: null,
    count,
    href: `/x/${ref}`,
  });
  it("groups a problem from three clients up, keeps fewer one per client, and keeps the order", () => {
    const rows = attentionRows([item("a", "out_of_quota"), item("b", "out_of_quota"), item("c", "out_of_quota"), item("d", "failed_messages", 2), item("e", "failed_messages", 1)]);
    expect(rows.map((r) => r.type)).toEqual(["many", "one", "one"]);
    expect(rows[0]).toMatchObject({ kind: "out_of_quota", names: ["a", "b", "c"], href: "/usage" });
  });

  it("with the partner's credit at zero, the blocked clients are one partner row, first", () => {
    const rows = attentionRows([item("a", "out_of_quota"), item("b", "out_of_quota"), item("d", "failed_messages", 2)], true);
    expect(rows[0]).toMatchObject({ type: "wallet", names: ["a", "b"], href: "/usage" });
    expect(rows.map((r) => r.type)).toEqual(["wallet", "one"]);
  });
});

describe("spendShares", () => {
  it("gives each slice its share and the shares add up to 100", () => {
    const share = (credits: number) => ({ kind: "client" as const, external_client_ref: "x", client_name: null, credits, cents: 0 });
    const out = spendShares([share(1), share(1), share(1)]);
    expect(out.map((s) => s.pct).reduce((a, b) => a + b, 0)).toBe(100);
    expect(spendShares([share(3), share(1)]).map((s) => s.pct)).toEqual([75, 25]);
    expect(spendShares([])).toEqual([]);
  });
});

describe("creditRunway", () => {
  const now = new Date("2026-10-02T12:00:00Z"); // 30 days left in October
  it("says how many of the month's days left the credit covers", () => {
    expect(creditRunway(5_000_000, 70, now)).toEqual({ days: 30, monthLeft: 30, tone: "positive" });
    expect(creditRunway(100_000, 12.6, now)).toEqual({ days: 12, monthLeft: 30, tone: "warning" });
    expect(creditRunway(10_000, 3, now)).toEqual({ days: 3, monthLeft: 30, tone: "danger" });
  });
  it("empty credit is an empty gauge, and no pace means no gauge", () => {
    expect(creditRunway(0, 4, now)).toBeNull();
    expect(creditRunway(5_000, null, now)).toBeNull();
    expect(creditRunway(null, 10, now)).toBeNull();
  });
});
