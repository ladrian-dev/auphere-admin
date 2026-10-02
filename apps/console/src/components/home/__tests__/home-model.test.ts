import { describe, expect, it } from "vitest";

import { attentionRows, chartData, roundDays, statusTone, trendDelta } from "../home-model";

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

  it("monta la gráfica apilada con el resto al final", () => {
    const data = chartData(
      {
        days: ["2026-10-01", "2026-10-02"],
        series: [3, 5],
        current: 8,
        previous: null,
        by_client: [
          { external_client_ref: "flor", client_name: "Flor y Encanto", series: [2, 4] },
          { external_client_ref: null, client_name: null, series: [1, 1] },
        ],
      },
      "Resto de clientes",
    );
    expect(data.series).toEqual([
      { key: "s0", label: "Flor y Encanto" },
      { key: "s1", label: "Resto de clientes" },
    ]);
    expect(data.rows[1]).toEqual({ day: "2026-10-02", s0: 4, s1: 1 });
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
